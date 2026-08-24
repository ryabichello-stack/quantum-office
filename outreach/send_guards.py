"""Unified send gate: suppression + consent DNC + Account BLACKLISTED."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ava-outreach.send_guards")

BLOCKING_CONSENT = frozenset({"unsubscribed", "bounced", "manual_dnc"})


def check_send_allowed(
    email: str,
    *,
    company_id: str | None = None,
    deliverability: Any | None = None,
) -> tuple[bool, str]:
    """Return (ok, reason). reason empty when ok."""
    em = (email or "").strip().lower()
    if not em or "@" not in em:
        return False, "invalid_email"

    # 1) Deliverability suppression list
    try:
        store = deliverability
        if store is None:
            from modules.deliverability import DeliverabilityStore

            store = DeliverabilityStore()
        reason = store.is_suppressed(em)
        if reason:
            return False, f"suppressed:{reason}"
    except Exception:  # noqa: BLE001
        logger.debug("deliverability check failed", exc_info=True)

    # 2) Consent ledger latest status
    try:
        from modules.consent import ConsentLedgerStore

        latest = ConsentLedgerStore().latest_for_email(em)
        if latest and (latest.get("status") or "") in BLOCKING_CONSENT:
            return False, f"consent:{latest.get('status')}"
    except Exception:  # noqa: BLE001
        logger.debug("consent check failed", exc_info=True)

    # 3) Account lifecycle BLACKLISTED (by bitrix company or person email)
    try:
        from modules.accounts import AccountStore

        acc_store = AccountStore()
        if company_id:
            acc = acc_store.get_account_by_bitrix(str(company_id))
            if acc and (acc.get("lifecycle_status") or "") == "BLACKLISTED":
                return False, "account:BLACKLISTED"
        person = acc_store.find_person_by_email(em)
        if person:
            # any employment account blacklisted?
            with acc_store.connect() as conn:
                row = conn.execute(
                    """
                    SELECT a.lifecycle_status
                    FROM employments e
                    JOIN accounts a ON a.id = e.account_id
                    WHERE e.person_id = ?
                    ORDER BY e.updated_at DESC LIMIT 1
                    """,
                    (person["id"],),
                ).fetchone()
            if row and (row["lifecycle_status"] or "") == "BLACKLISTED":
                return False, "account:BLACKLISTED"
    except Exception:  # noqa: BLE001
        logger.debug("account blacklist check failed", exc_info=True)

    return True, ""
