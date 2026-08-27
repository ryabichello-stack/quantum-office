"""Sales training mode: PIN unlock, ACL tools, no internal files."""

from __future__ import annotations

import json
from pathlib import Path

import ava_client as ac
from scenarios import default_scenario, load_scenarios, role_for
from session_store import get_session_meta, init_db, set_session_acl_role
from training import (
    ROLE_TRAINEE,
    parse_training_command,
    verify_pin,
)


def test_parse_training_commands():
    assert parse_training_command("/обучение")[0] == "help"
    assert parse_training_command("/обучение 482917") == ("unlock", "482917")
    assert parse_training_command("/обучение выход") == ("lock", None)
    assert parse_training_command("привет") == (None, None)


def test_verify_pin(monkeypatch):
    monkeypatch.setenv("SECRETARY_TRAINING_PIN", "482917")
    assert verify_pin("482917") is True
    assert verify_pin("482-917") is True
    assert verify_pin("000000") is False


def test_role_trainee_from_allowlist(monkeypatch):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "1")
    monkeypatch.setenv("SECRETARY_TRAINEE_IDS", "555")
    monkeypatch.setenv("SECRETARY_TRAINING_ENABLED", "true")
    load_scenarios()
    assert role_for("555", "telegram", chat_type="private") == ROLE_TRAINEE
    assert role_for("555", "max", chat_type="private") == ROLE_TRAINEE
    assert role_for("555", "telegram_business", chat_type="private") == "guest"
    assert role_for("999", "telegram", chat_type="private") == "guest"


def test_role_trainee_from_session_acl(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "1")
    monkeypatch.setenv("SECRETARY_TRAINEE_IDS", "")
    monkeypatch.setenv("SECRETARY_TRAINING_ENABLED", "true")
    load_scenarios()
    db = tmp_path / "s.db"
    init_db(db)
    set_session_acl_role(db, "telegram:777", ROLE_TRAINEE)
    meta = get_session_meta(db, "telegram:777")
    assert meta["acl_role"] == ROLE_TRAINEE
    assert role_for("777", "telegram", chat_type="private", acl_role=ROLE_TRAINEE) == ROLE_TRAINEE


def test_trainee_tools_are_knowledge_only():
    names = {t["function"]["name"] for t in ac.tools_for_role("trainee")}
    assert names == {"get_company_knowledge", "list_knowledge_topics"}
    assert "browse_files" not in names
    assert "search_office_memory" not in names
    assert "outbound_dial" not in names


def test_trainee_cannot_browse_files():
    raw = ac.run_tool(
        "browse_files",
        {"source": "mailru", "path": "/"},
        role="trainee",
    )
    data = json.loads(raw)
    assert data["ok"] is False
    assert data["error"] == "forbidden"


def test_default_trainee_scenario():
    load_scenarios()
    sc = default_scenario("trainee")
    assert sc.id == "training"
