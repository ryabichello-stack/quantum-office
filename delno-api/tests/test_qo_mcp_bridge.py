"""Smoke: archived Quantum Office MCP catalog registers into ToolRegistry."""

from __future__ import annotations

from app.operator.tools import register_builtin_tools
from app.operator.tools.qo_mcp_bridge import qo_mcp_cabinet_tools
from app.operator.tools.registry import registry


def test_qo_mcp_tools_register():
    register_builtin_tools()
    cabinet = qo_mcp_cabinet_tools()
    assert len(cabinet) >= 70
    for name in ("kb.search", "messenger.send", "telephony.dial", "outreach.dashboard", "files.list"):
        assert registry.get(name) is not None, name
        assert name in cabinet
    # Aliases skipped — DELNO owns calls.*
    assert "calls.dial" not in cabinet
