"""SOUL / hermes_runtime templates must ship in the API tree for provision."""

from __future__ import annotations

from pathlib import Path

from app.services.hermes_nous.provision import _TEMPLATES


def test_soul_template_documents_phone_micro_steps():
    soul = (_TEMPLATES / "SOUL.md").read_text(encoding="utf-8")
    assert "need_sip" in soul
    assert "need_did" in soul
    assert "need_reg" in soul
    assert "credentials.open_form" in soul
    assert "telegram_bot" in soul
    assert "max_bot" in soul
    assert "files_yadisk" in soul
    assert "hermes_ops" in soul or "hermes.setup_status" in soul


def test_templates_dir_layout():
    assert _TEMPLATES.is_dir(), f"missing templates at {_TEMPLATES}"
    for name in ("SOUL.md", "config.yaml", "AGENTS.md"):
        assert (_TEMPLATES / name).is_file(), name
