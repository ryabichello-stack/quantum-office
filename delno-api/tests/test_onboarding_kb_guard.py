"""After build_kb_draft, setup_mark/upload must not steal the turn."""

from __future__ import annotations

from app.operator.agent import _kb_draft_user_reply, _prefer_kb_draft_in_reply


def test_prefer_draft_over_status_when_sections_missing():
    draft = "## 1. Кто мы\nQuantum\n\n## 2. Услуги\nВыплаты\n" + ("x" * 800)
    tools = [
        {
            "tool": "office.build_kb_draft",
            "ok": True,
            "full_message": "Собрал\n\n" + draft,
            "message": "short",
        },
        {"tool": "hermes.setup_mark", "ok": False, "error": "blocked_until_kb_shown"},
    ]
    out = _prefer_kb_draft_in_reply("Готов выполнить: hermes.setup mark.", tools)
    assert "## 1. Кто мы" in out
    assert _kb_draft_user_reply(tools)
