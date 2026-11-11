from datetime import datetime

import pytz

import providers


def test_list_providers_tools_first():
    status = providers.providers_status()
    names = [p["source"] for p in status["providers"]]
    assert names == ["mailru", "yandex", "google", "outlook"]
    assert all(p["configured"] is False for p in status["providers"])
    assert status["creds_policy"] == "tools_first"


def test_aliases_and_stub_suggest():
    assert providers.normalize_source("gcal") == "google"
    assert providers.normalize_source("ya") == "yandex"
    assert providers.normalize_source("office365") == "outlook"
    start = pytz.timezone("Europe/Moscow").localize(datetime(2026, 11, 12, 10, 0))
    for source in ("mailru", "yandex", "google", "outlook"):
        items = providers.get_provider(source).suggest_slots(start, duration_min=30, suggestions_count=2)
        assert len(items) == 2
        assert items[0]["source"] == source
        assert items[0].get("stub") is True


def test_stub_create_google():
    start = pytz.timezone("Europe/Moscow").localize(datetime(2026, 11, 12, 11, 0))
    end = start.replace(minute=30)
    out = providers.get_provider("google").create_event(
        start_dt=start, end_dt=end, summary="Demo"
    )
    assert out["stub"] is True
    assert out["created"] is False
    assert out["source"] == "google"
