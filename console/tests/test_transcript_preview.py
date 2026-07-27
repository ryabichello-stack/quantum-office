"""Console transcript preview formatting."""

from __future__ import annotations

import json

from console.transcript_format import format_transcript_preview


def test_format_transcript_preview_human():
    hist = json.dumps(
        [
            {"role": "assistant", "content": "Алло, это Денис"},
            {"role": "user", "content": "Да, слушаю"},
        ],
        ensure_ascii=False,
    )
    preview = format_transcript_preview(hist)
    assert "AVA:" in preview
    assert "Клиент:" in preview
    assert "Да, слушаю" in preview
    assert "{" not in preview
