"""Hermes coach replies without LLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.hermes_guide import coach_reply, llm_unavailable_reply


def test_llm_unavailable_mentions_proxy():
    text = llm_unavailable_reply("расскажи анекдот")
    assert "OPENAI_HTTP_PROXY" in text
    assert "анекдот" in text


def test_coach_phone_setup_asks_form_when_sip_missing():
    db = MagicMock()
    ctx = MagicMock()
    with (
        patch("app.services.hermes_guide.phone_provision.list_phones") as phones,
        patch("app.services.hermes_guide.hermes_ops.office_setup_status") as setup,
        patch("app.services.hermes_guide.hermes_ops.office_health_report") as health,
        patch("app.services.hermes_guide.list_secret_status") as secrets,
        patch("app.services.sip_probe.probe_registration") as probe,
    ):
        phones.return_value = {
            "items": [{"e164": "+79699665899", "label": "main", "status": "active"}]
        }
        setup.return_value = {"message_ru": "Сетап 80%"}
        health.return_value = {"message_ru": "Есть предупреждения"}
        secrets.return_value = {"items": [{"kind": "mango_sip", "configured": False}]}
        probe.return_value = {"ok": False, "status": "rejected", "message_ru": "Rejected"}
        out = coach_reply(db, ctx, "Помоги настроить телефон секретаря")
    assert out is not None
    assert "79699665899" in out["reply"]
    assert "без лишних вопросов" in out["reply"]
    assert out.get("pending_credential_form")
    assert out["tool_calls"][0]["tool"] == "hermes.guide.phone"


def test_coach_phone_status_does_not_loop_when_sip_saved():
    db = MagicMock()
    ctx = MagicMock()
    with (
        patch("app.services.hermes_guide.phone_provision.list_phones") as phones,
        patch("app.services.hermes_guide.hermes_ops.office_setup_status") as setup,
        patch("app.services.hermes_guide.hermes_ops.office_health_report") as health,
        patch("app.services.hermes_guide.list_secret_status") as secrets,
        patch("app.services.sip_probe.probe_registration") as probe,
    ):
        phones.return_value = {
            "items": [{"e164": "+79699665899", "label": "main", "status": "active"}]
        }
        setup.return_value = {"message_ru": "Сетап почти готов"}
        health.return_value = {"message_ru": "Есть предупреждения"}
        secrets.return_value = {
            "items": [
                {
                    "kind": "mango_sip",
                    "configured": True,
                    "login_masked": "ga***k",
                    "updated_at": "2026-11-12T15:39:39Z",
                }
            ]
        }
        probe.return_value = {"ok": False, "status": "rejected", "message_ru": "Rejected"}
        out = coach_reply(db, ctx, "Телефон уже настроен?")
    assert out is not None
    assert "не начинаю настройку заново" in out["reply"].lower() or "уже сохранён" in out["reply"]
    assert out.get("pending_credential_form") is None
    assert "неполн" in out["reply"].lower()  # login looks partial (no slash)


def test_coach_does_not_steal_calls_list():
    db = MagicMock()
    ctx = MagicMock()
    assert coach_reply(db, ctx, "Какие звонки были сегодня?") is None


def test_coach_lost_user_steps():
    db = MagicMock()
    ctx = MagicMock()
    with (
        patch("app.services.hermes_guide.phone_provision.list_phones") as phones,
        patch("app.services.hermes_guide.hermes_ops.office_setup_status") as setup,
        patch("app.services.hermes_guide.list_secret_status") as secrets,
        patch("app.services.sip_probe.probe_registration") as probe,
        patch("app.services.telephony_script.get_telephony_config") as tel,
    ):
        phones.return_value = {"items": [{"e164": "+79699665899", "status": "active"}]}
        setup.return_value = {
            "next_steps": [{"id": "telegram", "title": "Telegram", "hint": "токен"}],
            "checks": {"kb": {"ok": False}},
        }
        secrets.return_value = {"items": [{"kind": "mango_sip", "configured": False}]}
        probe.return_value = {"ok": False, "status": "rejected"}
        tel.return_value = {"configured": False, "tools": []}
        out = coach_reply(db, ctx, "Я ничего не понимаю, скажи что нужно делать")
    assert out is not None
    assert "по порядку" in out["reply"].lower() or "шаг" in out["reply"].lower()
    assert "сценарий" in out["reply"].lower()
    assert out.get("pending_credential_form")


def test_coach_offers_blank_template():
    db = MagicMock()
    ctx = MagicMock()
    with patch("app.services.telephony_script.get_telephony_config") as tel:
        tel.return_value = {"configured": False, "tools": []}
        out = coach_reply(db, ctx, "Дай шаблон профиля компании")
    assert out is not None
    assert "Профиль компании" in out["reply"]
    assert "Название компании" in out["reply"]


def test_setup_status_starts_with_company_not_telegram():
    db = MagicMock()
    ctx = MagicMock()
    with patch("app.services.hermes_guide.hermes_ops.office_setup_status") as setup:
        setup.return_value = {
            "message_ru": "Давайте настроим офис. Следующий шаг: Telegram.",
            "checks": {"kb": {"ok": False}},
            "next_steps": [{"id": "telegram", "title": "Telegram", "hint": "токен"}],
        }
        out = coach_reply(
            db,
            ctx,
            "Я владелец офиса. Покажи статус сетапа и скажи, что сделать следующим шагом.",
        )
    assert out is not None
    assert "компани" in out["reply"].lower()
    assert out["reply"].lower().startswith("сначала") or "сначала мне нужно" in out["reply"].lower()
    assert "Подключите branded bot token" not in out["reply"]
    assert out.get("pending_download") or any(
        isinstance(t, dict) and t.get("pending_download") for t in (out.get("tool_calls") or [])
    )


def test_coach_proposes_generic_script():
    db = MagicMock()
    ctx = MagicMock()
    tenant = MagicMock()
    tenant.name = "Новая Компания"
    tenant.settings = {}
    db.query.return_value.filter.return_value.one.return_value = tenant
    with (
        patch("app.services.telephony_script.get_telephony_config") as tel,
        patch("app.services.telephony_script.get_template") as gt,
    ):
        tel.return_value = {"configured": False, "tools": []}
        gt.return_value = {"body": "# Сценарий\nТекст первой фразы (одна короткая реплика):\n…\n"}
        out = coach_reply(db, ctx, "Предложи сценарий из базы знаний")
    assert out is not None
    assert "черновик" in out["reply"].lower() or "сценари" in out["reply"].lower()
    assert "Quantum Labs" not in out["reply"]
