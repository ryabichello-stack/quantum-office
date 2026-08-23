"""Layer F: company drill-down, consent export, on-call webhook."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from company_card import build_company_card
from modules.clients import ClientsStore
from modules.consent import ConsentLedgerStore
from modules.sequences import SequenceStore
from outbox import OutboxStore
from ops_notify import notify_ops_event


def _seed_company(clients: ClientsStore, company_id: str = "42") -> None:
    with clients.connect() as conn:
        conn.execute(
            """
            INSERT INTO companies(
                bitrix_id, title, emails_json, phones_json, primary_email,
                date_create, raw_json, synced_at, updated_at, inn, city, timezone
            ) VALUES (?, ?, '[]', '[]', ?, '', '{}', 'now', 'now', '7707083893', 'Москва', 'Europe/Moscow')
            """,
            (company_id, "Test Lombard", "test@lombard.ru"),
        )


def test_build_company_card():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clients = ClientsStore(tmp_path / "clients.db")
        outbox = OutboxStore(tmp_path / "outbox.db")
        sequences = SequenceStore(tmp_path / "sequences.db")
        consent = ConsentLedgerStore(tmp_path / "consent.db")
        _seed_company(clients)
        out = build_company_card(
            "42",
            clients=clients,
            outbox=outbox,
            sequences=sequences,
            consent=consent,
        )
        assert out["ok"] is True
        assert out["company"]["title"] == "Test Lombard"
        assert out["company"]["inn"] == "7707083893"


def test_build_company_card_missing():
    with tempfile.TemporaryDirectory() as tmp:
        clients = ClientsStore(Path(tmp) / "clients.db")
        out = build_company_card("999", clients=clients)
        assert out["ok"] is False
        assert out["error"] == "company_not_found"


def test_consent_export_rows():
    with tempfile.TemporaryDirectory() as tmp:
        store = ConsentLedgerStore(Path(tmp) / "c.db")
        store.record(email="a@b.ru", status="unsubscribed", source="test", reason="user asked")
        rows = store.export_rows()
        assert len(rows) == 1
        assert rows[0]["email"] == "a@b.ru"


def test_consent_export_date_filter():
    with tempfile.TemporaryDirectory() as tmp:
        store = ConsentLedgerStore(Path(tmp) / "c.db")
        store.record(email="old@b.ru", status="unsubscribed", source="test", reason="old")
        rows, total = store.list_entries(created_from="2099-01-01T00:00:00+00:00")
        assert total == 0
        rows2, total2 = store.list_entries()
        assert total2 == 1


@patch("ops_notify._notify_store")
@patch("ops_notify._notify_oncall_webhook")
def test_notify_oncall_test(mock_hook, mock_store):
    settings = MagicMock()
    settings.get.side_effect = lambda k, d="": {
        "OPS_NOTIFY_ONCALL_ENABLED": "true",
        "OPS_NOTIFY_ONCALL_WEBHOOK_URL": "https://hooks.example/oncall",
    }.get(k, d)
    from ops_notify import notify_oncall_test

    out = notify_oncall_test(settings, message="ping")
    assert out.get("ok") is True
    mock_hook.assert_called_once()


def test_build_company_card_has_data_quality():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clients = ClientsStore(tmp_path / "clients.db")
        outbox = OutboxStore(tmp_path / "outbox.db")
        sequences = SequenceStore(tmp_path / "sequences.db")
        consent = ConsentLedgerStore(tmp_path / "consent.db")
        _seed_company(clients)
        out = build_company_card(
            "42",
            clients=clients,
            outbox=outbox,
            sequences=sequences,
            consent=consent,
        )
        assert "data_quality" in out
        assert "score" in out["data_quality"]


@patch("ops_notify._notify_store")
@patch("ops_notify._notify_oncall_webhook")
def test_notify_ops_event_oncall_webhook(mock_oncall, mock_store):
    mock_store.return_value.should_send.return_value = True
    settings = MagicMock()
    settings.get.side_effect = lambda k, d="": {
        "OPS_NOTIFY_ENABLED": "true",
        "OPS_NOTIFY_EMAIL_ENABLED": "false",
        "OPS_NOTIFY_TELEGRAM_ENABLED": "false",
        "OPS_NOTIFY_ONCALL_ENABLED": "true",
        "OPS_NOTIFY_ONCALL_WEBHOOK_URL": "https://hooks.example/oncall",
    }.get(k, d)
    out = notify_ops_event(
        event="test",
        title="Alert",
        body="Details",
        settings=settings,
        dedup_key="oncall-test",
    )
    assert out.get("oncall") is True
    mock_oncall.assert_called_once()


def test_calendar_snapshot_buckets_by_msk_day():
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    with tempfile.TemporaryDirectory() as tmp:
        store = SequenceStore(Path(tmp) / "seq.db")
        store.init_db()
        msk = ZoneInfo("Europe/Moscow")
        today = datetime.now(msk).date()
        day2 = today + timedelta(days=2)
        day3 = today + timedelta(days=3)
        at2 = datetime(day2.year, day2.month, day2.day, 12, 0, tzinfo=msk).astimezone(timezone.utc)
        at3 = datetime(day3.year, day3.month, day3.day, 9, 0, tzinfo=msk).astimezone(timezone.utc)
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO sequence_leads(
                  email, company_id, contact_name, status, current_step,
                  next_action_at, subject_base, meta_json, created_at, updated_at
                ) VALUES (?, '1', 'Иван', 'active', 1, ?, 'subj', '{}', 'now', 'now')
                """,
                ("a@b.ru", at2.isoformat()),
            )
        first = [
            {
                "kind": "first_touch",
                "email": "c@d.ru",
                "next_step": 1,
                "next_label": "intro",
                "due": True,
                "next_slot_at": at3.isoformat(),
            }
        ]
        snap = store.calendar_snapshot(days=14, first_touch=first)
        assert snap["ok"] is True
        assert snap["timezone"] == "Europe/Moscow"
        assert len(snap["calendar"]) == 14
        by_date = {d["date"]: d for d in snap["calendar"]}
        assert by_date[day2.isoformat()]["count"] == 1
        assert by_date[day2.isoformat()]["items"][0]["email"] == "a@b.ru"
        assert by_date[day3.isoformat()]["count"] == 1
        assert by_date[day3.isoformat()]["items"][0]["kind"] == "first_touch"
        assert snap["totals"]["items"] >= 2

