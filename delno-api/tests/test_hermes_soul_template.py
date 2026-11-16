"""SOUL / hermes_runtime templates must ship in the API tree for provision."""

from __future__ import annotations

from pathlib import Path

from app.services.hermes_nous.provision import _TEMPLATES


def test_soul_template_starts_from_owner_goal_without_mandatory_tools():
    soul = (_TEMPLATES / "SOUL.md").read_text(encoding="utf-8")
    skill = (_TEMPLATES / "skills/onboarding.md").read_text(encoding="utf-8")
    assert "hermes.goal_set" in soul and "hermes.goal_set" in skill
    assert "Нет обязательного списка" in soul
    assert "только если владелец её выбрал" in soul
    assert "hermes.catalog_ack" in skill
    assert "полный черновик" in soul
    assert "##" in soul
    assert "credentials.open_form" in soul
    assert "hermes.setup_status" in soul


def test_templates_dir_layout():
    assert _TEMPLATES.is_dir(), f"missing templates at {_TEMPLATES}"
    for name in ("SOUL.md", "config.yaml", "AGENTS.md"):
        assert (_TEMPLATES / name).is_file(), name
