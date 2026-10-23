"""Unit tests for answer→greeting latency helper (no AVA/Asterisk required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import _greeting_latency_from_conversation  # noqa: E402


def test_answer_to_greeting_and_short_barge() -> None:
    # Mirrors call 1792675305.0 shape: ~14.25s silence then «Приём»
    start = "2026-10-22T13:21:56.436667+00:00"
    answer = 1792675316.436667
    greet = answer + 14.255
    user = greet + 0.002
    out = _greeting_latency_from_conversation(
        start_time=start,
        conversation=[
            {
                "role": "assistant",
                "content": "Здравствуйте, я секретарь Quantum",
                "timestamp": greet,
            },
            {"role": "user", "content": "Приём", "timestamp": user},
            {
                "role": "assistant",
                "content": "Labs…",
                "timestamp": greet + 9.0,
            },
        ],
    )
    assert out["answer_to_greeting_s"] == 14.255
    assert out["greeting_to_user_s"] == 0.002
    assert out["short_barge_in"] is True
    assert out["target_ok"] is False


def test_target_ok_under_1_2s() -> None:
    from datetime import datetime, timezone

    start_dt = datetime(2026, 10, 22, 13, 0, 0, tzinfo=timezone.utc)
    answer = start_dt.timestamp()
    out = _greeting_latency_from_conversation(
        start_time=start_dt.isoformat(),
        conversation=[
            {
                "role": "assistant",
                "content": "Здравствуйте, я секретарь Quantum Labs.",
                "timestamp": answer + 0.9,
            },
            {"role": "user", "content": "Слушаю", "timestamp": answer + 4.0},
        ],
    )
    assert out["answer_to_greeting_s"] == 0.9
    assert out["target_ok"] is True
    assert out["short_barge_in"] is True


def test_allo_variants_count_as_barge() -> None:
    out = _greeting_latency_from_conversation(
        start_time="2026-10-22T13:00:00+00:00",
        conversation=[
            {"role": "assistant", "content": "Здравствуйте", "timestamp": 1.0},
            {"role": "user", "content": "Аллё", "timestamp": 1.2},
        ],
    )
    assert out["short_barge_in"] is True
