"""Campaign runner: sheet → console dial → await → classify → writeback."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import classify
import script
import script_store
import sheets_io

logger = logging.getLogger("sheets-campaign.runner")

CONSOLE_BASE = os.getenv("CONSOLE_BASE", "http://127.0.0.1:8013").rstrip("/")
CONSOLE_TOKEN = os.getenv("CONSOLE_TOKEN", "").strip()
CALL_GAP_SECONDS = int(os.getenv("CALL_GAP_SECONDS", "45") or "45")
CALL_WAIT_SECONDS = int(os.getenv("CALL_WAIT_SECONDS", "240") or "240")
DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-sheets-campaign/data"))


class CampaignState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.stop_flag = False
        self.thread: Optional[threading.Thread] = None
        self.status: dict[str, Any] = {
            "running": False,
            "processed": 0,
            "interested": 0,
            "errors": 0,
            "last": None,
            "message": "idle",
        }


STATE = CampaignState()


def _db_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "campaign.db"


def init_db() -> None:
    conn = sqlite3.connect(str(_db_path()))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_name TEXT,
                gid TEXT,
                row_number INTEGER,
                phone TEXT,
                note TEXT,
                status TEXT,
                interest TEXT,
                transcript TEXT,
                call_id TEXT,
                channel_id TEXT,
                written INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _console_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if CONSOLE_TOKEN:
        h["X-Console-Token"] = CONSOLE_TOKEN
        h["Authorization"] = f"Bearer {CONSOLE_TOKEN}"
    return h


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 60) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_console_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {err[:500]}") from exc


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def dial_lead(phone: str, *, dry_run: bool = False) -> dict[str, Any]:
    phone_n = normalize_phone(phone)
    playbook = script_store.load_script()
    tools = list(playbook.get("tools") or script.CAMPAIGN_TOOLS)
    payload = {
        "phone": phone_n,
        "context": "outbound",
        "greeting": str(playbook.get("greeting") or script.GREETING),
        "script": str(playbook.get("script") or script.SCRIPT),
        "use_knowledge": "get_company_knowledge" in tools,
        "tools": tools,
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "phone": phone_n, "payload": payload}
    return _http_json("POST", f"{CONSOLE_BASE}/api/outbound/dial", payload, timeout=45)


def await_call(phone: str, *, dialed_after: float, timeout: float) -> dict[str, Any] | None:
    phone_n = normalize_phone(phone)
    deadline = time.time() + timeout
    best: dict[str, Any] | None = None
    while time.time() < deadline:
        data = _http_json(
            "GET",
            f"{CONSOLE_BASE}/api/calls?limit=30&context=outbound",
            timeout=30,
        )
        for call in data.get("calls") or []:
            caller = normalize_phone(str(call.get("caller_number") or ""))
            if caller != phone_n:
                continue
            start = str(call.get("start_time") or "")
            # ISO-ish compare: accept if start_time >= dialed_after - 30s window via parse
            try:
                # many stores use ISO UTC
                ts = datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = 0
            if ts and ts + 5 < dialed_after:
                continue
            cid = str(call.get("call_id") or "")
            if not cid:
                continue
            detail = _http_json(
                "GET",
                f"{CONSOLE_BASE}/api/calls/{urllib.parse.quote(cid, safe='')}",
                timeout=30,
            )
            call_full = detail.get("call") or {}
            if call_full.get("end_time") or call_full.get("outcome") not in (None, "", "in_progress"):
                return call_full
            best = call_full
        time.sleep(5)
    return best


def _save_result(row: dict[str, Any]) -> None:
    conn = sqlite3.connect(str(_db_path()))
    try:
        conn.execute(
            """
            INSERT INTO results (
                sheet_name, gid, row_number, phone, note, status, interest,
                transcript, call_id, channel_id, written, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("sheet_name"),
                row.get("gid"),
                row.get("row_number"),
                row.get("phone"),
                row.get("note"),
                row.get("status"),
                row.get("interest"),
                row.get("transcript"),
                row.get("call_id"),
                row.get("channel_id"),
                1 if row.get("written") else 0,
                row.get("created_at"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def flush_writebacks(limit: int = 50) -> dict[str, Any]:
    if not sheets_io.sheets_write_enabled():
        return {"ok": False, "error": "google_sa_not_configured", "flushed": 0}
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    flushed = 0
    errors: list[str] = []
    try:
        rows = conn.execute(
            "SELECT * FROM results WHERE written = 0 ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        for r in rows:
            lead = sheets_io.LeadRow(
                sheet_name=r["sheet_name"],
                gid=r["gid"],
                row_number=int(r["row_number"]),
                phone=r["phone"],
                date="",
                source="",
                note="",
                transcript="",
                status="",
                col_index={
                    sheets_io.NOTE_HEADER: 22,
                    sheets_io.TRANSCRIPT_HEADER: 20,
                    sheets_io.STATUS_HEADER: 21,
                    sheets_io.PHONE_HEADER: 0,
                },
            )
            # Refresh column indexes from live header
            try:
                live = sheets_io.load_leads(only_empty_notes=False, sheet_filter=r["gid"])
                match = next((x for x in live if x.row_number == int(r["row_number"])), None)
                if match:
                    lead = match
            except Exception as exc:
                errors.append(f"reload:{exc}")
            wr = sheets_io.update_lead_result(
                lead,
                note=r["note"] or "",
                transcript=r["transcript"] or "",
                status=r["status"] or "",
            )
            if wr.get("ok"):
                conn.execute("UPDATE results SET written = 1 WHERE id = ?", (r["id"],))
                conn.commit()
                flushed += 1
            else:
                errors.append(str(wr.get("error")))
    finally:
        conn.close()
    return {"ok": True, "flushed": flushed, "errors": errors[:10]}


def _process_one(lead: sheets_io.LeadRow, *, dry_run: bool) -> dict[str, Any]:
    dialed_after = time.time()
    dial = dial_lead(lead.phone, dry_run=dry_run)
    if dry_run:
        note = "DRY_RUN — не звонили"
        result = {
            "sheet_name": lead.sheet_name,
            "gid": lead.gid,
            "row_number": lead.row_number,
            "phone": normalize_phone(lead.phone),
            "note": note,
            "status": "",
            "interest": "maybe",
            "transcript": "",
            "call_id": "",
            "channel_id": "",
            "written": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dial": dial,
        }
        _save_result(result)
        return result

    if not dial.get("ok"):
        raise RuntimeError(f"dial failed: {dial}")

    call = await_call(lead.phone, dialed_after=dialed_after - 15, timeout=float(CALL_WAIT_SECONDS))
    conversation = (call or {}).get("conversation") or (call or {}).get("turns") or []
    # turns from API may be richer
    if (call or {}).get("turns") and not conversation:
        conversation = [
            {"role": t.get("role"), "content": t.get("text")}
            for t in (call.get("turns") or [])
        ]
    duration = int((call or {}).get("duration_seconds") or 0)
    outcome = str((call or {}).get("outcome") or "")
    cls = classify.classify(conversation, outcome=outcome, duration=duration)
    transcript = "\n".join(
        f"{(t.get('who') or t.get('role') or '')}: {(t.get('text') or t.get('content') or '')}".strip()
        for t in (
            (call or {}).get("turns")
            or [
                {"role": x.get("role"), "text": x.get("content")}
                for x in (conversation or [])
                if isinstance(x, dict)
            ]
        )
    )
    written = False
    write_info: dict[str, Any] = {}
    if sheets_io.sheets_write_enabled():
        write_info = sheets_io.update_lead_result(
            lead,
            note=cls["note"],
            transcript=transcript,
            status=cls.get("status") or "",
        )
        written = bool(write_info.get("ok"))

    result = {
        "sheet_name": lead.sheet_name,
        "gid": lead.gid,
        "row_number": lead.row_number,
        "phone": normalize_phone(lead.phone),
        "note": cls["note"],
        "status": cls.get("status") or "",
        "interest": cls.get("interest") or "",
        "transcript": transcript,
        "call_id": str((call or {}).get("call_id") or ""),
        "channel_id": str(dial.get("channel_id") or ""),
        "written": written,
        "write_info": write_info,
        "classify_method": cls.get("method"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_result(result)
    return result


def _worker(*, max_calls: int, sheet_filter: str | None, dry_run: bool) -> None:
    with STATE.lock:
        # running already set by start_campaign; refresh message
        STATE.stop_flag = False
        STATE.status.update(
            {
                "running": True,
                "processed": 0,
                "interested": 0,
                "errors": 0,
                "message": "loading leads",
                "started_at": STATE.status.get("started_at")
                or datetime.now(timezone.utc).isoformat(),
            }
        )
    try:
        leads = sheets_io.load_leads(only_empty_notes=True, sheet_filter=sheet_filter)
        # Prefer active tab first
        leads.sort(key=lambda x: (0 if "Архив" not in x.sheet_name else 1, x.row_number))
        if max_calls > 0:
            leads = leads[:max_calls]
        with STATE.lock:
            STATE.status["queued"] = len(leads)
            STATE.status["message"] = f"queued {len(leads)}"
        for lead in leads:
            if STATE.stop_flag:
                break
            try:
                with STATE.lock:
                    STATE.status["message"] = f"dialing {lead.phone} ({lead.sheet_name}#{lead.row_number})"
                result = _process_one(lead, dry_run=dry_run)
                with STATE.lock:
                    STATE.status["processed"] += 1
                    if str(result.get("interest")) == "yes":
                        STATE.status["interested"] += 1
                    STATE.status["last"] = {
                        "phone": result.get("phone"),
                        "note": result.get("note"),
                        "written": result.get("written"),
                        "call_id": result.get("call_id"),
                    }
            except Exception as exc:
                logger.exception("lead failed phone=%s", lead.phone)
                with STATE.lock:
                    STATE.status["errors"] += 1
                    STATE.status["last_error"] = str(exc)
            if STATE.stop_flag:
                break
            time.sleep(max(0, CALL_GAP_SECONDS))
        with STATE.lock:
            STATE.status["message"] = "done" if not STATE.stop_flag else "stopped"
    finally:
        with STATE.lock:
            STATE.running = False
            STATE.status["running"] = False
            STATE.status["finished_at"] = datetime.now(timezone.utc).isoformat()


def start_campaign(
    *,
    max_calls: int | None = None,
    sheet: str | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    with STATE.lock:
        # Recover if previous thread died without clearing the flag
        if STATE.running and STATE.thread is not None and not STATE.thread.is_alive():
            STATE.running = False
            STATE.status["running"] = False
            STATE.status["message"] = "recovered_stale_worker"
        if STATE.running:
            return {"ok": False, "error": "already_running", "status": dict(STATE.status)}
        STATE.running = True
        STATE.stop_flag = False
        STATE.status.update(
            {
                "running": True,
                "processed": 0,
                "interested": 0,
                "errors": 0,
                "message": "starting",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "last_error": None,
            }
        )
    init_db()
    if max_calls is None:
        max_calls = int(os.getenv("MAX_CALLS_PER_RUN", "5") or "5")
    if dry_run is None:
        dry_run = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
    t = threading.Thread(
        target=_worker,
        kwargs={"max_calls": int(max_calls), "sheet_filter": sheet, "dry_run": bool(dry_run)},
        daemon=True,
    )
    with STATE.lock:
        STATE.thread = t
    t.start()
    return {
        "ok": True,
        "started": True,
        "max_calls": max_calls,
        "dry_run": dry_run,
        "sheet": sheet,
        "message": f"Обзвон запущен (max_calls={max_calls}"
        + (", dry_run" if dry_run else "")
        + ")",
    }


def stop_campaign() -> dict[str, Any]:
    with STATE.lock:
        STATE.stop_flag = True
        alive = bool(STATE.thread and STATE.thread.is_alive())
        if STATE.running and not alive:
            STATE.running = False
            STATE.status["running"] = False
            STATE.status["message"] = "stopped_stale"
        return {
            "ok": True,
            "stopping": STATE.running,
            "thread_alive": alive,
            "status": dict(STATE.status),
            "message": "Остановка запрошена" if STATE.running else "Обзвон не был запущен",
        }


def get_status() -> dict[str, Any]:
    with STATE.lock:
        st = dict(STATE.status)
        st["sheets_write_enabled"] = sheets_io.sheets_write_enabled()
        st["sa_email"] = sheets_io.sa_email()
        return st


def preview(limit: int = 30, sheet: str | None = None) -> dict[str, Any]:
    leads = sheets_io.load_leads(only_empty_notes=True, sheet_filter=sheet)
    leads.sort(key=lambda x: (0 if "Архив" not in x.sheet_name else 1, x.row_number))
    by_sheet: dict[str, int] = {}
    for x in leads:
        by_sheet[x.sheet_name] = by_sheet.get(x.sheet_name, 0) + 1
    items = [
        {
            "sheet": x.sheet_name,
            "gid": x.gid,
            "row": x.row_number,
            "phone": x.phone,
            "source": x.source,
            "date": x.date,
            "sheet_url": (
                f"https://docs.google.com/spreadsheets/d/{sheets_io.SHEET_ID}"
                f"/edit#gid={x.gid}"
            ),
        }
        for x in leads[:limit]
    ]
    return {
        "ok": True,
        "total_pending": len(leads),
        "showing": len(items),
        "by_sheet": by_sheet,
        "items": items,
        "sheet_id": sheets_io.SHEET_ID,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheets_io.SHEET_ID}/edit",
        "sheets_write_enabled": sheets_io.sheets_write_enabled(),
        "sa_email": sheets_io.sa_email(),
        "tools": (script_store.load_script().get("tools") or script.CAMPAIGN_TOOLS),
        "script_source": script_store.load_script().get("source"),
    }


def list_results(limit: int = 50) -> dict[str, Any]:
    init_db()
    conn = sqlite3.connect(str(_db_path()))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, sheet_name, gid, row_number, phone, note, status, interest,
                   call_id, written, created_at
            FROM results
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        items = [dict(r) for r in rows]
    finally:
        conn.close()
    return {"ok": True, "total": total, "showing": len(items), "items": items}
