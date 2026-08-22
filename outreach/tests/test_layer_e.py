"""Layer E: ops notify, consent ledger, sequence step analytics."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.analytics import build_sequence_step_report
from modules.consent import ConsentLedgerStore, record_consent_from_suppression
from ops_notify import OpsNotifyStore, notify_ops_event


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
