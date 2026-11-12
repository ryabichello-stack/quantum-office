"""Hermes cabinet: search HTML parse + agent stop policy + debug."""

from __future__ import annotations

from app.operator.agent import (
    _cabinet_agent_max_rounds,
    _cabinet_agent_max_tokens,
    _cabinet_agent_no_progress_limit,
    _completion_token_total,
    _format_debug_failures,
    _tool_call_fingerprint,
    _with_debug_failures,
)
from app.services.web_browser import _parse_ddg_html


def test_agent_stop_policy_defaults():
    assert 4 <= _cabinet_agent_max_rounds() <= 200
    assert _cabinet_agent_no_progress_limit() >= 2
    assert _cabinet_agent_max_tokens() >= 0


def test_tool_fingerprint_stable_and_sensitive():
    a = _tool_call_fingerprint("web.search", {"query": "выплаты", "limit": 5})
    b = _tool_call_fingerprint("web.search", {"limit": 5, "query": "выплаты"})
    c = _tool_call_fingerprint("web.search", {"query": "другое", "limit": 5})
    assert a == b
    assert a != c


def test_completion_token_total():
    assert _completion_token_total({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}) == 15
    assert _completion_token_total({"usage": {"total_tokens": 42}}) == 42
    assert _completion_token_total({}) == 0


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
