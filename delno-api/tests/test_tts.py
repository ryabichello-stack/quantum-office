from unittest.mock import patch

from app.services.tts import prepare_tts_text, synthesize_speech


def test_prepare_tts_text():
    assert "дельно" in prepare_tts_text("DELNO отвечает клиентам")


def test_synthesize_speech_not_configured():
    with patch("app.services.tts.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = None
        data, err = synthesize_speech("Привет")
    assert data is None
    assert err == "VOICE_NOT_CONFIGURED"
