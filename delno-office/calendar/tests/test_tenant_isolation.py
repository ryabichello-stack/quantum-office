"""Tenant A must not see tenant B's events. Env calendar is opt-in."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import providers  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


def setup_module() -> None:
    import os

    os.environ["CALENDAR_MEMORY_BACKEND"] = "1"
    os.environ["GOOGLE_CALENDAR_TOKEN"] = "env-cal-token"
    providers.seed_memory_events(
        "token-a",
        [{"summary": "A secret", "start": "2026-11-15T10:00:00+03:00", "end": "2026-11-15T11:00:00+03:00"}],
    )
    providers.seed_memory_events(
        "token-b",
        [{"summary": "B secret", "start": "2026-11-15T12:00:00+03:00", "end": "2026-11-15T13:00:00+03:00"}],
    )
    providers.seed_memory_events(
        "env-cal-token",
        [{"summary": "Env secret", "start": "2026-11-15T15:00:00+03:00", "end": "2026-11-15T16:00:00+03:00"}],
    )


def _summaries(response) -> list[str]:
    return [item["summary"] for item in response.json().get("events") or []]


def test_events_without_tenant_rejected():
    client = TestClient(main.app)
    response = client.post("/api/calendar/events", json={"source": "google"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tenant_required"


def test_events_foreign_tenant_rejected():
    client = TestClient(main.app)
    response = client.post(
        "/api/calendar/events",
        json={"source": "google", "tenant_id": "tenant-a", "credentials": {"token": "token-a"}},
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tenant_mismatch"
    assert "A secret" not in response.text
    assert "B secret" not in response.text


def test_tenant_a_does_not_see_tenant_b_events():
    client = TestClient(main.app)
    first = client.post(
        "/api/calendar/events",
        json={"source": "google", "tenant_id": "tenant-a", "credentials": {"token": "token-a"}},
    )
    second = client.post(
        "/api/calendar/events",
        json={"source": "google", "tenant_id": "tenant-b", "credentials": {"token": "token-b"}},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert _summaries(first) == ["A secret"]
    assert _summaries(second) == ["B secret"]
    assert "Env secret" not in first.text
    assert "token-a" not in first.text


def test_env_calendar_hidden_until_service_flag():
    client = TestClient(main.app)
    denied = client.post(
        "/api/calendar/events",
        json={"source": "google", "tenant_id": "tenant-a"},
    )
    assert denied.status_code == 403
    assert "Env secret" not in denied.text
    allowed = client.post(
        "/api/calendar/events",
        json={"source": "google", "tenant_id": "service-tenant", "allow_env_fallback": True},
    )
    assert allowed.status_code == 200
    assert _summaries(allowed) == ["Env secret"]


def test_change_rejects_foreign_tenant_and_missing_credentials(monkeypatch):
    class Provider:
        name = "google"

        def configured(self):
            return bool(providers.google_token())

        def delete_event(self, event_id):
            raise AssertionError("must not call provider without tenant credentials")

    monkeypatch.setattr(main, "_resolve_provider", lambda _: Provider())
    client = TestClient(main.app)
    body = {"tenant_id": "tenant-a", "source": "google", "event_id": "event-1"}
    foreign = client.post("/api/calendar/change?action=delete", json=body, headers={"X-Tenant-Id": "tenant-b"})
    missing = client.post("/api/calendar/change?action=delete", json=body, headers={"X-Tenant-Id": "tenant-a"})
    assert foreign.status_code == 403
    assert missing.status_code == 403


def test_change_uses_only_current_tenant_token(monkeypatch):
    seen = []

    class Provider:
        name = "google"

        def configured(self):
            return bool(providers.google_token())

        def delete_event(self, event_id):
            seen.append((providers.google_token(), event_id))
            return {"ok": True, "deleted": True}

    monkeypatch.setattr(main, "_resolve_provider", lambda _: Provider())
    client = TestClient(main.app)
    for tenant, token in (("tenant-a", "token-a"), ("tenant-b", "token-b")):
        response = client.post(
            "/api/calendar/change?action=delete",
            json={"tenant_id": tenant, "source": "google", "event_id": "event-1", "credentials": {"token": token}},
            headers={"X-Tenant-Id": tenant},
        )
        assert response.status_code == 200
    assert seen == [("token-a", "event-1"), ("token-b", "event-1")]


def test_tenant_booking_never_sends_legacy_welcome_mail(monkeypatch):
    class Provider:
        name = "google"

        def configured(self):
            return True

        def slot_is_free(self, start, end):
            return True

        def create_event(self, **kwargs):
            return {"ok": True, "created": True, "event_id": "own-event", "stub": False}

    monkeypatch.setattr(main, "_resolve_provider", lambda source: Provider())
    monkeypatch.setattr(main.mailer_client, "queue_welcome_presentation", lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy sender used")))
    response = TestClient(main.app).post(
        "/api/calendar/create",
        json={
            "tenant_id": "tenant-a", "source": "google", "credentials": {"token": "tenant-token"},
            "start": "2026-12-10T10:00:00+03:00", "attendee_email": "customer@example.test",
            "create_telemost": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["event_id"] == "own-event"
    assert response.json()["welcome_email_queued"] is False
