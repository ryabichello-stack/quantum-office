"""Tests for multi-mailbox IMAP account discovery."""

from brain_platform.ingest import mail


def test_configured_mail_accounts_primary_and_mail2(monkeypatch):
    monkeypatch.setenv("MAIL_USERNAME", "office@quantumlabs.ru")
    monkeypatch.setenv("MAIL_PASSWORD", "p1")
    monkeypatch.setenv("IMAP_HOST", "imap.mail.ru")
    monkeypatch.setenv("MAIL2_USERNAME", "rdv@quantumlabs.ru")
    monkeypatch.setenv("MAIL2_PASSWORD", "p2")
    monkeypatch.delenv("MAIL3_USERNAME", raising=False)

    accounts = mail.configured_mail_accounts()
    assert [a.username for a in accounts] == [
        "office@quantumlabs.ru",
        "rdv@quantumlabs.ru",
    ]
    assert mail.imap_configured() is True
    assert mail.imap_account_usernames() == [
        "office@quantumlabs.ru",
        "rdv@quantumlabs.ru",
    ]


def test_configured_mail_accounts_skips_incomplete(monkeypatch):
    monkeypatch.setenv("MAIL_USERNAME", "office@quantumlabs.ru")
    monkeypatch.setenv("MAIL_PASSWORD", "p1")
    monkeypatch.setenv("MAIL2_USERNAME", "rdv@quantumlabs.ru")
    monkeypatch.delenv("MAIL2_PASSWORD", raising=False)

    accounts = mail.configured_mail_accounts()
    assert [a.username for a in accounts] == ["office@quantumlabs.ru"]
