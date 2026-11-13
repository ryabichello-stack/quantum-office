"""DIY credentials.open_form fast-path — PRODUCT_LOOP vault forms in cabinet."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.api.v1.operator import _credential_form_kind_from_message, operator_chat
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult


def test_kind_from_explicit_mango_sip():
    assert (
        _credential_form_kind_from_message(
            "Открой безопасную форму credentials.open_form для mango_sip"
        )
        == "mango_sip"
    )


def test_kind_from_yadisk():
    assert _credential_form_kind_from_message("открой форму для Яндекс.Диска") == "files_yadisk"


def test_kind_open_form_uses_setup_next_phone():
    assert (
        _credential_form_kind_from_message("открой credentials.open_form", setup_next_id="phone")
        == "mango_sip"
    )


def test_kind_open_form_without_kind_or_setup_next_is_none():
    # Do not guess a vault — owner must name the connector or be on a mapped step.
    assert _credential_form_kind_from_message("открой credentials.open_form") is None


def test_kind_phone_step_sip_intent():
    assert (
        _credential_form_kind_from_message(
            "настрой телефонную линию SIP", setup_next_id="phone", setup_substep="need_sip"
        )
        == "mango_sip"
    )


def test_kind_phone_need_did_does_not_auto_open_sip_form():
    assert (
        _credential_form_kind_from_message(
            "подключи DID на телефонную линию",
            setup_next_id="phone",
            setup_substep="need_did",
        )
        is None
    )


def test_kind_phone_step_does_not_steal_calendar_intent():
    # Over-broad «подключ» previously opened mango_sip incorrectly.
    assert _credential_form_kind_from_message("подключи календарь", setup_next_id="phone") is None


def test_kind_post_save_followup_does_not_reopen_form():
    # HermesStage follow-up after vault save must reach Hermes, not DIY form loop.
    assert (
        _credential_form_kind_from_message(
            "SIP сохранён. Проверь регистрацию. Если Rejected — дай задание для Cursor или снова форму.",
            setup_next_id="phone",
        )
        is None
    )
    assert (
        _credential_form_kind_from_message(
            "SIP сохранён и линия Registered. Что дальше — тестовый звонок или сменить голос?",
            setup_next_id="phone",
        )
        is None
    )


def test_operator_chat_diy_opens_pending_credential_form():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()
    body = MagicMock()
    body.message = "Открой безопасную форму credentials.open_form для mango_sip"
    body.attachments = None
    body.modality = "text"
    body.channel = "hermes"
    body.conversation_id = None

    form = {"kind": "mango_sip", "title": "SIP Mango", "fields": []}
    loop = {
        "ok": True,
        "phase": "connectors",
        "setup_next": {"id": "phone", "title": "Телефония", "hint": "DID + SIP"},
        "kb_ok": True,
    }

    with patch(
        "app.services.hermes_nous.onboarding.get_office_loop",
        return_value=loop,
    ), patch(
        "app.api.v1.operator.register_builtin_tools",
        create=True,
    ), patch(
        "app.operator.tools.register_builtin_tools",
    ), patch(
        "app.operator.tools.registry.registry"
    ) as mock_registry:
        mock_registry.run.return_value = ToolResult(
            ok=True,
            data={"pending_credential_form": form, "kind": "mango_sip"},
            message="Открыл безопасную форму «SIP Mango».",
        )
        out = operator_chat(body, db=db, ctx=ctx)

    assert out["engine"] == "diy_credential_form"
    assert out["pending_credential_form"]["kind"] == "mango_sip"
    assert out["office_loop"]["setup_next"]["id"] == "phone"
    mock_registry.run.assert_called_once_with(db, ctx, "credentials.open_form", kind="mango_sip")
