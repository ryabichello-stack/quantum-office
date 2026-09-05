"""E2.4 — MAX adapter webhook parsing."""

from __future__ import annotations

from app.adapters.channels.max import MaxAdapter


def test_max_parse_message_created():
    adapter = MaxAdapter()
    payload = {
        "update_type": "message_created",
        "timestamp": 1710700000000,
        "message": {
            "sender": {"user_id": 12345, "first_name": "Иван", "is_bot": False},
            "recipient": {"chat_id": 67890, "chat_type": "chat"},
            "body": {"mid": "mid.abc123", "text": "Привет!"},
        },
    }
    msgs = adapter.parse_webhook(payload)
    assert len(msgs) == 1
    assert msgs[0].external_user_id == "67890"
    assert msgs[0].text == "Привет!"
    assert msgs[0].display_name == "Иван"


def test_max_parse_ignores_bot_messages():
    adapter = MaxAdapter()
    payload = {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 1, "first_name": "Bot", "is_bot": True},
            "recipient": {"chat_id": 2},
            "body": {"text": "hi"},
        },
    }
    assert adapter.parse_webhook(payload) == []


def test_max_parse_bot_started():
    adapter = MaxAdapter()
    payload = {"update_type": "bot_started", "chat_id": 555, "user": {"name": "Anna"}}
    msgs = adapter.parse_webhook(payload)
    assert len(msgs) == 1
    assert msgs[0].external_user_id == "555"
    assert msgs[0].text == "/start"


def test_max_verify_webhook_secret():
    adapter = MaxAdapter()
    assert adapter.verify_webhook_secret(secret_header="abc", expected_secret="abc")
    assert not adapter.verify_webhook_secret(secret_header="wrong", expected_secret="abc")
