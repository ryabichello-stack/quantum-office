"""Shared mailbox domain caps (mail.ru must not be capped at 2/day)."""

from __future__ import annotations

from unittest.mock import MagicMock

from modules.deliverability import DeliverabilityStore, is_shared_mailbox_domain


def test_mail_ru_is_shared():
    assert is_shared_mailbox_domain("mail.ru") is True
    assert is_shared_mailbox_domain("bk.ru") is True
    assert is_shared_mailbox_domain("yandex.ru") is True
    assert is_shared_mailbox_domain("company-pawn.ru") is False


def test_shared_domain_uses_daily_limit(tmp_path):
    store = DeliverabilityStore(tmp_path / "m.db")
    settings = MagicMock()
    settings.get_bool.return_value = False  # no warmup → effective = configured
    settings.get_int.side_effect = lambda k, d=0: {
        "DOMAIN_DAILY_CAP": 2,
        "DOMAIN_SHARED_DAILY_CAP": 0,
        "COMPANY_DAILY_CAP": 1,
    }.get(k, d)

    # Simulate 5 already sent to mail.ru today
    for _ in range(5):
        store.bump_domain("mail.ru")

    decision = store.decide(
        email="boss@mail.ru",
        settings=settings,
        sent_today=5,
        configured_daily_limit=15,
        company_id="c1",
    )
    assert decision.allow is True
    assert decision.reason == "ok"

    # Corporate domain still hard-capped at 2
    store.bump_domain("acme-lombard.ru")
    store.bump_domain("acme-lombard.ru")
    decision2 = store.decide(
        email="ceo@acme-lombard.ru",
        settings=settings,
        sent_today=5,
        configured_daily_limit=15,
        company_id="c2",
    )
    assert decision2.allow is False
    assert "domain_cap" in decision2.reason
