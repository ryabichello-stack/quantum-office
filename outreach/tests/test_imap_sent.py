"""Tests for IMAP save-sent helpers (no live Mail.ru)."""

from __future__ import annotations

import imaplib
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

from imap_sent import (
    DEFAULT_FOLDER,
    append_sent_copy,
    encode_imap_utf7,
    ensure_mailbox_folder,
    imap_save_sent_enabled,
    sent_folder_name,
)


def test_encode_imap_utf7_ascii_passthrough():
    assert encode_imap_utf7("Outreach") == "Outreach"
    assert encode_imap_utf7("A&B") == "A&-B"


def test_encode_imap_utf7_cyrillic():
    enc = encode_imap_utf7("Рассылка")
    assert enc.startswith("&")
    assert enc.endswith("-")
    assert "Рассылка" not in enc


def test_sent_folder_env(monkeypatch):
    monkeypatch.delenv("IMAP_SENT_FOLDER", raising=False)
    assert sent_folder_name() == DEFAULT_FOLDER
    monkeypatch.setenv("IMAP_SENT_FOLDER", "Outreach Sent")
    assert sent_folder_name() == "Outreach Sent"


def test_imap_save_sent_enabled(monkeypatch):
    monkeypatch.setenv("MAIL_USERNAME", "office@quantumlabs.ru")
    monkeypatch.setenv("MAIL_PASSWORD", "x")
    monkeypatch.setenv("IMAP_SAVE_SENT", "true")
    assert imap_save_sent_enabled() is True
    monkeypatch.setenv("IMAP_SAVE_SENT", "false")
    assert imap_save_sent_enabled() is False


def test_ensure_mailbox_folder_creates():
    imap = MagicMock()
    # first select fails, create ok
    imap.select.side_effect = [("NO", [b"no"]), ("OK", [b"1"])]
    imap.create.return_value = ("OK", [b""])
    name = ensure_mailbox_folder(imap, "Рассылка")
    assert name
    assert imap.create.called


def test_append_sent_copy_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("IMAP_SAVE_SENT", "false")
    msg = MIMEText("hi", "plain", "utf-8")
    out = append_sent_copy(msg)
    assert out.get("skipped") is True


def test_append_sent_copy_ok(monkeypatch):
    monkeypatch.setenv("IMAP_SAVE_SENT", "true")
    monkeypatch.setenv("MAIL_USERNAME", "office@quantumlabs.ru")
    monkeypatch.setenv("MAIL_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_HOST", "imap.mail.ru")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_SENT_FOLDER", "Рассылка")

    fake = MagicMock()
    fake.login.return_value = ("OK", [b""])
    fake.select.return_value = ("OK", [b"1"])
    fake.create.return_value = ("OK", [b""])
    fake.append.return_value = ("OK", [b""])
    fake.logout.return_value = ("OK", [b""])

    msg = MIMEText("body", "plain", "utf-8")
    msg["From"] = "office@quantumlabs.ru"
    msg["To"] = "a@b.ru"
    msg["Subject"] = "test"

    with patch("imap_sent.imaplib.IMAP4_SSL", return_value=fake):
        with patch("imap_sent.ensure_mailbox_folder", return_value="&BB4EQgQ,BDAEOwRO-"):
            out = append_sent_copy(msg)

    assert out.get("ok") is True
    assert out.get("folder") == "Рассылка"
    assert fake.append.called
    args = fake.append.call_args[0]
    assert args[1] == "(\\Seen)"
    assert isinstance(args[3], (bytes, bytearray))
    assert b"Subject: test" in args[3] or b"test" in args[3]
