"""Layer G: inbox thread view + operator reply."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from modules.replies import ReplyInboxStore
from modules.replies.classify import classify_reply
from modules.replies.thread import build_inbox_thread, send_inbox_reply
from outbox import OutboxStore


def test_build_inbox_thread_orders_messages():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        inbox = ReplyInboxStore(tmp_path / "inbox.db")
        outbox = OutboxStore(tmp_path / "outbox.db")
        classified = classify_reply(subject="Re: test", body="Интересно")
        inbox.add(
            message_id="inbound-1",
            from_email="client@lombard.ru",
            subject="Re: test",
            preview="Интересно, перезвоните",
            classified=classified,
            outbox_id=None,
            company_id="99",
        )
        inbox.record_operator_reply(
            inbox_id=1,
            to_email="client@lombard.ru",
            subject="Re: test",
            body="Спасибо, свяжемся завтра",
            message_id="op-1",
            in_reply_to="inbound-1",
        )
        out = build_inbox_thread(1, inbox=inbox, outbox=outbox)
        assert out["ok"] is True
        assert out["peer_email"] == "client@lombard.ru"
        kinds = [m["kind"] for m in out["messages"]]
        assert "reply" in kinds
        assert "operator" in kinds


@patch("modules.replies.thread.send_email")
@patch("modules.replies.thread.smtp_configured", return_value=True)
def test_send_inbox_reply(mock_smtp_ok, mock_send):
    mock_send.return_value = "sent-mid-123"
    with tempfile.TemporaryDirectory() as tmp:
        inbox = ReplyInboxStore(Path(tmp) / "inbox.db")
        classified = classify_reply(subject="Re: hello", body="Да")
        row = inbox.add(
            message_id="inbound-abc",
            from_email="a@b.ru",
            subject="Re: hello",
            preview="Да",
            classified=classified,
        )
        assert row
        out = send_inbox_reply(int(row["id"]), body="Ответ оператора", inbox=inbox)
        assert out["ok"] is True
        assert out["message_id"] == "sent-mid-123"
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["to"] == "a@b.ru"
        assert kwargs["in_reply_to"] == "inbound-abc"
        assert kwargs["include_list_unsubscribe"] is False
        updated = inbox.get(int(row["id"]))
        assert updated and updated["processed"] == 1
