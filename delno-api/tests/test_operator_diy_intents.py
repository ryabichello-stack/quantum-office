"""Unit tests for operator DIY intent matchers (no DB)."""

from app.api.v1.operator import (
    _wants_billing_summary,
    _wants_office_health,
    _wants_phones_list,
)


def test_wants_phones_list():
    assert _wants_phones_list("перечисли мои телефонные номера")
    assert _wants_phones_list("покажи номера")
    assert _wants_phones_list("phones.list")
    assert not _wants_phones_list("создай конференцию")


def test_wants_billing_summary():
    assert _wants_billing_summary("покажи баланс биллинга")
    assert _wants_billing_summary("billing.summary")
    assert _wants_billing_summary("сколько токенов осталось")
    assert not _wants_billing_summary("перечисли номера")


def test_wants_office_health_includes_sip_reg():
    assert _wants_office_health("статус офиса")
    assert _wants_office_health("проверь регистрацию SIP")
    assert _wants_office_health("проверь sip")
