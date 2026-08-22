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
