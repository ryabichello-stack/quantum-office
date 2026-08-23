"""Tenant-defined content themes — universal flywheel lens (any niche)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from core.paths import DATA_DIR
from core.tenant import DEFAULT_TENANT_ID

logger = logging.getLogger("ava-outreach.content_flywheel.theme_config")

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PRESETS_DIR = PACKAGE_ROOT / "config" / "theme_presets"
TENANTS_DIR = PACKAGE_ROOT / "config" / "tenants"
DEFAULT_TENANT = DEFAULT_TENANT_ID


def _tenant_data_path(tenant_id: str) -> Path:
    return Path(DATA_DIR) / "tenants" / tenant_id / "content_theme.json"


def _tenant_package_path(tenant_id: str) -> Path:
    return TENANTS_DIR / tenant_id / "content_theme.json"


def list_presets() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not PRESETS_DIR.is_dir():
        return out
    for path in sorted(PRESETS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": path.stem,
                    "lens_id": data.get("lens_id"),
                    "lens_label": data.get("lens_label"),
                    "themes_count": len(data.get("themes") or []),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue
    return out


def load_preset(preset_id: str) -> dict[str, Any]:
    path = PRESETS_DIR / f"{preset_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"preset_not_found: {preset_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_config(data, tenant_id=DEFAULT_TENANT)


def _normalize_config(raw: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
    themes_in = raw.get("themes") or []
    themes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, t in enumerate(themes_in):
        if not isinstance(t, dict):
            continue
        tid = (t.get("id") or f"theme_{i+1}").strip()
        if not tid or tid in seen:
            tid = f"theme_{i+1}_{len(seen)}"
        seen.add(tid)
        kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
        themes.append(
            {
                "id": tid[:80],
                "label": (t.get("label") or tid).strip()[:120],
                "hook_prefix": (t.get("hook_prefix") or raw.get("default_hook_prefix") or "").strip()[:200],
                "keywords": kws[:40],
                "weight": float(t.get("weight") or 1.0),
            }
        )
    if not themes:
        themes = [
            {
                "id": "core",
                "label": "Основная тема",
                "hook_prefix": (raw.get("default_hook_prefix") or "В контексте темы").strip(),
                "keywords": ["рынок"],
                "weight": 1.0,
            }
        ]
    return {
        "tenant_id": tenant_id,
        "preset": raw.get("preset"),
        "lens_id": (raw.get("lens_id") or "custom").strip()[:80],
        "lens_label": (raw.get("lens_label") or "Контент-тематика").strip()[:200],
        "brand_short": (raw.get("brand_short") or "").strip()[:80],
        "min_score": _float(raw.get("min_score"), 0.35),
        "score_cap": max(1.0, _float(raw.get("score_cap"), 4.0)),
        "high_tier_threshold": _float(raw.get("high_tier_threshold"), 0.65),
        "low_tier_threshold": _float(raw.get("low_tier_threshold"), 0.15),
        "off_topic_message": (raw.get("off_topic_message") or "Новость вне заданной тематики.").strip()[:500],
        "default_hook_prefix": (raw.get("default_hook_prefix") or "В контексте вашей темы").strip()[:200],
        "hashtags": [str(h).strip() for h in (raw.get("hashtags") or []) if str(h).strip()][:12],
        "video_intro": (raw.get("video_intro") or "Коротко по теме:").strip()[:200],
        "themes": themes,
    }


def _float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def load_theme_config(tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
    """Load tenant theme config: DATA_DIR override → package tenant → generic preset."""
    tenant_id = (tenant_id or DEFAULT_TENANT).strip() or DEFAULT_TENANT
    for path in (_tenant_data_path(tenant_id), _tenant_package_path(tenant_id)):
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                cfg = _normalize_config(raw, tenant_id=tenant_id)
                cfg["source_path"] = str(path)
                return cfg
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("content_theme load failed %s: %s", path, exc)
    try:
        cfg = load_preset("generic")
        cfg["tenant_id"] = tenant_id
        cfg["source_path"] = str(PRESETS_DIR / "generic.json")
        return cfg
    except FileNotFoundError:
        return _normalize_config({}, tenant_id=tenant_id)


def save_theme_config(tenant_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Persist tenant theme to DATA_DIR (runtime edits, survives deploy)."""
    tenant_id = (tenant_id or DEFAULT_TENANT).strip() or DEFAULT_TENANT
    normalized = _normalize_config(config, tenant_id=tenant_id)
    path = _tenant_data_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    normalized["source_path"] = str(path)
    return normalized


def apply_preset(tenant_id: str, preset_id: str) -> dict[str, Any]:
    preset = load_preset(preset_id)
    preset["tenant_id"] = tenant_id
    preset["preset"] = preset_id
    return save_theme_config(tenant_id, preset)


def taxonomy_from_config(config: dict[str, Any]) -> dict[str, str]:
    return {t["id"]: t["label"] for t in config.get("themes") or []}


def min_score_for_tenant(tenant_id: str = DEFAULT_TENANT) -> float:
    env = (os.getenv("FLYWHEEL_THEME_MIN_SCORE") or "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return float(load_theme_config(tenant_id).get("min_score") or 0.35)


def _keyword_matches(text: str, keyword: str) -> bool:
    kw = (keyword or "").strip()
    if not kw:
        return False
    if kw.startswith("/") and kw.endswith("/") and len(kw) > 2:
        try:
            return bool(re.search(kw[1:-1], text, flags=re.IGNORECASE))
        except re.error:
            return kw[1:-1].lower() in text
    return kw.lower() in text


def build_keyword_rules(config: dict[str, Any]) -> list[tuple[str, str, float]]:
    rules: list[tuple[str, str, float]] = []
    for theme in config.get("themes") or []:
        tid = theme.get("id") or ""
        weight = float(theme.get("weight") or 1.0)
        for kw in theme.get("keywords") or []:
            rules.append((str(kw), tid, weight))
    return rules


def brand_for_tenant(tenant_id: str = DEFAULT_TENANT) -> str:
    return (load_theme_config(tenant_id).get("brand_short") or "").strip()


def hashtags_for_tenant(tenant_id: str = DEFAULT_TENANT) -> list[str]:
    return list(load_theme_config(tenant_id).get("hashtags") or [])


def video_intro_for_tenant(tenant_id: str = DEFAULT_TENANT) -> str:
    return (load_theme_config(tenant_id).get("video_intro") or "Коротко по теме:").strip()
