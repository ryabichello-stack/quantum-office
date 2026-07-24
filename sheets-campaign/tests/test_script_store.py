"""script_store load/save overrides."""

from __future__ import annotations

import json
from pathlib import Path

import script_store


def test_load_default(tmp_path, monkeypatch):
    monkeypatch.setattr(script_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(script_store, "SCRIPT_FILE", tmp_path / "campaign_script.json")
    doc = script_store.load_script()
    assert "массовых выплат" in doc["script"] or "Quantum" in doc["greeting"]
    assert doc["source"] == "builtin"


def test_save_and_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(script_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(script_store, "SCRIPT_FILE", tmp_path / "campaign_script.json")
    script_store.save_script(greeting="Привет тест", script="Playbook X")
    doc = script_store.load_script()
    assert doc["greeting"] == "Привет тест"
    assert doc["script"] == "Playbook X"
    assert doc["source"] == "file"
    assert json.loads(Path(doc["path"]).read_text(encoding="utf-8"))["script"] == "Playbook X"
