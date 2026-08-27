"""Tests for owner alert formatting / gating (no live Telegram/Max)."""

from __future__ import annotations

import os

import owner_alerts


def test_format_alert_labels():
    text = owner_alerts.format_alert(
        kind="outreach_reply",
        title="positive_interest: a@b.ru",
        body="Превью ответа",
    )
    assert "[Ответ на рассылку]" in text
    assert "positive_interest" in text
    assert "Превью" in text


def test_should_alert_new_chat_guest_only(monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_ALERT_ENABLED", "true")
    monkeypatch.setenv("SECRETARY_OWNER_IDS", "963782")
    monkeypatch.setenv("OWNER_ALERT_MAX_USER_ID", "12239171")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    assert owner_alerts.should_alert_new_chat(
        channel="telegram", user_id="111", role="guest"
    )
    assert owner_alerts.should_alert_new_chat(
        channel="telegram_business", user_id="6808878848", role="guest"
    )
    assert owner_alerts.should_alert_new_chat(
        channel="max", user_id="999", role="guest"
    )
    assert not owner_alerts.should_alert_new_chat(
        channel="telegram", user_id="963782", role="owner"
    )
    assert not owner_alerts.should_alert_new_chat(
        channel="telegram", user_id="111", role="trainee"
    )
    assert not owner_alerts.should_alert_new_chat(
        channel="telegram", user_id="smoke-guest", role="guest"
    )
    assert not owner_alerts.should_alert_new_chat(
        channel="max", user_id="12239171", role="guest"
    )
    assert not owner_alerts.should_alert_new_chat(
        channel="api", user_id="111", role="guest"
    )


def test_claim_once_dedupes(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert owner_alerts.claim_once("k1", kind="new_chat") is True
    assert owner_alerts.claim_once("k1", kind="new_chat") is False
    assert owner_alerts.claim_once("k2", kind="new_chat") is True


def test_notify_owner_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_ALERT_ENABLED", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    out = owner_alerts.notify_owner(kind="inbound_call", title="test", body="x")
    assert out.get("skipped") == "disabled"
