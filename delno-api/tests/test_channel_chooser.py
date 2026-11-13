"""Telegram/MAX dual-path chooser (bot vs QR)."""

from __future__ import annotations

from app.services import channel_chooser


def test_generic_connect_is_chooser_intent():
    assert channel_chooser.wants_channel_connect_intent("подключи телеграм") == "telegram"
    assert channel_chooser.wants_channel_connect_intent("подключи MAX") == "max"
    assert channel_chooser.explicit_bot_form_kind("подключи телеграм") is None


def test_bot_path_opens_form_kind():
    assert channel_chooser.wants_bot_path("подключи телеграм через бота")
    assert channel_chooser.explicit_bot_form_kind("подключи телеграм через бота") == "telegram_bot"
    assert channel_chooser.explicit_bot_form_kind("подключи MAX через бота") == "max_bot"


def test_qr_and_help_markers():
    assert channel_chooser.wants_qr_path("подключи телеграм через QR")
    assert channel_chooser.wants_bot_help("помоги создать телеграм бота")
    assert not channel_chooser.wants_qr_path("подключи телеграм через бота")


def test_chooser_copy_has_actions():
    tg = channel_chooser.chooser_reply("telegram")
    assert "BotFather" in tg["reply"] or "бота" in tg["reply"].lower()
    assert "QR" in tg["reply"]
    assert len(tg["suggested_actions"]) >= 2
    mx = channel_chooser.chooser_reply("max")
    assert "QR" in mx["reply"]
    assert len(mx["suggested_actions"]) >= 2


def test_bot_help_has_form_kind():
    h = channel_chooser.bot_help_reply("telegram")
    assert h["form_kind"] == "telegram_bot"
    assert "BotFather" in h["reply"] or "@BotFather" in h["reply"]
    h2 = channel_chooser.bot_help_reply("max")
    assert h2["form_kind"] == "max_bot"
