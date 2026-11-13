"""OpenAI function names must match ^[a-zA-Z0-9_-]+$."""

from __future__ import annotations

import re

from app.operator.tools import register_builtin_tools
from app.operator.tools.registry import registry

_OPENAI_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def test_openai_specs_use_safe_names_and_resolve_back():
    register_builtin_tools()
    specs = registry.list_openai_specs(names=["web.search", "calls.list", "get_knowledge"])
    names = [s["function"]["name"] for s in specs]
    assert "web_search" in names
    assert "calls_list" in names
    assert "get_knowledge" in names
    for n in names:
        assert _OPENAI_NAME.match(n), n
    assert registry.resolve_openai_name("web_search") == "web.search"
    assert registry.resolve_openai_name("calls_list") == "calls.list"
    assert registry.resolve_openai_name("get_knowledge") == "get_knowledge"
