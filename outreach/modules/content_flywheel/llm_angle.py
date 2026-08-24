"""Optional LLM editorial angle — tenant lens, any industry."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from modules.content_flywheel.theme_config import load_theme_config

logger = logging.getLogger("ava-outreach.content_flywheel.llm_angle")


def llm_angle_enabled() -> bool:
    return (os.getenv("FLYWHEEL_LLM_ANGLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def enrich_editorial_angle(
    *,
    title: str,
    body: str,
    analysis: dict[str, Any],
    tenant_id: str,
) -> dict[str, Any]:
    """Return analysis enriched with LLM hook when API key present."""
    out = dict(analysis)
    if not llm_angle_enabled():
        out["llm_angle"] = {"enabled": False, "skipped": "FLYWHEEL_LLM_ANGLE off"}
        return out

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        out["llm_angle"] = {"enabled": True, "skipped": "no OPENAI_API_KEY"}
        return out

    cfg = load_theme_config(tenant_id)
    lens = (cfg.get("lens_label") or "ваша тематика").strip()
    brand = (cfg.get("brand_short") or "").strip()
    themes = ", ".join(t["label"] for t in (cfg.get("themes") or [])[:6] if t.get("label"))

    prompt = (
        f"Линза контента: {lens}.\n"
        f"Темы: {themes or 'не заданы'}.\n"
        f"Бренд (если уместно): {brand or 'не указан'}.\n"
        f"Keyword-анализ: tier={analysis.get('theme_tier')}, "
        f"score={analysis.get('theme_score')}, tags={analysis.get('theme_labels')}.\n\n"
        f"Заголовок: {title[:300]}\n"
        f"Текст: {(body or '')[:2000]}\n\n"
        "Верни JSON: hook (2-3 предложения — редакционный угол для поста в соцсети), "
        "headline (короткий заголовок до 80 символов), "
        "relevance (одно предложение почему это важно для линзы)."
    )
    model = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
    req_body = {
        "model": model,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты редактор контент-студии. Пиши на русском. "
                    "Угол должен соответствовать заданной линзе tenant — не навязывай финтех, "
                    "если линза другая. Только JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(req_body).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode())
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        hook = (data.get("hook") or "").strip()
        if hook:
            out["editorial_hook"] = hook[:2000]
            out["llm_headline"] = (data.get("headline") or title)[:120]
            out["llm_relevance"] = (data.get("relevance") or "")[:500]
        out["llm_angle"] = {"enabled": True, "model": model, "used": bool(hook)}
        return out
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("llm_angle failed: %s", exc)
        out["llm_angle"] = {"enabled": True, "error": str(exc)[:200]}
        return out
