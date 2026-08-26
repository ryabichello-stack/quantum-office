"""Telegram Business delivery fields for sendDocument."""

from __future__ import annotations

from models import FetchedFile
import delivery


def test_send_telegram_includes_business_connection(monkeypatch):
    captured: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok":true,"result":{}}'

    def fake_urlopen(req, timeout=120):
        captured["url"] = req.full_url
        captured["body"] = req.data
        captured["content_type"] = req.headers.get("Content-type") or req.headers.get(
            "Content-Type"
        )
        return _Resp()

    monkeypatch.setattr(delivery, "TELEGRAM_BUSINESS_BOT_TOKEN", "BIZTOKEN")
    monkeypatch.setattr(delivery, "TELEGRAM_BOT_TOKEN", "PERSONAL")
    monkeypatch.setattr(delivery.urllib.request, "urlopen", fake_urlopen)

    f = FetchedFile(
        filename="demo.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
        source="local",
        path="demo.pdf",
    )
    ok, err = delivery.send_telegram(
        "555",
        f,
        caption="Презентация",
        business_connection_id="bc-123",
    )
    assert ok is True
    assert err == ""
    assert "BIZTOKEN" in captured["url"]
    assert b'name="business_connection_id"' in captured["body"]
    assert b"bc-123" in captured["body"]
    assert b'name="chat_id"' in captured["body"]
    assert b"555" in captured["body"]
