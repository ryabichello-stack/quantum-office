"""List Mailer — отдельная рассылка по спискам на rdv@ (не ava-outreach).

Не использует office@, Bitrix outbox, OUTREACH_ENABLED, OUTREACH_DAILY_LIMIT.
Свои кампании / recipients / sends в SQLite + свои лимиты PARTNER_DAILY_LIMIT.
"""

from __future__ import annotations

__all__ = ["ALLOWED_FROM", "Store", "load_env", "send_pending"]

ALLOWED_FROM = "rdv@quantumlabs.ru"
BLOCKED_FROM = frozenset({"office@quantumlabs.ru"})
