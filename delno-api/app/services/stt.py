"""OpenAI Whisper STT for Hermes mic (server-side fallback)."""

from __future__ import annotations

import httpx

from app.core.config import get_settings


def transcribe_audio(audio_bytes: bytes, *, filename: str = "audio.webm") -> tuple[str | None, str | None]:
    """Return (text, error_code)."""
    settings = get_settings()
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return None, "STT_NOT_CONFIGURED"
    if not audio_bytes:
        return None, "AUDIO_REQUIRED"
    if len(audio_bytes) > 25 * 1024 * 1024:
        return None, "AUDIO_TOO_LARGE"

    try:
        from app.services.openai_http import openai_client, openai_url

        with openai_client(timeout=60.0) as client:
            response = client.post(
                openai_url("/audio/transcriptions"),
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_bytes, "application/octet-stream")},
                data={"model": "whisper-1", "language": "ru"},
            )
    except httpx.HTTPError:
        return None, "STT_FAILED"

    if response.status_code in (401, 403):
        return None, "STT_AUTH_FAILED"
    if response.status_code == 429:
        return None, "STT_LIMIT_REACHED"
    if response.status_code != 200:
        return None, "STT_FAILED"

    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        return None, "STT_FAILED"
    text = str(data.get("text") or "").strip()
    if not text:
        return None, "STT_EMPTY"
    return text, None
