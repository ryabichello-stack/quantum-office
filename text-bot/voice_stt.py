"""Telegram voice/audio → text via OpenAI Whisper."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger("ava-text-bot.voice-stt")

TELEGRAM_API = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1").strip() or "whisper-1"
VOICE_ENABLED = (os.getenv("TELEGRAM_VOICE_STT_ENABLED", "true") or "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def enabled() -> bool:
    return VOICE_ENABLED


def extract_voice_file(message: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return {file_id, duration, mime, kind} from voice / audio / video_note, else None."""
    if not isinstance(message, dict):
        return None
    for kind in ("voice", "audio", "video_note"):
        block = message.get(kind)
        if not isinstance(block, dict):
            continue
        file_id = str(block.get("file_id") or "").strip()
        if not file_id:
            continue
        return {
            "file_id": file_id,
            "duration": int(block.get("duration") or 0),
            "mime": str(block.get("mime_type") or ("audio/ogg" if kind == "voice" else "")),
            "kind": kind,
            "file_unique_id": str(block.get("file_unique_id") or ""),
        }
    return None


def _tg_get_file(token: str, file_id: str) -> dict[str, Any]:
    url = f"{TELEGRAM_API}/bot{token}/getFile"
    data = urllib.parse.urlencode({"file_id": file_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    if not out.get("ok"):
        raise RuntimeError(str(out.get("description") or out))
    return out.get("result") or {}


def _tg_download(token: str, file_path: str) -> bytes:
    url = f"{TELEGRAM_API}/file/bot{token}/{file_path}"
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def transcribe_telegram_voice(
    *,
    token: str,
    file_id: str,
    openai_api_key: str,
    language: str = "ru",
) -> str:
    """Download Telegram file and transcribe with Whisper. Returns plain text."""
    if not enabled():
        raise RuntimeError("voice_stt_disabled")
    if not (token or "").strip():
        raise RuntimeError("telegram_token_missing")
    if not (openai_api_key or "").strip():
        raise RuntimeError("openai_missing")

    meta = _tg_get_file(token.strip(), file_id)
    path = str(meta.get("file_path") or "").strip()
    if not path:
        raise RuntimeError("telegram_file_path_missing")
    raw = _tg_download(token.strip(), path)
    if not raw:
        raise RuntimeError("empty_audio")

    suffix = ".ogg"
    lower = path.lower()
    for ext in (".ogg", ".oga", ".mp3", ".m4a", ".wav", ".mp4", ".webm"):
        if lower.endswith(ext):
            suffix = ext
            break

    from openai import OpenAI

    client = OpenAI(api_key=openai_api_key.strip())
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(raw)
        tmp.flush()
        with open(tmp.name, "rb") as fh:
            kwargs: dict[str, Any] = {"model": WHISPER_MODEL, "file": fh}
            if language:
                kwargs["language"] = language
            result = client.audio.transcriptions.create(**kwargs)
    text = str(getattr(result, "text", "") or "").strip()
    if not text:
        raise RuntimeError("empty_transcript")
    logger.info("voice transcribed chars=%s bytes=%s", len(text), len(raw))
    return text


def format_voice_user_text(transcript: str, *, kind: str = "voice") -> str:
    label = {
        "voice": "голосовое сообщение",
        "audio": "аудиофайл",
        "video_note": "видеосообщение",
    }.get(kind, "голосовое сообщение")
    return f"[{label}]\n{(transcript or '').strip()}"
