"""Layer E: ops notify, consent ledger, sequence step analytics."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.analytics import build_sequence_step_report
from modules.consent import ConsentLedgerStore, record_consent_from_suppression
from ops_notify import (
    OpsNotifyStore,
    PANEL_BRAND,
    _format_panel_telegram,
    notify_ops_event,
    resolve_bot_token,
    telegram_apply_branding,
    telegram_discover_chats,
    telegram_verify_bot,
)
from runtime_settings import RuntimeSettings


def test_consent_record_and_list():
    with tempfile.TemporaryDirectory() as tmp:
        store = ConsentLedgerStore(Path(tmp) / "c.db")
        row = store.record(
            email="Test@Example.com",
            status="unsubscribed",
            source="test",
            reason="user asked",
        )
        assert row["email"] == "test@example.com"
        items, total = store.list_entries(limit=10)
        assert total == 1
        assert items[0]["status"] == "unsubscribed"


def test_consent_from_suppression():
    with tempfile.TemporaryDirectory() as tmp:
        store = ConsentLedgerStore(Path(tmp) / "c.db")
        record_consent_from_suppression(
            store, email="a@b.ru", reason="hard_bounce:550", source="imap"
        )
        latest = store.latest_for_email("a@b.ru")
        assert latest and latest["status"] == "bounced"


def test_ops_notify_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        store = OpsNotifyStore(Path(tmp) / "n.db")
        assert store.should_send("evt1", dedup_minutes=30) is True
        store.mark_sent("evt1")
        assert store.should_send("evt1", dedup_minutes=30) is False


def test_ops_notify_skips_when_disabled():
    settings = MagicMock()
    settings.get.return_value = "false"
    out = notify_ops_event(
        event="test",
        title="t",
        body="b",
        settings=settings,
        dedup_key="unique-disabled-test",
    )
    assert out.get("skipped") is True


def test_sequence_step_report_empty():
    class FakeSeq:
        @staticmethod
        def connect():
            class Ctx:
                def __enter__(self):
                    conn = sqlite3.connect(":memory:")
                    conn.row_factory = sqlite3.Row
                    conn.execute(
                        """
                        CREATE TABLE sequence_leads (
                          id INTEGER PRIMARY KEY,
                          current_step INTEGER,
                          status TEXT
                        )
                        """
                    )
                    self._conn = conn
                    return conn

                def __exit__(self, *a):
                    self._conn.close()

            return Ctx()

    report = build_sequence_step_report(FakeSeq(), max_steps=3)
    assert report["total_sequences"] == 0
    assert len(report["steps"]) == 3


def test_resolve_bot_token_prefers_argument():
    settings = MagicMock()
    settings.get.return_value = "stored-token"
    assert resolve_bot_token("inline", settings) == "inline"
    assert resolve_bot_token("", settings) == "stored-token"


@patch("ops_notify._telegram_api")
def test_telegram_verify_bot(mock_api):
    mock_api.return_value = {
        "ok": True,
        "result": {"id": 1, "username": "Quantum_panel_bot", "first_name": "Panel"},
    }
    out = telegram_verify_bot("tok")
    assert out["ok"] is True
    assert out["username"] == "Quantum_panel_bot"
    assert "t.me/Quantum_panel_bot" in (out.get("link") or "")


@patch("ops_notify._telegram_api")
def test_telegram_discover_chats(mock_api):
    mock_api.return_value = {
        "ok": True,
        "result": [
            {
                "message": {
                    "chat": {
                        "id": 12345,
                        "type": "private",
                        "first_name": "Operator",
                    }
                }
            }
        ],
    }
    out = telegram_discover_chats("tok")
    assert out["ok"] is True
    assert out["chats"][0]["chat_id"] == "12345"


def test_panel_telegram_format():
    text = _format_panel_telegram(source="Outreach", title="Тест", body="Тело")
    assert PANEL_BRAND in text
    assert "Outreach" in text
    assert "Тест" in text


@patch("ops_notify._notify_store")
@patch("ops_notify._notify_telegram")
@patch("ops_notify._notify_email")
def test_notify_ops_event_panel_branding(mock_email, mock_tg, mock_store):
    mock_store.return_value.should_send.return_value = True
    settings = MagicMock()
    settings.get.side_effect = lambda k, d="": {
        "OPS_NOTIFY_ENABLED": "true",
        "OPS_NOTIFY_EMAIL_ENABLED": "false",
        "OPS_NOTIFY_TELEGRAM_ENABLED": "true",
        "OPS_NOTIFY_TELEGRAM_BOT_TOKEN": "tok",
        "OPS_NOTIFY_TELEGRAM_CHAT_ID": "1",
    }.get(k, d)
    out = notify_ops_event(
        event="test",
        title="Alert",
        body="Details",
        settings=settings,
        source="Console",
        dedup_key="panel-brand-test",
    )
    assert out.get("telegram") is True
    mock_tg.assert_called_once()
    assert PANEL_BRAND in mock_tg.call_args.kwargs["text"]
    assert "Console" in mock_tg.call_args.kwargs["text"]


@patch("ops_notify._notify_store")
@patch("ops_notify._notify_telegram")
@patch("ops_notify._notify_email")
def test_notify_panel_event_api_shape(mock_email, mock_tg, mock_store):
    mock_store.return_value.should_send.return_value = True
    from ops_notify import notify_panel_event

    settings = MagicMock()
    settings.get.side_effect = lambda k, d="": {
        "OPS_NOTIFY_ENABLED": "true",
        "OPS_NOTIFY_EMAIL_ENABLED": "false",
        "OPS_NOTIFY_TELEGRAM_ENABLED": "true",
        "OPS_NOTIFY_TELEGRAM_BOT_TOKEN": "tok",
        "OPS_NOTIFY_TELEGRAM_CHAT_ID": "1",
    }.get(k, d)
    out = notify_panel_event(
        event="service_down",
        title="Сервис недоступен",
        body="ava-knowledge не отвечает",
        source="Console",
        settings=settings,
        dedup_key="console:service:knowledge",
    )
    assert out.get("telegram") is True
    mock_tg.assert_called_once()
    assert "Console" in mock_tg.call_args.kwargs["text"]


@patch("ops_notify.resolve_avatar_jpg")
@patch("ops_notify._telegram_api")
def test_telegram_apply_branding_mocked(mock_api, mock_jpg):
    from pathlib import Path

    mock_api.return_value = {"ok": True, "result": True}
    mock_jpg.return_value = Path("/tmp/fake.jpg")
    with patch("ops_notify.telegram_set_profile_photo", return_value={"ok": True}) as mock_photo:
        out = telegram_apply_branding("tok", avatar_jpg="/tmp/fake.jpg")
        assert out.get("ok") is True
        assert mock_photo.called


@patch("ops_notify._telegram_api")
def test_telegram_apply_branding_skips_photo(mock_api):
    mock_api.return_value = {"ok": True, "result": True}
    with patch("ops_notify.telegram_set_profile_photo") as mock_photo:
        out = telegram_apply_branding("tok", include_profile_photo=False)
        assert out.get("ok") is True
        mock_photo.assert_not_called()
        assert out["steps"]["profile_photo"]["skipped"] is True


def test_runtime_settings_masked_token_not_overwritten():
    with tempfile.TemporaryDirectory() as tmp:
        rt = RuntimeSettings(Path(tmp) / "s.db")
        rt.set_many({"OPS_NOTIFY_TELEGRAM_BOT_TOKEN": "secret-token"})
        snap = rt.snapshot()
        assert snap["OPS_NOTIFY_TELEGRAM_BOT_TOKEN"] == ""
        assert snap["OPS_NOTIFY_TELEGRAM_BOT_TOKEN_CONFIGURED"] is True
        rt.set_many({"OPS_NOTIFY_TELEGRAM_BOT_TOKEN": ""})
        assert rt.get("OPS_NOTIFY_TELEGRAM_BOT_TOKEN") == "secret-token"
