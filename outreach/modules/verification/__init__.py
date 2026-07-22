"""Local pre-send email verification (syntax, MX, role-based, history).

No paid provider required. External verifier can plug in later via verify().
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.verification")

_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")

ROLE_LOCALS = frozenset(
    {
        "info",
        "office",
        "mail",
        "admin",
        "administrator",
        "support",
        "help",
        "sales",
        "contact",
        "contacts",
        "noreply",
        "no-reply",
        "donotreply",
        "postmaster",
        "abuse",
        "webmaster",
        "hostmaster",
        "billing",
        "accounting",
        "buh",
        "buch",
        "finance",
        "hr",
        "jobs",
        "marketing",
        "press",
        "pr",
        "director",
        "partner",
        "partners",
        "reception",
        "secretary",
    }
)

# Statuses allowed for automatic send
SEND_OK = frozenset({"valid", "role_based", "unknown"})
SEND_BLOCK = frozenset(
    {
        "invalid_syntax",
        "no_mx",
        "domain_not_found",
        "previous_hard_bounce",
        "suppressed",
        "disposable",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_role_based(email: str) -> bool:
    local = normalize_email(email).split("@", 1)[0]
    local = local.split("+", 1)[0]
    return local in ROLE_LOCALS


def check_mx(domain: str) -> tuple[bool, str]:
    """Return (mx_ok, detail). Tries dnspython, then A-record fallback."""
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return False, "empty_domain"
    try:
        import dns.exception
        import dns.resolver

        try:
            answers = dns.resolver.resolve(domain, "MX")
            if answers:
                return True, f"mx:{len(list(answers))}"
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            pass
        except dns.exception.DNSException as exc:
            logger.debug("mx lookup error %s: %s", domain, exc)
        try:
            answers = dns.resolver.resolve(domain, "A")
            if answers:
                return True, "a_fallback"
        except dns.exception.DNSException:
            return False, "no_mx_or_a"
        return False, "no_mx_or_a"
    except ImportError:
        # Soft-fail without dnspython: treat as unknown (do not block)
        return True, "dns_lib_missing_assume_ok"


@dataclass
class VerificationResult:
    email: str
    status: str
    substatus: str = ""
    mx_exists: bool | None = None
    role_based: bool = False
    risk_score: int = 0
    detail: str = ""
    allow_send: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "email": self.email,
            "status": self.status,
            "substatus": self.substatus,
            "mx_exists": self.mx_exists,
            "role_based": self.role_based,
            "risk_score": self.risk_score,
            "detail": self.detail,
            "allow_send": self.allow_send,
        }


class VerificationStore:
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
                CREATE TABLE IF NOT EXISTS email_verifications (
                    email TEXT PRIMARY KEY,
                    normalized_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    substatus TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT 'local',
                    mx_exists INTEGER,
                    catch_all INTEGER,
                    role_based INTEGER NOT NULL DEFAULT 0,
                    risk_score INTEGER NOT NULL DEFAULT 0,
                    checked_at TEXT NOT NULL,
                    raw_response TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_email_verif_status "
                "ON email_verifications(status)"
            )

    def get(self, email: str) -> dict[str, Any] | None:
        em = normalize_email(email)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_verifications WHERE normalized_email = ?",
                (em,),
            ).fetchone()
        return dict(row) if row else None

    def save(self, result: VerificationResult, *, raw: dict[str, Any] | None = None) -> None:
        em = normalize_email(result.email)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO email_verifications(
                    email, normalized_email, status, substatus, provider,
                    mx_exists, catch_all, role_based, risk_score, checked_at, raw_response
                ) VALUES (?, ?, ?, ?, 'local', ?, NULL, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    normalized_email=excluded.normalized_email,
                    status=excluded.status,
                    substatus=excluded.substatus,
                    mx_exists=excluded.mx_exists,
                    role_based=excluded.role_based,
                    risk_score=excluded.risk_score,
                    checked_at=excluded.checked_at,
                    raw_response=excluded.raw_response
                """,
                (
                    em,
                    em,
                    result.status,
                    result.substatus,
                    1 if result.mx_exists else (0 if result.mx_exists is False else None),
                    1 if result.role_based else 0,
                    int(result.risk_score),
                    _utc_now(),
                    json.dumps(raw or result.to_dict(), ensure_ascii=False),
                ),
            )


def verify_email_local(
    email: str,
    *,
    suppressed_reason: str | None = None,
    previous_hard_bounce: bool = False,
) -> VerificationResult:
    em = normalize_email(email)
    role = is_role_based(em)

    if suppressed_reason:
        return VerificationResult(
            email=em,
            status="suppressed",
            substatus=suppressed_reason,
            role_based=role,
            risk_score=100,
            detail=f"suppressed:{suppressed_reason}",
            allow_send=False,
        )
    if previous_hard_bounce:
        return VerificationResult(
            email=em,
            status="previous_hard_bounce",
            role_based=role,
            risk_score=100,
            detail="hard_bounce_history",
            allow_send=False,
        )
    if not em or "@" not in em or not _EMAIL_RE.match(em):
        return VerificationResult(
            email=em or email,
            status="invalid_syntax",
            role_based=role,
            risk_score=100,
            detail="syntax",
            allow_send=False,
        )

    domain = em.split("@", 1)[1]
    mx_ok, mx_detail = check_mx(domain)
    if not mx_ok:
        return VerificationResult(
            email=em,
            status="no_mx",
            substatus=mx_detail,
            mx_exists=False,
            role_based=role,
            risk_score=90,
            detail=mx_detail,
            allow_send=False,
        )

    if role:
        return VerificationResult(
            email=em,
            status="role_based",
            substatus="b2b_ok",
            mx_exists=True,
            role_based=True,
            risk_score=25,
            detail=mx_detail,
            allow_send=True,
        )

    return VerificationResult(
        email=em,
        status="valid",
        substatus=mx_detail,
        mx_exists=True,
        role_based=False,
        risk_score=10,
        detail=mx_detail,
        allow_send=True,
    )


class VerificationModule:
    name = "verification"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = VerificationStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["verification"] = self.store
        logger.info("verification module ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM email_verifications").fetchone()["n"]
        return {"ok": True, "verified": int(n)}

    def verify(
        self,
        email: str,
        *,
        suppressed_reason: str | None = None,
        previous_hard_bounce: bool = False,
        force: bool = False,
    ) -> VerificationResult:
        em = normalize_email(email)
        if not force:
            cached = self.store.get(em)
            if cached and cached.get("status"):
                status = str(cached["status"])
                return VerificationResult(
                    email=em,
                    status=status,
                    substatus=str(cached.get("substatus") or ""),
                    mx_exists=bool(cached["mx_exists"])
                    if cached.get("mx_exists") is not None
                    else None,
                    role_based=bool(cached.get("role_based")),
                    risk_score=int(cached.get("risk_score") or 0),
                    detail="cached",
                    allow_send=status in SEND_OK,
                )
        result = verify_email_local(
            em,
            suppressed_reason=suppressed_reason,
            previous_hard_bounce=previous_hard_bounce,
        )
        self.store.save(result)
        return result

    def register_routes(self, router: Any) -> None:
        from pydantic import BaseModel

        class Body(BaseModel):
            email: str
            force: bool = False

        @router.post("/check")
        def check(body: Body) -> dict[str, Any]:
            result = self.verify(body.email, force=body.force)
            return {"ok": True, **result.to_dict()}

        @router.get("/status")
        def status(email: str) -> dict[str, Any]:
            row = self.store.get(email)
            return {"ok": True, "item": row}
