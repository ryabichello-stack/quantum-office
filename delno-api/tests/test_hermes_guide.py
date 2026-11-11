"""Hermes coach replies without LLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.hermes_guide import coach_reply, llm_unavailable_reply


def test_llm_unavailable_mentions_proxy():
    text = llm_unavailable_reply("расскажи анекдот")
    assert "OPENAI_HTTP_PROXY" in text
    assert "анекдот" in text


def test_coach_phone_setup():
    db = MagicMock()
    ctx = MagicMock()
    with (
        patch("app.services.hermes_guide.phone_provision.list_phones") as phones,
        patch("app.services.hermes_guide.hermes_ops.office_setup_status") as setup,
        patch("app.services.hermes_guide.hermes_ops.office_health_report") as health,
    ):
        phones.return_value = {
            "items": [{"e164": "+79699665899", "label": "main", "status": "active"}]
        }
        setup.return_value = {"message_ru": "Сетап 80%"}
        health.return_value = {"message_ru": "Есть предупреждения"}
        out = coach_reply(db, ctx, "Помоги настроить телефон секретаря")
    assert out is not None
    assert "79699665899" in out["reply"]
    assert "без лишних вопросов" in out["reply"]
    assert out["tool_calls"][0]["tool"] == "hermes.guide.phone"


def test_coach_does_not_steal_calls_list():
    db = MagicMock()
    ctx = MagicMock()
    assert coach_reply(db, ctx, "Какие звонки были сегодня?") is None
