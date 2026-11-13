"""Onboarding templates + telephony script for any tenant."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.onboarding_templates import get_template, list_templates
from app.services.telephony_script import (
    formalize_rough_script,
    propose_script_from_knowledge,
    save_telephony_script,
)


def test_list_templates_includes_blanks():
    items = list_templates(include_examples=True)
    ids = {i["id"] for i in items}
    assert "company-profile" in ids
    assert "telephony-script" in ids


def test_get_company_profile_template_body():
    tpl = get_template("company-profile")
    assert tpl is not None
    assert "Профиль компании" in tpl["body"]
    assert "Название компании" in tpl["body"]


def test_get_telephony_script_template_body():
    tpl = get_template("telephony-script")
    assert tpl is not None
    assert "Сценарий телефонного секретаря" in tpl["body"]
    assert "get_company_knowledge" in tpl["body"]


def test_formalize_rough_script_is_generic():
    out = formalize_rough_script(
        "Мы студия массажа, записываем на сеанс, спрашиваем имя и телефон.",
        company_name="Студия Лён",
    )
    assert "Студия Лён" in out
    assert "Приветствие" in out
    assert "get_company_knowledge" in out
    assert "Quantum" not in out


def test_propose_script_uses_tenant_name():
    db = MagicMock()
    ctx = MagicMock()
    tenant = MagicMock()
    tenant.name = "Ателье Шов"
    tenant.settings = {}
    db.query.return_value.filter.return_value.one.return_value = tenant
    with patch("app.services.telephony_script.get_template") as gt:
        gt.return_value = {"body": "# blank\nТекст первой фразы (одна короткая реплика):\n…\n"}
        out = propose_script_from_knowledge(db, ctx)
    assert out["ok"]
    assert "Ателье Шов" in out["draft"] or "Ателье" in out["company_name"]


def test_save_telephony_script_marks_ready():
    db = MagicMock()
    ctx = MagicMock()
    ctx.tenant_id = "t1"
    tenant = MagicMock()
    tenant.settings = {}
    db.query.return_value.filter.return_value.one.return_value = tenant
    with patch("app.services.telephony_script.upsert_tenant_knowledge_document") as upsert:
        upsert.return_value = {"ok": True}
        with patch("app.services.telephony_script.emit_event"):
            out = save_telephony_script(
                db,
                ctx,
                script="# Сценарий\n\n" + ("ответ на вопросы и запись на встречу. " * 5),
                source="test",
            )
    assert out["ok"]
    assert tenant.settings["hermes"]["telephony_script_ready"] is True
    assert "telephony" in tenant.settings
