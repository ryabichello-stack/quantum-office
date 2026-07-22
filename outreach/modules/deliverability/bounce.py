"""Bounce / DSN classification helpers (hard / soft / policy / unknown)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class BounceClass:
    category: str  # hard | soft | policy | auth | unknown
    code: str = ""
    suppress: bool = False
    retry: bool = False
    pause_mailbox: bool = False
    reason: str = ""


_STATUS_RE = re.compile(
    r"(?:status[=:\s]+)?([245]\.\d{1,3}\.\d{1,3})",
    re.IGNORECASE,
)
_SMTP_RE = re.compile(r"\b([245]\d{2})\b")


def _extract_codes(text: str) -> tuple[str, str]:
    enhanced = ""
    smtp = ""
    m = _STATUS_RE.search(text or "")
    if m:
        enhanced = m.group(1)
    m2 = _SMTP_RE.search(text or "")
    if m2:
        smtp = m2.group(1)
    return enhanced, smtp


def classify_bounce(raw: str | None) -> BounceClass:
    """Classify bounce text / DSN into actionable category."""
    text = (raw or "").strip()
    low = text.lower()
    enhanced, smtp = _extract_codes(text)

    # Policy / spam blocks first (still pause mailbox)
    if any(
        k in low
        for k in (
            "spam",
            "blocked",
            "blacklist",
            "policy",
            "rejected by",
            "reputation",
        )
    ) and not any(k in low for k in ("user unknown", "does not exist", "no such")):
        return BounceClass(
            "policy",
            code=enhanced or smtp or "",
            suppress=False,
            retry=False,
            pause_mailbox=True,
            reason="policy_or_spam_block",
        )

    # Authentication failures
    if (
        enhanced.startswith("5.7.26")
        or "5.7.26" in low
        or ("authentication" in low and "fail" in low)
        or "dmarc" in low
        or "dkim" in low and "fail" in low
    ):
        return BounceClass(
            "auth",
            code=enhanced or smtp or "5.7",
            suppress=False,
            retry=False,
            pause_mailbox=True,
            reason="authentication_or_policy_auth",
        )
    if enhanced.startswith("5.7."):
        return BounceClass(
            "policy",
            code=enhanced or smtp or "5.7",
            suppress=False,
            retry=False,
            pause_mailbox=True,
            reason="policy_5_7",
        )

    # Hard / permanent recipient
    hard_markers = (
        "user unknown",
        "unknown user",
        "does not exist",
        "no such user",
        "no such mailbox",
        "invalid recipient",
        "recipient rejected",
        "mailbox unavailable",
        "address rejected",
        "5.1.1",
        "5.1.2",
        "5.1.3",
        "550 5.1",
        "551 ",
        "553 ",
    )
    if enhanced.startswith("5.1.") or any(k in low for k in hard_markers):
        return BounceClass(
            "hard",
            code=enhanced or smtp or "5.1.1",
            suppress=True,
            retry=False,
            pause_mailbox=False,
            reason="invalid_recipient",
        )

    # Soft / temporary
    soft_markers = (
        "mailbox full",
        "over quota",
        "try again",
        "temporarily",
        "temporary",
        "4.2.2",
        "4.4.",
        "4.7.",
        "421 ",
        "450 ",
        "451 ",
        "452 ",
        "rate limit",
        "too many",
    )
    if enhanced.startswith("4.") or (smtp.startswith("4") if smtp else False):
        return BounceClass(
            "soft",
            code=enhanced or smtp,
            suppress=False,
            retry=True,
            pause_mailbox=False,
            reason="temporary_failure",
        )
    if any(k in low for k in soft_markers):
        return BounceClass(
            "soft",
            code=enhanced or smtp,
            suppress=False,
            retry=True,
            pause_mailbox=False,
            reason="temporary_failure",
        )

    # Generic 5.x → treat as hard for safety of primary domain
    if enhanced.startswith("5.") or (smtp.startswith("5") if smtp else False):
        return BounceClass(
            "hard",
            code=enhanced or smtp,
            suppress=True,
            retry=False,
            pause_mailbox=False,
            reason="permanent_unknown_5xx",
        )

    return BounceClass(
        "unknown",
        code=enhanced or smtp,
        suppress=True,  # conservative on primary corporate domain
        retry=False,
        pause_mailbox=False,
        reason="unknown_bounce",
    )
