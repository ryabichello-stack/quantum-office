#!/usr/bin/env python3
"""Warm pool = preconnected Live WebSocket only (no idle session.start).

Idle session.start + later commentary kick produced ~20s digital silence on
the phone (rms=0). Cold session.start+kick on answer speaks correctly.

V4 keeps TLS/WS connect warm, then on answer runs the same session.start +
greeting kick path as a cold call (Cedar voice, audible audio).

Requires V3 (silence gate / emit refresh) already applied.
Marker: QUANTUM_LIVE_WARM_V4
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

AVA = Path("/root/ava")
LIVE = AVA / "src" / "providers" / "openai_live.py"
ENGINE = AVA / "src" / "engine.py"
MARKER = "QUANTUM_LIVE_WARM_V4"


def _backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak-live-warm-v4")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())


def patch_live() -> str:
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text:
        return "live v4 already patched"
    if "QUANTUM_LIVE_WARM_V3" not in text:
        return "live: v3 missing — run harden_live_warm_silent_adopt.py first"

    # Replace warm_start with WS-only connect
    start = text.find("    async def warm_start(")
    if start < 0:
        return "live: warm_start missing"
    end = text.find("    async def adopt_for_call(", start)
    if end < 0:
        return "live: adopt_for_call after warm_start missing"

    new_warm = f'''    async def warm_start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """{MARKER}: preconnect Live WS only — no idle session.start.

        Idle session.start + delayed greeting kick emitted digital silence
        (~20s rms=0). On answer we session.start+kick on this warm socket.
        """
        await self.stop_session()
        self._call_id = "__warm__"
        self._closed = False
        self._warm_ready = False
        self._session_started.clear()
        self._input_rate_state = None
        self._output_resample_state = None
        self._first_audio_logged = False
        self._skip_leading_silence = True
        self._leading_silence_dropped_ms = 0.0
        self._heard_real_audio = False
        self._trailing_silence_ms = 0.0
        self._in_audio_burst = False
        self._context = dict(context or {{}})
        self._hangup_after_response = False
        self._user_transcript_buf = ""
        self._agent_transcript_buf = ""
        self._user_flush_task = None
        self._agent_flush_task = None
        self._farewell_waiting_for_audio_done = False
        self._user_requested_hangup = False
        self._forced_hangup_armed = False
        self._pending_tool_call_ids.clear()
        if "tools" in self._context:
            self._allowed_tools = [
                str(x).strip()
                for x in (self._context.get("tools") or [])
                if str(x).strip()
            ]
        else:
            self._allowed_tools = []
        self._wire_mode, _audio_format, self._provider_output_rate = self._resolve_wire_format()
        self._emit_encoding = self._engine_encoding()
        self._emit_rate = self._engine_rate()

        api_key = self._api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI Live warm pool")

        headers = {{"Authorization": f"Bearer {{api_key}}"}}
        org = getattr(self.config, "organization", None) or os.getenv("OPENAI_ORG_ID")
        project = getattr(self.config, "project_id", None) or os.getenv("OPENAI_PROJECT")
        if org:
            headers["OpenAI-Organization"] = str(org)
        if project:
            headers["OpenAI-Project"] = str(project)

        t0 = time.time()
        logger.info(
            "LIVE_WARM_CONNECT",
            extra={{"model": self._model(), "voice": self._voice(), "mode": "ws_only"}},
        )
        self.websocket = await websockets.connect(
            LIVE_WS_URL,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
        )
        # Detect remote close while idle; no session events until adopt.
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._warm_ready = True
        logger.info(
            "LIVE_WARM_READY",
            extra={{"warm_s": round(time.time() - t0, 3), "mode": "ws_only"}},
        )

'''
    text = text[:start] + new_warm + text[end:]

    # Replace adopt_for_call through _wait_greeting_energy (keep helper for energy)
    adopt_start = text.find("    async def adopt_for_call(")
    if adopt_start < 0:
        return "live: adopt missing after warm replace"
    health_start = text.find("\n    def is_warm_healthy(self)", adopt_start)
    if health_start < 0:
        return "live: is_warm_healthy after adopt missing"

    new_adopt = f'''    async def adopt_for_call(
        self, call_id: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """{MARKER}: session.start + greeting kick on preconnected warm WS."""
        ctx = dict(context or {{}})
        if not self.is_warm_healthy():
            await self.start_session(call_id, ctx)
            return False
        t0 = time.time()
        # Keep existing websocket; reset call state like start_session.
        self._call_id = call_id
        self._closed = False
        self._warm_ready = False
        self._session_started.clear()
        self._input_rate_state = None
        self._output_resample_state = None
        self._first_audio_logged = False
        self._skip_leading_silence = True
        self._leading_silence_dropped_ms = 0.0
        self._heard_real_audio = False
        self._trailing_silence_ms = 0.0
        self._in_audio_burst = False
        self._context = ctx
        self._hangup_after_response = False
        self._user_transcript_buf = ""
        self._agent_transcript_buf = ""
        self._user_flush_task = None
        self._agent_flush_task = None
        self._farewell_waiting_for_audio_done = False
        self._user_requested_hangup = False
        self._forced_hangup_armed = False
        self._pending_tool_call_ids.clear()
        self._wire_mode, audio_format, self._provider_output_rate = self._resolve_wire_format()
        # Engine applies transport overrides on config before adopt.
        self._emit_encoding = self._engine_encoding()
        self._emit_rate = self._engine_rate()
        if "tools" in ctx:
            self._allowed_tools = [
                str(x).strip() for x in (ctx.get("tools") or []) if str(x).strip()
            ]
        else:
            self._allowed_tools = []

        instructions = (
            (ctx.get("instructions") or ctx.get("prompt") or "")
            or (getattr(self.config, "instructions", None) or "")
        ).strip()
        greeting = (
            ctx.get("greeting") or getattr(self.config, "greeting", None) or ""
        ).strip()
        if greeting:
            instructions = (
                f"{{instructions}}\\n\\n"
                f"Сразу после соединения коротко поприветствуй одной фразой (без длинной паузы в начале), "
                f"затем слушай собеседника и отвечай. Текст приветствия: {{greeting}}"
            ).strip()
        if not instructions:
            instructions = (
                "Ты — живой телефонный ассистент Quantum Labs. Говори по-русски, коротко и тепло. "
                "Слушай собеседника и отвечай с минимальной задержкой."
            )
        if self._allowed_tools:
            tools_csv = ", ".join(self._allowed_tools)
            instructions = (
                instructions
                + "\\n\\n"
                + "Когда нужно проверить календарь, создать встречу, отправить письмо, "
                + "создать конференцию, ответить по базе знаний или завершить звонок — "
                + "используй инструменты: "
                + tools_csv
                + ". Если абонент просит завершить звонок — СРАЗУ вызови hangup_call."
            ).strip()

        tools_cfg: List[Dict[str, Any]] = []
        try:
            if self._allowed_tools:
                tools_cfg = self.tool_adapter.get_tools_config(list(self._allowed_tools)) or []
        except Exception:
            tools_cfg = []
        tool_choice = "auto" if tools_cfg else "none"
        session_cfg = {{
            "model": self._model(),
            "instructions": instructions,
            "audio": {{
                "format": audio_format,
                "output": {{"voice": self._voice()}},
            }},
            "delegation": {{
                "type": "responses",
                "responses": {{
                    "model": self._delegate_model(),
                    "tool_choice": tool_choice,
                    "parallel_tool_calls": False,
                    "tools": tools_cfg,
                }},
            }},
        }}
        try:
            if self._receive_task is None or self._receive_task.done():
                self._receive_task = asyncio.create_task(self._receive_loop())
            await self._send_json(
                {{
                    "type": "session.start",
                    "event_id": f"warm-adopt-{{call_id}}",
                    "session": session_cfg,
                }}
            )
            await asyncio.wait_for(self._session_started.wait(), timeout=8.0)
        except Exception:
            logger.warning(
                "LIVE_WARM_ADOPT_SESSION_FAILED",
                extra={{"call_id": call_id}},
                exc_info=True,
            )
            await self.start_session(call_id, ctx)
            return False

        await self._send_greeting_kick(call_id, greeting)
        await self._emit_audio_format(call_id)
        got_audio = await self._wait_greeting_energy(timeout_s=2.6)
        if not got_audio:
            logger.warning(
                "LIVE_WARM_SILENT_FALLBACK",
                extra={{
                    "call_id": call_id,
                    "wait_s": round(time.time() - t0, 3),
                    "emit_encoding": self._emit_encoding,
                    "mode": "ws_only",
                }},
            )
            await self.start_session(call_id, ctx)
            return False
        logger.info(
            "LIVE_WARM_ADOPT",
            extra={{
                "call_id": call_id,
                "adopt_s": round(time.time() - t0, 3),
                "greeting_chars": len(greeting),
                "emit_encoding": self._emit_encoding,
                "mode": "ws_only",
            }},
        )
        return True

    async def _wait_greeting_energy(self, timeout_s: float = 1.15) -> bool:
        """QUANTUM_LIVE_WARM_V3: True once Live emits non-silent audio after kick."""
        deadline = time.time() + float(timeout_s)
        while time.time() < deadline:
            if getattr(self, "_heard_real_audio", False):
                return True
            if getattr(self, "_closed", False) or self.websocket is None:
                return False
            await asyncio.sleep(0.02)
        return bool(getattr(self, "_heard_real_audio", False))
'''
    text = text[:adopt_start] + new_adopt + text[health_start + 1 :]  # keep leading newline via health

    # Fix: health_start pointed at "\n    def is_warm_healthy" — we sliced from +1 so we need the def
    # Actually text[health_start+1:] starts with "    def is_warm_healthy" — good.

    LIVE.write_text(text, encoding="utf-8")
    try:
        ast.parse(text)
    except SyntaxError as exc:
        return f"live: syntax error after v4: {exc}"
    return "live v4 patched"


def patch_engine() -> str:
    text = ENGINE.read_text(encoding="utf-8")
    if MARKER in text:
        return "engine v4 already patched"
    needle = "    # QUANTUM_LIVE_WARM_V3\n"
    if needle in text:
        text = text.replace(needle, f"    # QUANTUM_LIVE_WARM_V3\n    # {MARKER}\n", 1)
        ENGINE.write_text(text, encoding="utf-8")
        return "engine v4 marker added"
    helpers = "    # QUANTUM_LIVE_WARM_HELPERS\n"
    if helpers in text:
        text = text.replace(helpers, f"    # QUANTUM_LIVE_WARM_HELPERS\n    # {MARKER}\n", 1)
        ENGINE.write_text(text, encoding="utf-8")
        return "engine v4 marker added"
    return "engine: warm marker missing"


def main() -> int:
    if not LIVE.exists():
        print("AVA paths missing", file=sys.stderr)
        return 2
    _backup(LIVE)
    _backup(ENGINE)
    r1 = patch_live()
    r2 = patch_engine()
    print(r1)
    print(r2)
    ok = ("patched" in r1 or "already" in r1) and ("added" in r2 or "already" in r2)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
