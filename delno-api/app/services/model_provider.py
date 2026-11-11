"""LLM/voice provider abstraction — swap vendors without rewriting business logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIProvider(ModelProvider):
    name = "openai"

    def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.openai_api_key:
            return {"ok": False, "error": "openai_api_key_not_configured"}
        try:
            from app.services.openai_http import openai_client, openai_proxy_url, openai_url

            payload: dict[str, Any] = {
                "model": model or settings.openai_model,
                "messages": messages,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            # Vision / large multimodal payloads need a longer timeout
            has_vision = any(
                isinstance(m.get("content"), list)
                for m in messages
                if isinstance(m, dict)
            )
            with openai_client(timeout=60.0 if has_vision else 30.0) as client:
                response = client.post(
                    openai_url("/chat/completions"),
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json=payload,
                )
            if response.status_code == 200:
                data = response.json()
                usage = data.get("usage") if isinstance(data, dict) else None
                return {
                    "ok": True,
                    "data": data,
                    "provider": self.name,
                    "via_proxy": bool(openai_proxy_url()),
                    "usage": usage if isinstance(usage, dict) else {},
                    "model": payload.get("model"),
                }
            return {
                "ok": False,
                "error": f"openai_http_{response.status_code}",
                "provider": self.name,
                "via_proxy": bool(openai_proxy_url()),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "provider": self.name}


class StubProvider(ModelProvider):
    name = "stub"

    def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        last = messages[-1]["content"] if messages else ""
        if isinstance(last, list):
            texts = [p.get("text", "") for p in last if isinstance(p, dict) and p.get("type") == "text"]
            last = " ".join(texts) or "[multimodal]"
        return {
            "ok": True,
            "provider": self.name,
            "data": {"choices": [{"message": {"role": "assistant", "content": f"[stub] {str(last)[:200]}"}}]},
        }


def get_model_provider() -> ModelProvider:
    settings = get_settings()
    provider = (getattr(settings, "model_provider", None) or "openai").lower()
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider()
    if provider == "openai":
        return StubProvider()
    return StubProvider()
