"""Fetch OpenAI model/voice catalogs for admin settings dropdowns."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.platform_env import read_env_values

_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}
_CACHE_TTL_SEC = 300

# Realtime voices (OpenAI Realtime API — extend when new voices ship)
VOICE_FALLBACK: tuple[str, ...] = (
    "cedar",
    "marin",
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
)

CHAT_MODEL_FALLBACK: tuple[str, ...] = (
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4o",
)

REALTIME_MODEL_FALLBACK: tuple[str, ...] = (
    "gpt-realtime-2.1",
    "gpt-realtime-2.1-mini",
    "gpt-4o-realtime-preview",
    "gpt-4o-mini-realtime-preview",
)


def _api_key() -> str:
    values = read_env_values()
    return (values.get("OPENAI_API_KEY") or get_settings().openai_api_key or "").strip()


def _fetch_model_ids(api_key: str) -> tuple[list[str], str | None]:
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        return [], f"network:{exc.__class__.__name__}"

    if response.status_code in (401, 403):
        return [], "auth_failed"
    if response.status_code != 200:
        return [], f"http_{response.status_code}"

    try:
        data = response.json()
    except ValueError:
        return [], "invalid_json"

    ids = sorted({str(item.get("id", "")).strip() for item in data.get("data", []) if item.get("id")})
    return ids, None


def _is_realtime_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return "realtime" in lowered


def _is_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    if _is_realtime_model(model_id):
        return False
    if any(token in lowered for token in ("embedding", "whisper", "tts", "dall-e", "davinci", "babbage")):
        return False
    return lowered.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))


def _merge_unique(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for item in lst:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
    return out


def fetch_openai_options(*, force_refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force_refresh and _CACHE["payload"] and now < float(_CACHE["expires_at"]):
        return dict(_CACHE["payload"])

    api_key = _api_key()
    values = read_env_values()
    current_chat = (values.get("OPENAI_MODEL") or get_settings().openai_model or "").strip()
    current_realtime = (values.get("OPENAI_REALTIME_MODEL") or get_settings().openai_realtime_model or "").strip()
    current_voice = (values.get("OPENAI_REALTIME_VOICE") or get_settings().openai_realtime_voice or "").strip()

    source = "fallback"
    fetch_error: str | None = None
    chat_models = list(CHAT_MODEL_FALLBACK)
    realtime_models = list(REALTIME_MODEL_FALLBACK)
    voices = list(VOICE_FALLBACK)

    if api_key:
        model_ids, err = _fetch_model_ids(api_key)
        if model_ids:
            source = "openai"
            fetched_chat = [mid for mid in model_ids if _is_chat_model(mid)]
            fetched_realtime = [mid for mid in model_ids if _is_realtime_model(mid)]
            chat_models = _merge_unique(fetched_chat, chat_models, [current_chat] if current_chat else [])
            realtime_models = _merge_unique(
                fetched_realtime,
                realtime_models,
                [current_realtime] if current_realtime else [],
            )
        elif err:
            fetch_error = err
            chat_models = _merge_unique(chat_models, [current_chat] if current_chat else [])
            realtime_models = _merge_unique(realtime_models, [current_realtime] if current_realtime else [])
    else:
        fetch_error = "openai_key_missing"

    if current_voice and current_voice not in voices:
        voices = _merge_unique([current_voice], voices)

    payload = {
        "source": source,
        "fetched_at": int(now),
        "fetch_error": fetch_error,
        "chat_models": chat_models,
        "realtime_models": realtime_models,
        "realtime_voices": voices,
        "defaults": {
            "OPENAI_MODEL": current_chat or chat_models[0] if chat_models else "",
            "OPENAI_REALTIME_MODEL": current_realtime or realtime_models[0] if realtime_models else "",
            "OPENAI_REALTIME_VOICE": current_voice or "cedar",
        },
    }
    _CACHE["payload"] = payload
    _CACHE["expires_at"] = now + _CACHE_TTL_SEC
    return payload
