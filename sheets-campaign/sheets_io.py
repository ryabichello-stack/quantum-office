"""Read Google Sheets via public CSV; write via Service Account or webhook."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("sheets-campaign.io")

SHEET_ID = os.getenv("SHEET_ID", "1xjr7vtz56ro9WD8lTIBj3uGliSSN3mh2KHZFJPdLGXE").strip()
PHONE_HEADER = "Номер телефона"
NOTE_HEADER = "Пометки Клиента"
TRANSCRIPT_HEADER = "Транскрибация"
STATUS_HEADER = "Статус (IVR=Положительный)"
START_HEADER = "Начало звонка"
TRANSFER_HEADER = "Дата передачи номера на прозвонку"

DEFAULT_SA_PATH = Path(
    os.getenv("GOOGLE_SERVICE_ACCOUNT_DEFAULT", "/opt/ava-sheets-campaign/sa.json")
)


def _parse_tabs() -> list[tuple[str, str]]:
    raw = os.getenv(
        "SHEET_TABS",
        "НомераКлиентов:467949580,НомераКлиентов Архив:323510684",
    )
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip().strip('"')
        if not part:
            continue
        if ":" not in part:
            continue
        name, gid = part.rsplit(":", 1)
        out.append((name.strip(), gid.strip()))
    return out


@dataclass
class LeadRow:
    sheet_name: str
    gid: str
    row_number: int  # 1-indexed in sheet (header=1)
    phone: str
    date: str
    source: str
    note: str
    transcript: str
    status: str
    col_index: dict[str, int]


def _col_letter(idx0: int) -> str:
    """0-based index → A1 column letters."""
    n = idx0 + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def fetch_csv(gid: str) -> list[list[str]]:
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
        f"?format=csv&gid={urllib.parse.quote(gid)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ava-sheets-campaign/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    text = raw.decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def _header_index(header: list[str], name: str) -> int:
    for i, h in enumerate(header):
        if (h or "").strip() == name:
            return i
    raise KeyError(f"column not found: {name!r} in {header[:25]}")


def load_leads(*, only_empty_notes: bool = True, sheet_filter: str | None = None) -> list[LeadRow]:
    leads: list[LeadRow] = []
    for name, gid in _parse_tabs():
        if sheet_filter and sheet_filter not in (name, gid):
            continue
        rows = fetch_csv(gid)
        if not rows:
            continue
        header = rows[0]
        phone_i = _header_index(header, PHONE_HEADER)
        note_i = _header_index(header, NOTE_HEADER)
        try:
            tr_i = _header_index(header, TRANSCRIPT_HEADER)
        except KeyError:
            tr_i = -1
        try:
            st_i = _header_index(header, STATUS_HEADER)
        except KeyError:
            st_i = -1
        date_i = 1 if len(header) > 1 else -1
        src_i = 2 if len(header) > 2 else -1
        cols = {
            PHONE_HEADER: phone_i,
            NOTE_HEADER: note_i,
            TRANSCRIPT_HEADER: tr_i,
            STATUS_HEADER: st_i,
        }
        for offset, row in enumerate(rows[1:], start=2):
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            phone = (row[phone_i] or "").strip()
            if not phone:
                continue
            note = (row[note_i] or "").strip()
            if only_empty_notes and note:
                continue
            leads.append(
                LeadRow(
                    sheet_name=name,
                    gid=gid,
                    row_number=offset,
                    phone=phone,
                    date=(row[date_i] if date_i >= 0 else "") or "",
                    source=(row[src_i] if src_i >= 0 else "") or "",
                    note=note,
                    transcript=(row[tr_i] if tr_i >= 0 else "") or "",
                    status=(row[st_i] if st_i >= 0 else "") or "",
                    col_index=cols,
                )
            )
    return leads


def _sa_file_path() -> str:
    path = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if path and os.path.isfile(path):
        return path
    inline = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if inline:
        # Materialize inline JSON to a temp/default file for google-auth.
        target = DEFAULT_SA_PATH
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.read_text(encoding="utf-8") != inline:
                target.write_text(inline, encoding="utf-8")
                os.chmod(target, 0o600)
            os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = str(target)
            return str(target)
        except Exception:
            logger.exception("failed to materialize GOOGLE_SERVICE_ACCOUNT_JSON")
    if DEFAULT_SA_PATH.is_file():
        os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_FILE", str(DEFAULT_SA_PATH))
        return str(DEFAULT_SA_PATH)
    return ""


def sheets_write_enabled() -> bool:
    if _sa_file_path():
        return True
    return bool((os.getenv("SHEETS_WEBHOOK_URL") or "").strip())


def write_mode() -> str:
    if _sa_file_path():
        return "service_account"
    if (os.getenv("SHEETS_WEBHOOK_URL") or "").strip():
        return "webhook"
    return "off"


def _sheets_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    path = _sa_file_path()
    if not path:
        raise RuntimeError("google_sa_not_configured")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _update_via_sa(
    lead: LeadRow,
    *,
    note: str,
    transcript: str = "",
    status: str = "",
) -> dict[str, Any]:
    svc = _sheets_service()
    sheet = lead.sheet_name
    data: list[dict[str, Any]] = []

    def add(col_name: str, value: str) -> None:
        idx = lead.col_index.get(col_name, -1)
        if idx is None or idx < 0 or not value:
            return
        a1 = f"{sheet}!{_col_letter(idx)}{lead.row_number}"
        data.append({"range": a1, "values": [[value]]})

    add(NOTE_HEADER, note)
    add(TRANSCRIPT_HEADER, transcript[:45000] if transcript else "")
    add(STATUS_HEADER, status)

    if not data:
        return {"ok": False, "error": "nothing_to_write", "mode": "service_account"}

    body = {"valueInputOption": "USER_ENTERED", "data": data}
    result = (
        svc.spreadsheets()
        .values()
        .batchUpdate(spreadsheetId=SHEET_ID, body=body)
        .execute()
    )
    return {
        "ok": True,
        "mode": "service_account",
        "updated": result.get("totalUpdatedCells"),
        "ranges": [d["range"] for d in data],
    }


def _update_via_webhook(
    lead: LeadRow,
    *,
    note: str,
    transcript: str = "",
    status: str = "",
) -> dict[str, Any]:
    url = (os.getenv("SHEETS_WEBHOOK_URL") or "").strip()
    if not url:
        return {"ok": False, "error": "webhook_not_configured", "mode": "webhook"}
    token = (os.getenv("SHEETS_WEBHOOK_TOKEN") or os.getenv("WEBHOOK_TOKEN") or "").strip()
    payload = {
        "token": token,
        "sheet_id": SHEET_ID,
        "sheet_name": lead.sheet_name,
        "gid": lead.gid,
        "row": lead.row_number,
        "phone": lead.phone,
        "note": note,
        "transcript": transcript[:45000] if transcript else "",
        "status": status,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"raw": raw}
            ok = bool(body.get("ok", True))
            return {"ok": ok, "mode": "webhook", "response": body}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"http_{exc.code}", "detail": err[:500], "mode": "webhook"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "mode": "webhook"}


def update_lead_result(
    lead: LeadRow,
    *,
    note: str,
    transcript: str = "",
    status: str = "",
    call_started: str = "",
) -> dict[str, Any]:
    """Write note/transcript/status back to the sheet row."""
    _ = call_started  # reserved for optional start-time column
    mode = write_mode()
    if mode == "service_account":
        try:
            return _update_via_sa(lead, note=note, transcript=transcript, status=status)
        except Exception as exc:
            logger.exception("SA write failed")
            return {"ok": False, "error": str(exc), "mode": "service_account"}
    if mode == "webhook":
        return _update_via_webhook(lead, note=note, transcript=transcript, status=status)
    return {"ok": False, "error": "google_sa_not_configured", "mode": "off"}


def sa_email() -> Optional[str]:
    path = _sa_file_path()
    if not path or not os.path.isfile(path):
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return str(doc.get("client_email") or "") or None
    except Exception:
        return None


def install_service_account(doc: dict[str, Any], *, path: str | None = None) -> dict[str, Any]:
    """Save SA JSON, enable writeback in-process + .env hint path."""
    if not isinstance(doc, dict):
        return {"ok": False, "error": "json_object_required"}
    if doc.get("type") != "service_account" or not doc.get("client_email") or not doc.get("private_key"):
        return {"ok": False, "error": "not_a_service_account_json"}
    target = Path(path or str(DEFAULT_SA_PATH))
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, ensure_ascii=False, indent=2)
    # atomic write
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".sa-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass

    os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = str(target)
    # Keep .env in sync for service restarts
    env_path = Path("/opt/ava-sheets-campaign/.env")
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        done = False
        for line in lines:
            if line.startswith("GOOGLE_SERVICE_ACCOUNT_FILE="):
                out.append(f"GOOGLE_SERVICE_ACCOUNT_FILE={target}")
                done = True
            else:
                out.append(line)
        if not done:
            out.append(f"GOOGLE_SERVICE_ACCOUNT_FILE={target}")
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass

    email = str(doc.get("client_email") or "")
    return {
        "ok": True,
        "path": str(target),
        "sa_email": email,
        "sheets_write_enabled": True,
        "write_mode": "service_account",
        "share_hint": (
            f"Откройте таблицу → Настройки доступа → добавить {email} как Редактор"
            if email
            else "Расшарьте таблицу на client_email из JSON (Редактор)"
        ),
    }


def write_status() -> dict[str, Any]:
    return {
        "sheets_write_enabled": sheets_write_enabled(),
        "write_mode": write_mode(),
        "sa_email": sa_email(),
        "sa_path": _sa_file_path() or None,
        "webhook_configured": bool((os.getenv("SHEETS_WEBHOOK_URL") or "").strip()),
        "sheet_id": SHEET_ID,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit",
    }
