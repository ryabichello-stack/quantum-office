"""Consent / DNC ledger — audit trail per email beyond suppression list."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.consent")

STATUSES = (
  "allowed",
  "outreach",
  "unsubscribed",
  "bounced",
  "manual_dnc",
  "replied",
  "callback",
)


def _utc_now() -> str:
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ConsentLedgerStore:
  def __init__(self, db_path: Path | None = None) -> None:
    self.db_path = Path(db_path or MODULES_DB)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.init_db()

  @contextmanager
  def connect(self) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    try:
      yield conn
      conn.commit()
    except Exception:
      conn.rollback()
      raise
    finally:
      conn.close()

  def init_db(self) -> None:
    with self.connect() as conn:
      conn.execute(
        """
        CREATE TABLE IF NOT EXISTS consent_ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT NOT NULL,
          company_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT 'system',
          reason TEXT NOT NULL DEFAULT '',
          note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        )
        """
      )
      conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_consent_email ON consent_ledger(lower(email))"
      )
      conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_consent_created ON consent_ledger(created_at DESC)"
      )

  def record(
    self,
    *,
    email: str,
    status: str,
    source: str = "system",
    reason: str = "",
    company_id: str = "",
    note: str = "",
  ) -> dict[str, Any]:
    em = (email or "").strip().lower()
    st = (status or "allowed").strip().lower()
    if not em:
      raise ValueError("email required")
    if st not in STATUSES:
      st = "manual_dnc"
    now = _utc_now()
    with self.connect() as conn:
      cur = conn.execute(
        """
        INSERT INTO consent_ledger(email, company_id, status, source, reason, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (em, (company_id or "").strip(), st, source[:120], reason[:500], note[:1000], now),
      )
      rid = int(cur.lastrowid)
    return self.get(rid) or {}

  def get(self, entry_id: int) -> dict[str, Any] | None:
    with self.connect() as conn:
      row = conn.execute(
        "SELECT * FROM consent_ledger WHERE id = ?", (int(entry_id),)
      ).fetchone()
    return dict(row) if row else None

  def latest_for_email(self, email: str) -> dict[str, Any] | None:
    em = (email or "").strip().lower()
    if not em:
      return None
    with self.connect() as conn:
      row = conn.execute(
        """
        SELECT * FROM consent_ledger
        WHERE lower(email) = lower(?)
        ORDER BY id DESC LIMIT 1
        """,
        (em,),
      ).fetchone()
    return dict(row) if row else None

  def list_entries(
    self,
    *,
    q: str | None = None,
    status: str | None = None,
    limit: int = 80,
    offset: int = 0,
  ) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if q:
      clauses.append("(lower(email) LIKE ? OR lower(reason) LIKE ? OR company_id LIKE ?)")
      like = f"%{q.strip().lower()}%"
      params.extend([like, like, f"%{q.strip()}%"])
    if status:
      clauses.append("status = ?")
      params.append(status.strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    with self.connect() as conn:
      total = conn.execute(
        f"SELECT COUNT(*) AS n FROM consent_ledger {where}", params
      ).fetchone()["n"]
      rows = conn.execute(
        f"""
        SELECT * FROM consent_ledger {where}
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,
        [*params, lim, off],
      ).fetchall()
    return [dict(r) for r in rows], int(total)

  def counts(self) -> dict[str, int]:
    with self.connect() as conn:
      total = int(conn.execute("SELECT COUNT(*) AS n FROM consent_ledger").fetchone()["n"])
      by_status = {
        str(r["status"]): int(r["n"])
        for r in conn.execute(
          "SELECT status, COUNT(*) AS n FROM consent_ledger GROUP BY status"
        ).fetchall()
      }
    return {"total": total, **by_status}

  def import_suppression(self, items: list[dict[str, Any]]) -> int:
    """One-time style backfill from deliverability suppression rows."""
    n = 0
    for row in items:
      email = str(row.get("email") or "").strip()
      if not email:
        continue
      reason = str(row.get("reason") or "suppressed")
      st = "unsubscribed" if "unsub" in reason.lower() else "bounced" if "bounce" in reason.lower() else "manual_dnc"
      if self.latest_for_email(email):
        continue
      self.record(
        email=email,
        status=st,
        source=str(row.get("source") or "suppression_import"),
        reason=reason,
      )
      n += 1
    return n


def record_consent_from_suppression(
  store: ConsentLedgerStore,
  *,
  email: str,
  reason: str,
  source: str = "suppression",
  company_id: str = "",
) -> None:
  rl = reason.lower()
  if "unsub" in rl:
    status = "unsubscribed"
  elif "bounce" in rl:
    status = "bounced"
  else:
    status = "manual_dnc"
  store.record(
    email=email,
    status=status,
    source=source,
    reason=reason,
    company_id=company_id,
  )


class ConsentModule:
  name = "consent"
  version = "1.0.0"

  def __init__(self) -> None:
    self.store = ConsentLedgerStore()

  def init_db(self) -> None:
    self.store.init_db()

  def on_startup(self, ctx: AppContext) -> None:
    ctx.extras["consent"] = self.store
    logger.info("consent module ready %s", self.store.counts())

  def on_shutdown(self) -> None:
    return None

  def health(self) -> dict[str, Any]:
    return {"ok": True, **self.store.counts()}

  def register_routes(self, router: Any) -> None:
    from pydantic import BaseModel, Field

    class ConsentBody(BaseModel):
      email: str
      status: str = "manual_dnc"
      reason: str = ""
      company_id: str = ""
      note: str = ""

    @router.get("/ledger")
    def ledger(
      q: str | None = None,
      status: str | None = None,
      limit: int = 80,
      offset: int = 0,
    ) -> dict[str, Any]:
      items, total = self.store.list_entries(q=q, status=status, limit=limit, offset=offset)
      return {"ok": True, "total": total, "items": items, "counts": self.store.counts()}

    @router.post("/ledger")
    def add_entry(body: ConsentBody) -> dict[str, Any]:
      row = self.store.record(
        email=body.email,
        status=body.status,
        source="ui",
        reason=body.reason,
        company_id=body.company_id,
        note=body.note,
      )
      return {"ok": True, "entry": row}

    @router.post("/import-suppression")
    def import_suppression(limit: int = 500) -> dict[str, Any]:
      from modules.deliverability import DeliverabilityStore

      lim = max(1, min(int(limit or 500), 5000))
      items = DeliverabilityStore().list_suppression(limit=lim)
      n = self.store.import_suppression(items)
      return {"ok": True, "imported": n, "counts": self.store.counts()}
