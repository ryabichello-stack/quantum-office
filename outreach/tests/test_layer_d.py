"""Layer D: operator ops center (alerts + next actions)."""

from __future__ import annotations

from unittest.mock import MagicMock

from ops_center import build_ops_summary


class _Rt:
    def get_bool(self, key, default=False):
        return default

    def get(self, key, default=""):
        return default


def test_ops_mailbox_paused_alert():
    deliver = MagicMock()
    deliver.is_paused.return_value = (True, "bounce_spike")
    inbox = MagicMock()
    inbox.list_unprocessed.return_value = []
    inbox.counts.return_value = {"unprocessed": 0}
    seq = MagicMock()
    seq.counts.return_value = {"paused": 0}

    out = build_ops_summary(
        rt=_Rt(),
        deliverability=deliver,
        reply_inbox=inbox,
        sequences=seq,
        runner=MagicMock(),
        reply_watch={"imap_configured": True, "last_at": "2026-08-22T12:00:00+00:00"},
        callback_requests=[],
        queue={"due": 0},
        outbox_counts={"pending": 5},
    )
    assert any(a["id"] == "mailbox_paused" for a in out["alerts"])
    assert any(a["kind"] == "mailbox_paused" for a in out["actions"])


def test_ops_inbox_action_priority():
    deliver = MagicMock()
    deliver.is_paused.return_value = (False, "")
    inbox = MagicMock()
    inbox.list_unprocessed.return_value = [
        {
            "id": 1,
            "classification": "positive_interest",
            "from_email": "ceo@example.com",
            "subject": "Интересно",
            "created_at": "2026-08-22T10:00:00+00:00",
        }
    ]
    inbox.counts.return_value = {"unprocessed": 1}
    seq = MagicMock()
    seq.counts.return_value = {"paused": 0}

    out = build_ops_summary(
        rt=_Rt(),
        deliverability=deliver,
        reply_inbox=inbox,
        sequences=seq,
        runner=MagicMock(),
        reply_watch={"imap_configured": True, "enabled": True, "interval_seconds": 120},
        callback_requests=[],
        queue={"due": 2},
        outbox_counts={"pending": 0},
    )
    kinds = [a["kind"] for a in out["actions"]]
    assert "inbox_reply" in kinds
    assert out["actions"][0]["severity"] == "high"
