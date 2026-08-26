"""Tests for Telegram Panel stats helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from tg_panel import (
    build_outreach_stats,
    chat_allowed,
    format_stats_text,
    validate_webapp_init_data,
)


class _FakeSettings(dict):
    def get(self, key, default=""):
        return super().get(key, default)


class _FakeOutbox:
    def sent_today_count(self):
        return 3

    def counts(self):
        return {"pending": 12, "sent": 18}


def test_chat_allowed():
    s = _FakeSettings(
        {
            "OPS_NOTIFY_TELEGRAM_CHAT_ID": "963782",
            "OPS_NOTIFY_TELEGRAM_ALLOW_CHATS": "111,222",
        }
    )
    assert chat_allowed("963782", s)
    assert chat_allowed(111, s)
    assert not chat_allowed("999", s)


def test_build_and_format_stats():
    s = _FakeSettings(
        {
            "OUTREACH_RUN_STATE": "playing",
            "OUTREACH_DAILY_LIMIT": "15",
            "OUTREACH_DELAY_MIN_SECONDS": "600",
            "OUTREACH_DELAY_MAX_SECONDS": "900",
            "TRACKING_PUBLIC_BASE": "https://a.47z.ru/_ava_outreach",
        }
    )
    stats = build_outreach_stats(
        settings=s,
        outbox=_FakeOutbox(),
        runner_status=lambda: {"state": "playing"},
        queue_snapshot=lambda: {"counts": {"followups_due": 2, "first_touch_in_window": 1}},
    )
    assert stats["sent_today"] == 3
    assert stats["pending"] == 12
    assert stats["delay_min_min"] == 10.0
    text = format_stats_text(stats)
    assert "Идёт" in text
    assert "10.0–15.0 мин" in text


def test_validate_webapp_init_data_ok():
    token = "123456:ABCDEF"
    user = json.dumps({"id": 963782, "username": "op"}, separators=(",", ":"))
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE",
        "user": user,
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    init_data = urlencode(fields)
    out = validate_webapp_init_data(init_data, token)
    assert out["ok"] is True
    assert out["user_id"] == "963782"


def test_validate_webapp_init_data_bad_hash():
    out = validate_webapp_init_data("auth_date=1&hash=deadbeef", "token")
    assert out["ok"] is False
