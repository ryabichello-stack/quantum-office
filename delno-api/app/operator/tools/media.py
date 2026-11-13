"""Hermes media tools — image generation (OpenAI Images API)."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult


class GenerateImageTool:
    name = "generate_image"
    description = (
        "Generate an image from a text prompt via OpenAI Images API. "
        "Use when the owner asks Hermes to create a picture, mockup, cover, or visual. "
        "Returns a data-URL (png) the chat can show."
    )
    critical_write = False
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed image prompt in Russian or English",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1024x1536", "1536x1024"],
                "description": "Output size",
            },
        },
        "required": ["prompt"],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        prompt = str(params.get("prompt") or "").strip()
        if len(prompt) < 3:
            return ToolResult(ok=False, message="prompt_required")
        size = str(params.get("size") or "1024x1024")
        if size not in {"1024x1024", "1024x1536", "1536x1024"}:
            size = "1024x1024"

        settings = get_settings()
        api_key = (settings.openai_api_key or "").strip()
        if not api_key:
            return ToolResult(ok=False, message="OPENAI_API_KEY not configured")

        base = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        proxy = (getattr(settings, "openai_http_proxy", None) or "").strip() or None

        # dall-e-3 is widely available; try gpt-image-1 first when account supports it.
        models = ["gpt-image-1", "dall-e-3"]
        last_error = "image_generation_failed"
        for model in models:
            payload: dict[str, Any] = {
                "model": model,
                "prompt": prompt[:4000],
                "size": "1024x1024" if model == "dall-e-3" else size,
                "n": 1,
            }
            if model == "dall-e-3":
                payload["response_format"] = "b64_json"
            try:
                client_kwargs: dict[str, Any] = {"timeout": 120.0}
                if proxy:
                    client_kwargs["proxy"] = proxy
                with httpx.Client(**client_kwargs) as client:
                    res = client.post(
                        f"{base}/images/generations",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if res.status_code >= 400:
                    last_error = f"http_{res.status_code}: {(res.text or '')[:200]}"
                    continue
                body = res.json()
                data = (body.get("data") or [{}])[0]
                b64 = data.get("b64_json")
                url = data.get("url")
                if b64:
                    data_url = f"data:image/png;base64,{b64}"
                    return ToolResult(
                        ok=True,
                        message="image_generated",
                        data={
                            "prompt": prompt[:500],
                            "model": model,
                            "size": size,
                            "image_data_url": data_url,
                            "markdown": f"![Hermes image]({data_url})",
                        },
                    )
                if url:
                    return ToolResult(
                        ok=True,
                        message="image_generated",
                        data={
                            "prompt": prompt[:500],
                            "model": model,
                            "size": size,
                            "image_url": url,
                            "markdown": f"![Hermes image]({url})",
                        },
                    )
                last_error = "empty_image_payload"
            except httpx.HTTPError as exc:
                last_error = f"network:{exc}"
                continue

        return ToolResult(ok=False, message=last_error)
