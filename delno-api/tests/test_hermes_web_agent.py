"""Hermes cabinet: search HTML parse + debug failure surfacing."""

from __future__ import annotations

from app.operator.agent import _format_debug_failures, _with_debug_failures
from app.services.web_browser import _parse_ddg_html


def test_parse_ddg_html_result_a():
    html = """
    <div class="result results_links">
      <a rel="nofollow" class="result__a" href="https://example.com/a">Title A</a>
    </div>
    <div class="result results_links">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb">Title B</a>
    </div>
    """
    items = _parse_ddg_html(html, limit=5)
    assert len(items) == 2
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["title"] == "Title A"
    assert items[1]["url"] == "https://example.com/b"


def test_debug_failures_block_lists_tool_errors(monkeypatch):
    monkeypatch.setattr("app.operator.agent._hermes_debug_failures", lambda: True)
    block = _format_debug_failures(
        tools=[
            {"tool": "web.search", "ok": False, "error": "search_failed", "detail": "SSL boom"},
            {"tool": "get_knowledge", "ok": True, "message": "ok"},
            {"tool": "get_knowledge", "ok": False, "blocked": True, "error": "web_only"},
        ],
        llm_error="openai_http_502",
    )
    assert "— отладка (сбои) —" in block
    assert "LLM: openai_http_502" in block
    assert "web.search: SSL boom" in block
    assert "get_knowledge: заблокирован" in block
    assert "get_knowledge: ok" not in block

    reply = _with_debug_failures(
        "Краткий ответ",
        tools=[{"tool": "web.fetch", "ok": False, "error": "timeout"}],
    )
    assert reply.startswith("Краткий ответ")
    assert "web.fetch: timeout" in reply
