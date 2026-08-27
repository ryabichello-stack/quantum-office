"""send_explain: remaining slots vs schedule / SMTP."""

from __future__ import annotations

from send_explain import _human_smtp_error, build_send_explain


class _FakeOutbox:
    def __init__(self):
        self._sent = 10

    def sent_today_count(self):
        return self._sent

    def connect(self):
        return _FakeConn()


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        if "count(*) from outbox" in s and "not_before <=" in s:
            return _Rows([(0,)])
        if "date(not_before)" in s and "group by" in s:
            return _Rows([("2026-08-28", 10)])
        if "status = 'failed'" in s or 'status = "failed"' in s or "status='failed'" in s:
            return _Rows(
                [
                    (
                        "lombard@adalit.ru",
                        "{'lombard@adalit.ru': (550, b'non-local recipient verification failed')}",
                        "2026-08-26T04:01:25+00:00",
                    )
                ]
            )
        return _Rows([])


class _Rows:
    def __init__(self, rows):
        self._rows = rows
        self._i = 0

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


def test_human_smtp():
    h = _human_smtp_error("{'x': (550, b'non-local recipient verification failed')}")
    assert "550" in h
    assert "non-local" in h.lower()


def test_build_send_explain_scheduled_ahead():
    ex = build_send_explain(_FakeOutbox(), None, daily_limit=15)
    assert ex["code"] == "has_failures" or ex["code"] == "scheduled_ahead" or "свободн" in ex["text"]
    assert ex["sent_today"] == 10
    assert ex["remaining_today"] == 5
    assert ex["next_scheduled_day"] == "2026-08-28"
    assert any("28.08.2026" in ln or "завтра" in ln.lower() or "28" in ln for ln in ex["lines"])
    assert any("adalit" in ln for ln in ex["lines"])
