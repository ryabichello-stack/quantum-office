"""Read Google Sheets via public CSV; write via Service Account when configured."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("sheets-campaign.io")

SHEET_ID = os.getenv("SHEET_ID", "1xjr7vtz56ro9WD8lTIBj3uGliSSN3mh2KHZFJPdLGXE").strip()
PHONE_HEADER = "Номер телефона"
NOTE_HEADER = "Пометки Клиента"
TRANSCRIPT_HEADER = "Транскрибация"
STATUS_HEADER = "Статус (IVR=Положительный)"
START_HEADER = "Начало звонка"
TRANSFER_HEADER = "Дата передачи номера на прозвонку"


def _parse_tabs() -> list[tuple[str, str]]:
    raw = os.getenv(
        "SHEET_TABS",
        "НомераКлиентов:467949580,НомераКлиентов Архив:323510684",
    )
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
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
            # pad
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


def sheets_write_enabled() -> bool:
    path = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    return bool(path and os.path.isfile(path))


def _sheets_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def update_lead_result(
    lead: LeadRow,
    *,
    note: str,
    transcript: str = "",
    status: str = "",
    call_started: str = "",
) -> dict[str, Any]:
    """Write note/transcript/status back to the sheet row."""
    if not sheets_write_enabled():
        return {"ok": False, "error": "google_sa_not_configured"}

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
    if call_started:
        # best-effort column by header name if present in original header map —
        # we only stored key cols; optional transfer/start via letters R/S if needed.
        pass

    if not data:
        return {"ok": False, "error": "nothing_to_write"}

    body = {"valueInputOption": "USER_ENTERED", "data": data}
    result = (
        svc.spreadsheets()
        .values()
        .batchUpdate(spreadsheetId=SHEET_ID, body=body)
        .execute()
    )
    return {"ok": True, "updated": result.get("totalUpdatedCells"), "ranges": [d["range"] for d in data]}


def sa_email() -> Optional[str]:
    path = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        doc = json.loads(open(path, encoding="utf-8").read())
        return str(doc.get("client_email") or "") or None
    except Exception:
        return None
