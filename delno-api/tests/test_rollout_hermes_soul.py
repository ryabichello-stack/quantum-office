"""Existing multiplexed Hermes profiles receive a reviewed template update."""

import importlib.util
import sys
from pathlib import Path


def test_rollout_finds_worker_profiles_and_preserves_edited_files(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "rollout_hermes_soul.py"
    spec = importlib.util.spec_from_file_location("rollout_hermes_soul", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    templates = tmp_path / "templates"
    baseline = tmp_path / "baseline"
    profile = tmp_path / "profiles" / "workers" / "pool" / "profiles" / "tenant_a"
    for root in (templates, baseline, profile):
        (root / "skills").mkdir(parents=True)
    (templates / "SOUL.md").write_text("new soul")
    (templates / "skills/onboarding.md").write_text("new skill")
    (baseline / "SOUL.md").write_text("old soul")
    (baseline / "skills/onboarding.md").write_text("old skill")
    (profile / "SOUL.md").write_text("old soul")
    (profile / "skills/onboarding.md").write_text("owner edited skill")

    monkeypatch.setattr(module, "TEMPLATES", templates)
    monkeypatch.setattr(sys, "argv", ["rollout", "--root", str(tmp_path / "profiles"),
                                      "--baseline", str(baseline), "--apply"])
    module.main()

    assert (profile / "SOUL.md").read_text() == "new soul"
    assert (profile / "skills/onboarding.md").read_text() == "owner edited skill"
    assert (profile / "skills/onboarding.md.update-candidate").read_text() == "new skill"
