import providers


def test_providers_status_tools_first():
    status = providers.providers_status()
    names = [p["provider"] for p in status["providers"]]
    assert names == ["yandex", "google_meet", "zoom", "teams", "jitsi"]
    assert status["creds_policy"] == "tools_first"


def test_aliases_and_stubs():
    assert providers.normalize_provider("telemost") == "yandex"
    assert providers.normalize_provider("gmeet") == "google_meet"
    assert providers.normalize_provider("ms_teams") == "teams"
    for name in ("yandex", "google_meet", "zoom", "teams"):
        out = providers.get_provider(name).create(title="Demo Call")
        assert out["ok"] is True
        assert out.get("stub") is True
        assert out["provider"] == name
        assert f"stub.{name}." in out["join_url"] or f"stub.telemost." in out["join_url"]


def test_jitsi_creates_real_room_without_oauth():
    out = providers.get_provider("jitsi").create(title="Standup")
    assert out["ok"] is True
    assert out.get("stub") is False
    assert out["join_url"].startswith("https://meet.jit.si/")
