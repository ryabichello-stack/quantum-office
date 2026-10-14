"""text-bot send_email tool → mailer /api/email/send."""

from __future__ import annotations

import json

import ava_client as ac


def test_send_email_in_owner_tools():
    names = {t["function"]["name"] for t in ac.tools_for_role("owner")}
    assert "send_email" in names


def test_send_email_guest_forbidden():
    out = json.loads(
        ac.run_tool(
            "send_email",
            {
                "to": "a@b.com",
                "subject": "Hi",
                "body": "Hello",
            },
            role="guest",
        )
    )
    assert out["ok"] is False
    assert out["error"] == "forbidden"


def test_send_email_posts_to_mailer(monkeypatch):
    monkeypatch.setattr(ac, "MAILER_BASE", "http://mailer.test")
    called: dict = {}

    def fake_post(url, body, *, timeout=30.0, brain_principal=None):
        called["url"] = url
        called["body"] = body
        return {
            "ok": True,
            "queued": True,
            "to": body["to"],
            "subject": body["subject"],
            "message": "queued",
        }

    monkeypatch.setattr(ac, "_post_json", fake_post)
    out = json.loads(
        ac.run_tool(
            "send_email",
            {
                "to": "client@example.com",
                "subject": "Презентация",
                "body": "Здравствуйте!",
                "attach_presentation": True,
            },
            role="owner",
        )
    )
    assert called["url"] == "http://mailer.test/api/email/send"
    assert called["body"]["to"] == "client@example.com"
    assert called["body"]["attach_presentation"] is True
    assert out["ok"] is True
    assert "owner_message" in out
    assert "client@example.com" in out["owner_message"]
