"""Per-send tracking: Message-ID chain + optional plus Reply-To + open pixel + bounces.

Mail.ru / custom domain note
----------------------------
Correct plus form is ``office+tag@quantumlabs.ru`` (mailbox BEFORE +).
``au1+office@…`` is wrong — that would be mailbox ``au1``, not ``office``.

Plus delivery to the base mailbox is **not guaranteed** on Mail.ru Business.
We therefore treat Message-ID as the source of truth and use plus Reply-To
only as an optional secondary signal (TRACKING_PLUS_REPLY_TO).

Engagement
----------
- Open: 1×1 HTML pixel at ``TRACKING_PUBLIC_BASE/t/o/{token}.gif``
- Bounce: IMAP DSN / mailer-daemon matched via In-Reply-To → Message-ID
- Delivered: inferred as sent − bounced (no Mail.ru delivery webhook)
"""

from __future__ import annotations

import hashlib
import hmac
import html as html_lib
import logging
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.tracking")

_PLUS_TAG_RE = re.compile(
    r"^([^+@]+)\+(au|unsub)\.([a-zA-Z0-9_-]+)\.([a-f0-9]{6,16})@",
    re.IGNORECASE,
)

PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01"
    b"\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def tracking_secret() -> str:
    secret = (os.getenv("TRACKING_HMAC_SECRET") or "").strip()
    if secret:
        return secret
    ui = (os.getenv("OUTREACH_UI_TOKEN") or "").strip()
    if ui:
        return hashlib.sha256(f"outreach-tracking:{ui}".encode()).hexdigest()
    secret = secrets.token_hex(16)
    os.environ["TRACKING_HMAC_SECRET"] = secret
    return secret


def short_hmac(payload: str, *, n: int = 8) -> str:
    dig = hmac.new(
        tracking_secret().encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return dig[:n]


def open_tracking_enabled(settings: Any = None) -> bool:
    if settings is not None:
        return bool(settings.get_bool("OPEN_TRACKING_ENABLED", True))
    return os.getenv("OPEN_TRACKING_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def tracking_public_base(settings: Any = None) -> str:
    if settings is not None:
        base = settings.get("TRACKING_PUBLIC_BASE") or ""
    else:
        base = os.getenv("TRACKING_PUBLIC_BASE", "")
    base = (base or "https://a.47z.ru/_ava_outreach").strip().rstrip("/")
    return base


def new_open_token() -> str:
    return secrets.token_urlsafe(18)


def make_unsubscribe_token(*, outbox_id: int, email: str) -> str:
    """Stable signed token: {outbox_id}.{hmac} — outbox id only in URL."""
    em = (email or "").strip().lower()
    sig = short_hmac(f"unsub:{int(outbox_id)}:{em}", n=10)
    return f"{int(outbox_id)}.{sig}"


def parse_unsubscribe_token(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if "." not in raw:
        return None
    oid_s, _sig = raw.split(".", 1)
    try:
        oid = int(oid_s)
    except ValueError:
        return None
    return {"outbox_id": oid, "token": raw}


def verify_unsubscribe_token(token: str, *, email: str) -> bool:
    parsed = parse_unsubscribe_token(token)
    if not parsed:
        return False
    expected = make_unsubscribe_token(outbox_id=parsed["outbox_id"], email=email)
    return hmac.compare_digest(expected, parsed["token"])


def unsubscribe_url_for(token: str, settings: Any = None) -> str:
    return f"{tracking_public_base(settings)}/unsubscribe/{token}"


def open_pixel_url(token: str, settings: Any = None) -> str:
    return f"{tracking_public_base(settings)}/t/o/{quote(token)}.gif"


def inject_open_pixel(html_body: str, token: str, settings: Any = None) -> str:
    """Append a 1×1 tracking pixel before </body> (or at end)."""
    if not token or not open_tracking_enabled(settings):
        return html_body
    url = html_lib.escape(open_pixel_url(token, settings), quote=True)
    pixel = (
        f'<img src="{url}" width="1" height="1" alt="" '
        f'style="display:block;width:1px;height:1px;border:0;" />'
    )
    lower = html_body.lower()
    idx = lower.rfind("</body>")
    if idx >= 0:
        return html_body[:idx] + pixel + html_body[idx:]
    return html_body + pixel


def build_plus_address(
    *,
    mailbox: str,
    kind: str,
    outbox_id: int,
    company_slug: str | None = None,
) -> str:
    """Build ``office+au.<slug>.<id>.<hmac>@domain`` (slug optional).

    Example: ``office+lombard-sever.42.a1b2c3d4@quantumlabs.ru``
    Legacy without slug still supported by ``parse_plus_address``.
    """
    mailbox = mailbox.strip()
    if "@" not in mailbox:
        raise ValueError("mailbox must be a full email")
    local, domain = mailbox.split("@", 1)
    local = local.split("+", 1)[0]
    sig = short_hmac(f"{kind}:{outbox_id}")
    slug = plus_company_slug(company_slug)
    if slug:
        return f"{local}+{kind}.{slug}.{outbox_id}.{sig}@{domain}"
    return f"{local}+{kind}.{outbox_id}.{sig}@{domain}"


_TRANSLIT = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


def plus_company_slug(raw: str | None, *, max_len: int = 28) -> str:
    """ASCII slug for plus-address readability (company / contact / domain)."""
    s = (raw or "").strip().lower()
    if not s:
        return ""
    if "@" in s:
        # recipient email → domain label
        domain = s.split("@", 1)[1]
        s = domain.split(".")[0]
    s = s.translate(_TRANSLIT)
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif ch in (" ", "-", "_", ".", "/"):
            if out and not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug[:max_len].strip("-")


def parse_plus_address(addr: str) -> dict[str, Any] | None:
    """Parse ``local+au[.slug].<id>.<sig>@domain`` (slug optional)."""
    addr = (addr or "").strip().lower()
    if "@" not in addr or "+" not in addr.split("@", 1)[0]:
        return None
    local, domain = addr.split("@", 1)
    base, _, rest = local.partition("+")
    parts = rest.split(".")
    if len(parts) < 3 or parts[0] not in ("au", "unsub"):
        return None
    kind = parts[0]
    if len(parts) >= 4 and parts[-2].isdigit():
        oid_s, sig = parts[-2], parts[-1]
        slug = ".".join(parts[1:-2]) or None
    elif parts[1].isdigit():
        oid_s, sig = parts[1], parts[2]
        slug = None
    else:
        return None
    try:
        outbox_id = int(oid_s)
    except ValueError:
        return None
    return {
        "mailbox": f"{base}@{domain}",
        "kind": kind,
        "outbox_id": outbox_id,
        "company_slug": slug,
        "sig": sig,
        "valid_sig": hmac.compare_digest(sig, short_hmac(f"{kind}:{outbox_id}")),
    }


@dataclass
class SendEvent:
    id: int
    outbox_id: int
    email: str
    message_id: str
    reply_to: str | None
    plus_tag: str | None
    subject: str | None
    created_at: str
    open_token: str | None = None
    opened_at: str | None = None
    open_count: int = 0
    bounced_at: str | None = None
    bounce_reason: str | None = None
    delivery_status: str = "sent"
    replied_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrackingStore:
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
                CREATE TABLE IF NOT EXISTS send_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    outbox_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    message_id TEXT NOT NULL UNIQUE,
                    reply_to TEXT,
                    plus_tag TEXT,
                    subject TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(send_events)").fetchall()}
            migrations = {
                "open_token": "ALTER TABLE send_events ADD COLUMN open_token TEXT",
                "opened_at": "ALTER TABLE send_events ADD COLUMN opened_at TEXT",
                "open_count": (
                    "ALTER TABLE send_events ADD COLUMN open_count INTEGER NOT NULL DEFAULT 0"
                ),
                "bounced_at": "ALTER TABLE send_events ADD COLUMN bounced_at TEXT",
                "bounce_reason": "ALTER TABLE send_events ADD COLUMN bounce_reason TEXT",
                "delivery_status": (
                    "ALTER TABLE send_events ADD COLUMN delivery_status "
                    "TEXT NOT NULL DEFAULT 'sent'"
                ),
                "replied_at": "ALTER TABLE send_events ADD COLUMN replied_at TEXT",
                "unsub_token": "ALTER TABLE send_events ADD COLUMN unsub_token TEXT",
            }
            for name, sql in migrations.items():
                if name not in cols:
                    conn.execute(sql)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_send_events_outbox ON send_events(outbox_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_send_events_plus ON send_events(plus_tag)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_send_events_open_token "
                "ON send_events(open_token) WHERE open_token IS NOT NULL"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_send_events_unsub_token "
                "ON send_events(unsub_token) WHERE unsub_token IS NOT NULL"
            )

    def record(
        self,
        *,
        outbox_id: int,
        email: str,
        message_id: str,
        reply_to: str | None,
        plus_tag: str | None,
        subject: str | None,
        open_token: str | None = None,
        unsub_token: str | None = None,
    ) -> int:
        mid = message_id.strip().strip("<>").lower()
        now = _utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO send_events
                  (outbox_id, email, message_id, reply_to, plus_tag, subject, created_at,
                   open_token, unsub_token, delivery_status, open_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sent', 0)
                ON CONFLICT(message_id) DO UPDATE SET
                  outbox_id=excluded.outbox_id,
                  email=excluded.email,
                  reply_to=excluded.reply_to,
                  plus_tag=excluded.plus_tag,
                  subject=excluded.subject,
                  open_token=COALESCE(excluded.open_token, send_events.open_token),
                  unsub_token=COALESCE(excluded.unsub_token, send_events.unsub_token),
                  delivery_status=CASE
                    WHEN send_events.delivery_status IN ('bounced', 'opened', 'replied')
                    THEN send_events.delivery_status
                    ELSE 'sent'
                  END
                """,
                (
                    outbox_id,
                    email.lower(),
                    mid,
                    reply_to,
                    plus_tag,
                    subject,
                    now,
                    open_token,
                    unsub_token,
                ),
            )
            return int(cur.lastrowid)

    def by_unsub_token(self, token: str) -> SendEvent | None:
        t = (token or "").strip()
        if not t:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM send_events WHERE unsub_token = ?", (t,)
            ).fetchone()
        return self._row(row) if row else None

    def by_message_id(self, message_id: str) -> SendEvent | None:
        mid = message_id.strip().strip("<>").lower()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM send_events WHERE message_id = ?", (mid,)
            ).fetchone()
        return self._row(row) if row else None

    def by_open_token(self, token: str) -> SendEvent | None:
        t = (token or "").strip()
        if not t:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM send_events WHERE open_token = ?", (t,)
            ).fetchone()
        return self._row(row) if row else None

    def by_plus_tag(self, plus_tag: str) -> SendEvent | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM send_events WHERE plus_tag = ? ORDER BY id DESC LIMIT 1",
                (plus_tag,),
            ).fetchone()
        return self._row(row) if row else None

    def by_outbox_id(self, outbox_id: int) -> list[SendEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM send_events WHERE outbox_id = ? ORDER BY id DESC",
                (outbox_id,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def recent(self, limit: int = 50) -> list[SendEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM send_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def record_open(self, token: str) -> bool:
        event = self.by_open_token(token)
        if not event:
            return False
        now = _utc_now()
        with self.connect() as conn:
            if event.opened_at:
                conn.execute(
                    "UPDATE send_events SET open_count = COALESCE(open_count, 0) + 1 WHERE id = ?",
                    (event.id,),
                )
            else:
                conn.execute(
                    """
                    UPDATE send_events
                    SET opened_at = ?,
                        open_count = COALESCE(open_count, 0) + 1,
                        delivery_status = CASE
                          WHEN delivery_status IN ('bounced', 'replied') THEN delivery_status
                          ELSE 'opened'
                        END
                    WHERE id = ?
                    """,
                    (now, event.id),
                )
        return True

    def record_bounce(self, send_event_id: int, *, reason: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE send_events
                SET bounced_at = COALESCE(bounced_at, ?),
                    bounce_reason = COALESCE(?, bounce_reason),
                    delivery_status = 'bounced'
                WHERE id = ?
                """,
                (_utc_now(), (reason or "")[:500] or None, send_event_id),
            )

    def mark_replied(self, send_event_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE send_events
                SET replied_at = COALESCE(replied_at, ?),
                    delivery_status = CASE
                      WHEN delivery_status = 'bounced' THEN delivery_status
                      ELSE 'replied'
                    END
                WHERE id = ?
                """,
                (_utc_now(), send_event_id),
            )

    def engagement_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            sent = int(conn.execute("SELECT COUNT(*) AS n FROM send_events").fetchone()["n"])
            opened = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM send_events WHERE opened_at IS NOT NULL"
                ).fetchone()["n"]
            )
            bounced = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM send_events WHERE bounced_at IS NOT NULL"
                ).fetchone()["n"]
            )
            replied = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM send_events WHERE replied_at IS NOT NULL"
                ).fetchone()["n"]
            )
        delivered = max(0, sent - bounced)
        return {
            "send_events": sent,
            "sent": sent,
            "delivered": delivered,
            "not_delivered": bounced,
            "opened": opened,
            "not_opened": max(0, delivered - opened),
            "bounced": bounced,
            "replied": replied,
        }

    def counts(self) -> dict[str, int]:
        return self.engagement_counts()

    def daily_series(self, days: int = 14) -> list[dict[str, Any]]:
        from datetime import timedelta

        days = max(1, min(90, int(days)))
        start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
        buckets: dict[str, dict[str, int]] = {}
        for i in range(days):
            d = (start + timedelta(days=i)).isoformat()
            buckets[d] = {"day": d, "sent": 0, "opened": 0, "bounced": 0, "replied": 0}

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, opened_at, bounced_at, replied_at
                FROM send_events
                WHERE created_at >= ?
                """,
                (start.isoformat(),),
            ).fetchall()

        def day_of(val: str | None) -> str | None:
            return str(val)[:10] if val else None

        for row in rows:
            sd = day_of(row["created_at"])
            if sd and sd in buckets:
                buckets[sd]["sent"] += 1
            od = day_of(row["opened_at"])
            if od and od in buckets:
                buckets[od]["opened"] += 1
            bd = day_of(row["bounced_at"])
            if bd and bd in buckets:
                buckets[bd]["bounced"] += 1
            rd = day_of(row["replied_at"])
            if rd and rd in buckets:
                buckets[rd]["replied"] += 1
        return [buckets[k] for k in sorted(buckets.keys())]

    def _row(self, r: sqlite3.Row) -> SendEvent:
        keys = r.keys()
        return SendEvent(
            id=int(r["id"]),
            outbox_id=int(r["outbox_id"]),
            email=str(r["email"]),
            message_id=str(r["message_id"]),
            reply_to=r["reply_to"],
            plus_tag=r["plus_tag"],
            subject=r["subject"],
            created_at=str(r["created_at"]),
            open_token=r["open_token"] if "open_token" in keys else None,
            opened_at=r["opened_at"] if "opened_at" in keys else None,
            open_count=int(r["open_count"] or 0) if "open_count" in keys else 0,
            bounced_at=r["bounced_at"] if "bounced_at" in keys else None,
            bounce_reason=r["bounce_reason"] if "bounce_reason" in keys else None,
            delivery_status=(
                str(r["delivery_status"] or "sent") if "delivery_status" in keys else "sent"
            ),
            replied_at=r["replied_at"] if "replied_at" in keys else None,
        )


class TrackingModule:
    name = "tracking"
    version = "1.1.0"

    def __init__(self) -> None:
        self.store = TrackingStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["tracking"] = self.store
        logger.info("tracking module ready events=%s", self.store.counts())

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            **self.store.counts(),
            "open_tracking": open_tracking_enabled(),
            "tracking_public_base": tracking_public_base(),
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException

        @router.get("/events")
        def list_events(limit: int = 50) -> dict[str, Any]:
            items = self.store.recent(limit=max(1, min(limit, 200)))
            return {
                "ok": True,
                "items": [item.to_dict() for item in items],
                "note": (
                    "Plus Reply-To format: office+au.<id>.<sig>@domain "
                    "(NOT au+office@). Message-ID is primary chain key. "
                    "Opens via HTML pixel; delivery inferred as sent−bounce."
                ),
            }

        @router.get("/resolve")
        def resolve(q: str) -> dict[str, Any]:
            q = (q or "").strip()
            if not q:
                raise HTTPException(400, "q required")
            if "@" in q and "+" in q.split("@", 1)[0]:
                parsed = parse_plus_address(q)
                event = None
                if parsed and parsed.get("valid_sig"):
                    event = self.store.by_outbox_id(parsed["outbox_id"])
                return {
                    "ok": True,
                    "parsed_plus": parsed,
                    "events": [e.to_dict() for e in (event or [])],
                }
            ev = self.store.by_message_id(q)
            return {"ok": True, "event": ev.to_dict() if ev else None}

        @router.post("/preview-plus")
        def preview_plus(outbox_id: int = 1, mailbox: str | None = None) -> dict[str, Any]:
            return preview_plus_payload(outbox_id=max(1, outbox_id), mailbox=mailbox)


def build_tracking_headers(
    *,
    outbox_id: int,
    mailbox: str,
    enable_plus_reply_to: bool,
    company_slug: str | None = None,
) -> dict[str, str]:
    """Return reply_to / list_unsub / plus_tag for one send."""
    slug = plus_company_slug(company_slug)
    plus_tag = (
        f"au.{slug}.{outbox_id}.{short_hmac(f'au:{outbox_id}')}"
        if slug
        else f"au.{outbox_id}.{short_hmac(f'au:{outbox_id}')}"
    )
    out: dict[str, str] = {"plus_tag": plus_tag}
    if enable_plus_reply_to:
        reply = build_plus_address(
            mailbox=mailbox,
            kind="au",
            outbox_id=outbox_id,
            company_slug=slug or None,
        )
        unsub = build_plus_address(
            mailbox=mailbox,
            kind="unsub",
            outbox_id=outbox_id,
            company_slug=slug or None,
        )
        out["reply_to"] = reply
        out["unsubscribe_mailto"] = unsub
    return out


def preview_plus_payload(*, outbox_id: int, mailbox: str | None = None) -> dict[str, Any]:
    box = (mailbox or os.getenv("MAIL_USERNAME") or "office@quantumlabs.ru").strip()
    reply = build_plus_address(
        mailbox=box, kind="au", outbox_id=outbox_id, company_slug="example-co"
    )
    unsub = build_plus_address(
        mailbox=box, kind="unsub", outbox_id=outbox_id, company_slug="example-co"
    )
    return {
        "ok": True,
        "reply_to": reply,
        "unsubscribe_mailto": f"mailto:{unsub}?subject={quote('unsubscribe')}",
        "wrong_example": "au1+office@quantumlabs.ru  ← не использовать",
        "right_example": reply,
        "format": "office+au.<company-slug>.<outbox_id>.<sig>@quantumlabs.ru",
        "mailru_note": (
            "Mail.ru Business may not deliver plus aliases to the base inbox. "
            "We always store Message-ID as primary match; plus Reply-To is a secondary signal."
        ),
    }
