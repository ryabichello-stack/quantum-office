"""Hermes SSE → cabinet actions, and tenant isolation for run ids."""

from app.services.hermes_nous.live_events import (
    format_sse,
    iter_sse_blocks,
    map_hermes_event,
    normalize_tool_name,
    parse_sse_block,
    safe_preview,
    tenant_may_read_run,
)


def test_normalize_mcp_tool_names():
    assert normalize_tool_name("mcp__delno_office__web_research") == "web.research"
    assert normalize_tool_name("mcp__delno_office__phones_provision") == "phones.provision"
    assert normalize_tool_name("web.search") == "web.search"
    assert normalize_tool_name("credentials.open_form") == "credentials.open_form"


def test_tool_started_and_between_and_terminal():
    started = map_hermes_event(
        "tool.started",
        {"tool": "mcp__delno_office__web_search", "preview": "dlno.ru", "tool_call_id": "abc"},
    )
    assert started["phase"] == "tool"
    assert started["tool"] == "web.search"
    assert started["preview"] == "dlno.ru"
    assert started["tool_call_id"] == "abc"

    between = map_hermes_event("tool.completed", {"tool": "web.search", "tool_call_id": "abc"})
    assert between["phase"] == "between"

    thinking = map_hermes_event("reasoning.available", {"preview": "сверяю факты"})
    assert thinking["phase"] == "thinking"

    done = map_hermes_event("run.completed", {"status": "completed"})
    assert done["phase"] == "terminal"


def test_preview_drops_secrets():
    assert safe_preview("обычный запрос") == "обычный запрос"
    assert safe_preview("api_key=sk-secret") is None
    assert safe_preview("password=hunter2") is None


def test_sse_parser_and_frame():
    raw = "event: tool.started\ndata: {\"tool\": \"phones.provision\", \"tool_call_id\": \"1\"}\n\n"
    events = list(iter_sse_blocks(iter([raw])))
    assert events[0][0] == "tool.started"
    assert events[0][1]["tool"] == "phones.provision"
    name, data = parse_sse_block("event: reasoning.available\ndata: {}")
    assert name == "reasoning.available"
    frame = format_sse("action", {"phase": "thinking"})
    assert frame.startswith("event: action\n")
    assert "Думаю" not in frame or "phase" in frame


def test_other_tenant_cannot_read_run():
    assert tenant_may_read_run(
        owner_tenant_id="tenant-a",
        caller_tenant_id="tenant-a",
        stored_run_id="run-1",
        requested_id="run-1",
    )
    assert not tenant_may_read_run(
        owner_tenant_id="tenant-a",
        caller_tenant_id="tenant-b",
        stored_run_id="run-1",
        requested_id="run-1",
    )
    assert not tenant_may_read_run(
        owner_tenant_id="tenant-a",
        caller_tenant_id="tenant-a",
        stored_run_id="run-1",
        requested_id="run-2",
    )
