"""Unit checks for /api/email/send request model (no SMTP)."""

from __future__ import annotations

from pydantic import ValidationError

from mailer.main import SendEmailRequest


def test_send_email_request_ok():
    req = SendEmailRequest(
        to="client@example.com",
        subject="Тест",
        body="Здравствуйте!",
        attach_presentation=True,
    )
    assert req.to == "client@example.com"
    assert req.attach_presentation is True


def test_send_email_request_requires_fields():
    try:
        SendEmailRequest(to="a@b.c", subject="", body="x")
        assert False, "expected validation error"
    except ValidationError:
        pass


def test_attach_presentation_string_coercion():
    assert SendEmailRequest(
        to="a@b.co", subject="s", body="b", attach_presentation="true"
    ).attach_presentation is True
    assert SendEmailRequest(
        to="a@b.co", subject="s", body="b", attach_presentation="false"
    ).attach_presentation is False
    assert SendEmailRequest(
        to="a@b.co", subject="s", body="b", attach_presentation="yes"
    ).attach_presentation is True
