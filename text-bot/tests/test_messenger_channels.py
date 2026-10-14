"""Unit tests for messenger channel adapters (parse + ACL guest)."""

from __future__ import annotations

import os

import pytest

from channels import max_messenger, vk, whatsapp
from scenarios import is_owner, role_for


def test_whatsapp_parse_text_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "79001234567",
                                    "type": "text",
                                    "text": {"body": "Какая комиссия?"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    msgs = whatsapp.parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].channel == "whatsapp"
    assert msgs[0].user_id == "79001234567"
    assert "комиссия" in msgs[0].text


def test_whatsapp_verify():
    os.environ["WHATSAPP_VERIFY_TOKEN"] = "secret-verify"
    assert whatsapp.verify_webhook("subscribe", "secret-verify", "12345") == "12345"
    assert whatsapp.verify_webhook("subscribe", "wrong", "12345") is None


def test_max_parse_message_created():
    payload = {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 42},
            "recipient": {"chat_id": 42},
            "body": {"text": "Нужны массовые выплаты"},
        },
    }
    msgs = max_messenger.parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].channel == "max"
    assert msgs[0].user_id == "42"
    assert "выплаты" in msgs[0].text


def test_max_bot_started_becomes_start():
    payload = {
        "update_type": "bot_started",
        "user": {"user_id": 7},
        "chat_id": 7,
    }
    msgs = max_messenger.parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].text == "/start"


def test_vk_confirmation_and_message():
    os.environ["VK_CONFIRMATION_CODE"] = "conf123"
    os.environ["VK_GROUP_TOKEN"] = "tok"
    os.environ["VK_ENABLED"] = "true"
    body, code = vk.handle_callback({"type": "confirmation"}, secretary_handle=lambda **_: {})
    assert code == 200
    assert body == "conf123"

    payload = {
        "type": "message_new",
        "secret": "",
        "object": {
            "message": {
                "from_id": 1001,
                "peer_id": 1001,
                "text": "СБП для ломбарда",
            }
        },
    }
    msgs = vk.parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].channel == "vk"
    assert msgs[0].user_id == "1001"


def test_public_messengers_always_guest(monkeypatch):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "999,79001234567")
    # Force reload owners cache if any
    from scenarios import get_bundle

    get_bundle.cache_clear() if hasattr(get_bundle, "cache_clear") else None
    # re-init bundle
    import scenarios as sc

    sc._BUNDLE = None  # type: ignore[attr-defined]

    assert is_owner("999", "whatsapp") is False
    assert is_owner("999", "max") is False
    assert is_owner("999", "vk") is False
    assert role_for("999", "whatsapp") == "guest"
