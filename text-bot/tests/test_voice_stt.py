"""Voice STT helpers and business voice parse."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from channels import telegram_business
from voice_stt import extract_voice_file, format_voice_user_text


def test_extract_voice_file():
    msg = {
        "voice": {
            "file_id": "AwACAgIAAxkBAA",
            "duration": 4,
            "mime_type": "audio/ogg",
        }
    }
    v = extract_voice_file(msg)
    assert v is not None
    assert v["file_id"] == "AwACAgIAAxkBAA"
    assert v["kind"] == "voice"


def test_format_voice_user_text():
    t = format_voice_user_text("Нужны выплаты в Сбере", kind="voice")
    assert "[голосовое сообщение]" in t
    assert "Сбере" in t


def test_parse_business_voice_message():
    update = {
        "business_message": {
            "business_connection_id": "conn-voice",
            "chat": {"id": 901, "type": "private"},
            "from": {"id": 902, "is_bot": False},
            "voice": {
                "file_id": "VOICEFILE1",
                "duration": 3,
                "mime_type": "audio/ogg",
            },
        }
    }
    parsed = telegram_business.parse_business_message(update)
    assert parsed is not None
    assert parsed["connection_id"] == "conn-voice"
    assert parsed["text"] == ""
    assert parsed["voice"]["file_id"] == "VOICEFILE1"
    assert parsed["voice"]["kind"] == "voice"
