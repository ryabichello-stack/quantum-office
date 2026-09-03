"""OpenAI TTS for cabinet Operator voice replies."""

from __future__ import annotations

import httpx

from app.core.config import get_settings

TTS_INSTRUCTIONS = (
    "Говори на чистом естественном русском языке. Спокойный уверенный тон делового помощника. "
    "Название продукта «дельно» произноси по-русски, слитно: дель-но."
)
TTS_VOICE = "cedar"
MAX_TTS_CHARS = 800


def prepare_tts_text(text: str) -> str:
    return (
        text.replace("DELNO", "дельно")
        .replace("Delno", "дельно")
        .replace("delno", "дельно")
        .strip()
    )


def synthesize_speech(text: str) -> tuple[bytes | None, str | None]:
    """Return (mp3_bytes, error_code)."""
    settings = get_settings()
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return None, "VOICE_NOT_CONFIGURED"

    input_text = prepare_tts_text(text[:MAX_TTS_CHARS])
    if not input_text:
        return None, "TEXT_REQUIRED"

    payload = {
        "model": "gpt-4o-mini-tts",
        "voice": TTS_VOICE,
        "speed": 1.0,
        "input": input_text,
        "instructions": TTS_INSTRUCTIONS,
        "response_format": "mp3",
    }

    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError:
        return None, "VOICE_GENERATION_FAILED"

    if response.status_code in (401, 403):
        return None, "VOICE_AUTH_FAILED"
    if response.status_code == 429:
        return None, "VOICE_LIMIT_REACHED"
    if response.status_code != 200:
        return None, "VOICE_GENERATION_FAILED"

    return response.content, None
