"""OpenAI HTTP client helpers — base URL + egress proxy (SPB→Minsk→NL bridge)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.core.config import get_settings


def openai_base_url() -> str:
    settings = get_settings()
    raw = (getattr(settings, "openai_base_url", None) or "").strip()
    if not raw:
        raw = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
    return raw.rstrip("/")


def openai_proxy_url() -> str | None:
    """Prefer explicit OPENAI_HTTP_PROXY, then HTTPS_PROXY / HTTP_PROXY / ALL_PROXY."""
    settings = get_settings()
    for candidate in (
        getattr(settings, "openai_http_proxy", None),
        os.getenv("OPENAI_HTTP_PROXY"),
        os.getenv("HTTPS_PROXY"),
        os.getenv("HTTP_PROXY"),
        os.getenv("ALL_PROXY"),
        os.getenv("https_proxy"),
        os.getenv("http_proxy"),
        os.getenv("all_proxy"),
    ):
        value = (candidate or "").strip()
        if value:
            return value
    return None


def openai_url(path: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    return f"{openai_base_url()}{path}"


def openai_client(**kwargs: Any) -> httpx.Client:
    proxy = openai_proxy_url()
    timeout = kwargs.pop("timeout", 30.0)
    if proxy:
        return httpx.Client(timeout=timeout, proxy=proxy, **kwargs)
    return httpx.Client(timeout=timeout, **kwargs)
