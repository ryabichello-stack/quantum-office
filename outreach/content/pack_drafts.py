"""Editable pack letter drafts (all chain steps), stored in SQLite.

Base copy lives in ``content.packs.PACKS``. Campaign UI can override the full
letter chain per industry: subject, plain/html, delay, order, attach flag.
Sequences and senders resolve drafts over the code pack.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from content.packs import (
    LEGAL_FOOTER_HTML,
    LEGAL_FOOTER_PLAIN,
    _html_from_plain,
    ensure_legal_footer,
    get_pack,
)


def _normalize_step(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    step_n = int(raw.get("step") or (index + 1))
    delay = int(raw.get("delay_days") if raw.get("delay_days") is not None else 0)
    label = str(raw.get("label") or f"letter_{step_n}").strip() or f"letter_{step_n}"
    subject = str(raw.get("subject") or "").strip()
    plain = str(raw.get("plain") or "").rstrip()
    html = str(raw.get("html") or "").strip()
    attach = bool(raw.get("attach_presentation"))

    if plain and not html:
        html = _html_from_plain(plain).replace("{legal_html}", LEGAL_FOOTER_HTML)
    if plain and "{unsub_url}" not in plain and "Отписаться" not in plain:
        plain = plain.rstrip() + "\n" + LEGAL_FOOTER_PLAIN
    if html:
        plain, html = ensure_legal_footer(plain, html)
        if "{legal_html}" in html:
            html = html.replace("{legal_html}", LEGAL_FOOTER_HTML)

    return {
        "step": step_n,
        "delay_days": max(0, delay),
        "label": label,
        "subject": subject,
        "plain": plain,
        "html": html,
        "attach_presentation": attach,
    }


def normalize_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(steps or []):
        if not isinstance(raw, dict):
            continue
        out.append(_normalize_step(raw, index=i))
    # Re-number steps 1..n in current order; keep relative delays sorted soft-check
    for i, s in enumerate(out):
        s["step"] = i + 1
    return out


class PackDraftStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pack_letter_drafts (
                    pack_id TEXT PRIMARY KEY,
                    steps_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    def get_steps(self, pack_id: str) -> list[dict[str, Any]] | None:
        pid = (pack_id or "").strip().lower()
        if not pid:
            return None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT steps_json FROM pack_letter_drafts WHERE pack_id = ?",
                (pid,),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list) or not data:
            return None
        return normalize_steps(data)

    def save_steps(self, pack_id: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pid = (pack_id or "").strip().lower()
        if not pid:
            raise ValueError("pack_id required")
        normalized = normalize_steps(steps)
        if not normalized:
            raise ValueError("at least one letter required")
        payload = json.dumps(normalized, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pack_letter_drafts(pack_id, steps_json, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(pack_id) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    updated_at = datetime('now')
                """,
                (pid, payload),
            )
            conn.commit()
        return normalized

    def clear(self, pack_id: str) -> bool:
        pid = (pack_id or "").strip().lower()
        if not pid:
            return False
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM pack_letter_drafts WHERE pack_id = ?", (pid,)
            )
            conn.commit()
            return cur.rowcount > 0

    def has_draft(self, pack_id: str) -> bool:
        return self.get_steps(pack_id) is not None


def resolve_pack(
    pack_id: str,
    drafts: PackDraftStore | None = None,
) -> dict[str, Any] | None:
    """Base pack with optional draft steps overlay."""
    pack = get_pack(pack_id)
    if not pack:
        return None
    out = deepcopy(pack)
    if drafts is not None:
        draft_steps = drafts.get_steps(out["id"])
        if draft_steps:
            out["steps"] = draft_steps
            out["has_draft"] = True
        else:
            out["has_draft"] = False
    else:
        out["has_draft"] = False
    return out


def pack_letters_payload(pack: dict[str, Any]) -> dict[str, Any]:
    """API shape: full letter chain + step-1 convenience fields."""
    steps = list(pack.get("steps") or [])
    step1 = steps[0] if steps else {}
    return {
        "pack_id": pack["id"],
        "title": pack.get("title") or "",
        "short": pack.get("short") or "",
        "audience": pack.get("audience") or "",
        "has_draft": bool(pack.get("has_draft")),
        "subject": step1.get("subject") or "",
        "plain": step1.get("plain") or "",
        "html": step1.get("html") or "",
        "attach_presentation_default": bool(pack.get("attach_presentation_default")),
        "presentation": pack.get("presentation")
        or "quantum_payouts_presentation_small.pdf",
        "steps": [
            {
                "step": int(s["step"]),
                "delay_days": int(s["delay_days"]),
                "label": s.get("label") or "",
                "subject": s.get("subject") or "",
                "plain": s.get("plain") or "",
                "html": s.get("html") or "",
                "attach_presentation": bool(s.get("attach_presentation")),
            }
            for s in steps
        ],
    }
