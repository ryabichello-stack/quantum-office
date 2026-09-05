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
        messages: list[dict[str, str]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIProvider(ModelProvider):
    name = "openai"

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.openai_api_key:
            return {"ok": False, "error": "openai_api_key_not_configured"}
        try:
            import httpx

            payload: dict[str, Any] = {
                "model": model or settings.openai_model,
                "messages": messages,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
                timeout=60.0,
            )
            if response.status_code == 200:
                return {"ok": True, "data": response.json(), "provider": self.name}
            return {"ok": False, "error": f"openai_http_{response.status_code}", "provider": self.name}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "provider": self.name}


class StubProvider(ModelProvider):
    name = "stub"

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        last = messages[-1]["content"] if messages else ""
        return {
            "ok": True,
            "provider": self.name,
            "data": {"choices": [{"message": {"role": "assistant", "content": f"[stub] {last[:200]}"}}]},
        }


def get_model_provider() -> ModelProvider:
    settings = get_settings()
    provider = (getattr(settings, "model_provider", None) or "openai").lower()
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider()
    if provider == "openai":
        return StubProvider()
    return StubProvider()
