"""Owner full-access only in private Telegram DM."""

from scenarios import is_owner, load_scenarios, role_for


def test_owner_private_dm(monkeypatch):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "963782")
    monkeypatch.setenv("SECRETARY_TELEGRAM_DEFAULT_OWNER", "false")
    load_scenarios()
    assert is_owner("963782", "telegram", chat_type="private") is True
    assert role_for("963782", "telegram", chat_type="private") == "owner"


def test_owner_in_group_is_guest(monkeypatch):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "963782")
    monkeypatch.setenv("SECRETARY_TELEGRAM_DEFAULT_OWNER", "false")
    load_scenarios()
    assert is_owner("963782", "telegram", chat_type="group") is False
    assert is_owner("963782", "telegram", chat_type="supergroup") is False
    assert role_for("963782", "telegram", chat_type="group") == "guest"


def test_stranger_is_guest(monkeypatch):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "963782")
    monkeypatch.setenv("SECRETARY_TELEGRAM_DEFAULT_OWNER", "true")
    load_scenarios()
    assert role_for("111", "telegram", chat_type="private") == "guest"


def test_no_channel_owner_shortcuts(monkeypatch):
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "963782")
    load_scenarios()
    assert is_owner("me", "owner") is False
    assert is_owner("boss", "personal") is False
