"""Tenant-defined content themes for flywheel."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from modules.content_flywheel.theme_config import (
    apply_preset,
    load_preset,
    load_theme_config,
    min_score_for_tenant,
    save_theme_config,
    taxonomy_from_config,
)


def test_load_quantum_labs_has_fintech_themes():
    cfg = load_theme_config("quantum-labs")
    tax = taxonomy_from_config(cfg)
    assert "money_flows" in tax
    assert cfg.get("lens_label")
    assert len(cfg.get("themes") or []) >= 3


def test_generic_preset_minimal():
    cfg = load_preset("generic")
    assert cfg.get("lens_id") == "generic"
    assert len(cfg.get("themes") or []) >= 1


def test_save_and_reload_tenant_config():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("modules.content_flywheel.theme_config.DATA_DIR", Path(tmp)):
            saved = save_theme_config(
                "acme-corp",
                {
                    "lens_id": "saas",
                    "lens_label": "B2B SaaS",
                    "brand_short": "Acme",
                    "min_score": 0.4,
                    "themes": [
                        {
                            "id": "growth",
                            "label": "Рост",
                            "keywords": ["arr", "mrr", "рост"],
                            "weight": 1.0,
                        }
                    ],
                },
            )
            assert saved["tenant_id"] == "acme-corp"
            path = Path(tmp) / "tenants" / "acme-corp" / "content_theme.json"
            assert path.is_file()
            reloaded = load_theme_config("acme-corp")
            assert reloaded["lens_label"] == "B2B SaaS"
            assert reloaded["themes"][0]["id"] == "growth"


def test_apply_preset_writes_data_dir():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("modules.content_flywheel.theme_config.DATA_DIR", Path(tmp)):
            cfg = apply_preset("demo-tenant", "generic")
            assert cfg.get("preset") == "generic"
            raw = json.loads(
                (Path(tmp) / "tenants" / "demo-tenant" / "content_theme.json").read_text(encoding="utf-8")
            )
            assert raw["lens_id"] == "generic"


def test_min_score_env_override():
    with patch.dict("os.environ", {"FLYWHEEL_THEME_MIN_SCORE": "0.5"}, clear=False):
        assert min_score_for_tenant("quantum-labs") == 0.5
