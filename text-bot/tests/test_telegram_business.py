"""Telegram Business connection / message parsing tests."""

from __future__ import annotations

import json
from pathlib import Path

from channels import telegram_business
from scenarios import is_owner, role_for


def test_parse_business_message():
    update = {
        "business_message": {
            "business_connection_id": "conn-1",
            "chat": {"id": 555, "type": "private"},
            "from": {"id": 777, "is_bot": False},
            "text": "Здравствуйте, нужны выплаты",
        }
    }
    parsed = telegram_business.parse_business_message(update)
    assert parsed is not None
    assert parsed["connection_id"] == "conn-1"
    assert parsed["chat_id"] == 555
    assert parsed["user_id"] == "777"
    assert "выплаты" in parsed["text"]


def test_upsert_and_pause(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BUSINESS_OWNER_PAUSE_SECONDS", "60")
    telegram_business._CONNECTIONS.clear()
    telegram_business._PAUSE_UNTIL.clear()
    telegram_business.upsert_connection(
        {
            "id": "bc-abc",
            "user": {"id": 42},
            "user_chat_id": 42,
            "is_enabled": True,
            "can_reply": True,
        }
    )
    assert telegram_business.get_connection("bc-abc")["user_id"] == "42"
    store = Path(tmp_path) / "telegram_business.json"
    assert store.is_file()
    raw = json.loads(store.read_text(encoding="utf-8"))
    assert "bc-abc" in raw["connections"]

    assert telegram_business.is_paused(555) is False
    telegram_business.pause_chat(555)
    assert telegram_business.is_paused(555) is True


def test_business_channel_always_guest():
    assert is_owner("963782", "telegram_business") is False
    assert role_for("963782", "telegram_business") == "guest"
