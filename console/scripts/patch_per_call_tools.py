#!/usr/bin/env python3
"""Extend AVA per-call script patch: allow tools override from call_scripts JSON."""
from __future__ import annotations

from pathlib import Path

ENGINE = Path("/root/ava/src/engine.py")
MODELS = Path("/root/ava/src/core/models.py")


def patch_models() -> None:
    text = MODELS.read_text(encoding="utf-8")
    if "outbound_call_tools" in text:
        print("models tools already patched")
        return
    old = "    outbound_call_greeting: Optional[str] = None"
    if old not in text:
        raise SystemExit("models greeting field missing — run patch_per_call_script.py first")
    text = text.replace(
        old,
        old + "\n    outbound_call_tools: Optional[list] = None",
        1,
    )
    MODELS.write_text(text, encoding="utf-8")
    print("models tools patched")


def patch_engine_load() -> None:
    text = ENGINE.read_text(encoding="utf-8")
    if "outbound_call_tools" in text and "Per-call outbound tools loaded" in text:
        print("engine load tools already patched")
        return

    # After greeting/script assignment, also load tools from file payload / custom vars.
    needle = """                        if script_val:
                            session.outbound_call_script = script_val
                        if greet_val:
                            session.outbound_call_greeting = greet_val
                        if script_val or greet_val:
                            logger.info(
                                "Per-call outbound script loaded",
                                call_id=caller_channel_id,
                                script_chars=len(script_val or ""),
                                greeting_chars=len(greet_val or ""),
                                via_file=bool(script_file),
                            )"""
    insert = """                        if script_val:
                            session.outbound_call_script = script_val
                        if greet_val:
                            session.outbound_call_greeting = greet_val
                        tools_val = None
                        try:
                            if script_file:
                                from pathlib import Path as _P
                                fp = _P(script_file)
                                if fp.is_file():
                                    payload2 = json.loads(fp.read_text(encoding="utf-8"))
                                    if isinstance(payload2, dict) and isinstance(payload2.get("tools"), list):
                                        tools_val = [str(x).strip() for x in payload2["tools"] if str(x).strip()]
                            if not tools_val and isinstance(cv, dict):
                                raw_tools = cv.get("__tools__")
                                if isinstance(raw_tools, list):
                                    tools_val = [str(x).strip() for x in raw_tools if str(x).strip()]
                        except Exception:
                            tools_val = None
                        if tools_val:
                            session.outbound_call_tools = tools_val
                        if script_val or greet_val:
                            logger.info(
                                "Per-call outbound script loaded",
                                call_id=caller_channel_id,
                                script_chars=len(script_val or ""),
                                greeting_chars=len(greet_val or ""),
                                tools=tools_val or [],
                                via_file=bool(script_file),
                            )
                        elif tools_val:
                            logger.info(
                                "Per-call outbound tools loaded",
                                call_id=caller_channel_id,
                                tools=tools_val,
                            )"""
    if needle not in text:
        raise SystemExit("engine load tools needle missing")
    text = text.replace(needle, insert, 1)
    ENGINE.write_text(text, encoding="utf-8")
    print("engine load tools patched")


def patch_engine_apply() -> None:
    text = ENGINE.read_text(encoding="utf-8")
    marker = "per_call_tools = (getattr(session, \"outbound_call_tools\""
    if marker in text:
        print("engine apply tools already patched")
        return

    needle = """                        explicit_context_tools = list(getattr(context_config, "tools", None) or [])
                        if allowed_in_call_http_tool_names:
                            explicit_context_tools.extend(allowed_in_call_http_tool_names)
                        allowed = list(explicit_context_tools)"""
    insert = """                        explicit_context_tools = list(getattr(context_config, "tools", None) or [])
                        per_call_tools = getattr(session, "outbound_call_tools", None) or None
                        if isinstance(per_call_tools, list) and per_call_tools:
                            explicit_context_tools = [str(x).strip() for x in per_call_tools if str(x).strip()]
                            logger.info(
                                "Using per-call outbound tools",
                                call_id=call_id,
                                tools=explicit_context_tools,
                            )
                        if allowed_in_call_http_tool_names:
                            explicit_context_tools.extend(allowed_in_call_http_tool_names)
                        allowed = list(explicit_context_tools)"""
    if needle not in text:
        raise SystemExit("engine apply tools needle missing")
    text = text.replace(needle, insert, 1)
    ENGINE.write_text(text, encoding="utf-8")
    print("engine apply tools patched")


if __name__ == "__main__":
    patch_models()
    patch_engine_load()
    patch_engine_apply()
