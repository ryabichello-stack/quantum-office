#!/usr/bin/env python3
"""Restore reliable ≤1.5s Live greeting path (no silent-fallback tax).

Applies on top of QUANTUM_LIVE_WARM_V2:
  - warm_start = WS preconnect only (idle session.start caused silent TTS)
  - adopt = session.start + greeting kick on warm WS, emit refresh to transport
  - ulaw silence gate (do not stream digital silence to the phone)
  - NEVER wait-for-energy then cold-restart (that caused ~15s delays)

Marker: QUANTUM_LIVE_WARM_FAST
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LIVE = Path("/root/ava/src/providers/openai_live.py")
MARKER = "QUANTUM_LIVE_WARM_FAST"


def main() -> int:
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text:
        print("already patched")
        return 0
    if "QUANTUM_LIVE_WARM" not in text:
        print("warm v1/v2 missing", file=sys.stderr)
        return 1

    # --- Replace warm_start through end of adopt_for_call (before is_warm_healthy or send_audio) ---
    w0 = text.find("    async def warm_start(")
    if w0 < 0:
        print("warm_start missing", file=sys.stderr)
        return 1
    # Prefer is_warm_healthy if present, else send_audio
    h0 = text.find("\n    def is_warm_healthy(self)", w0)
    if h0 < 0:
        h0 = text.find("\n    async def send_audio(", w0)
    if h0 < 0:
        print("anchor after adopt missing", file=sys.stderr)
        return 1

    block = f'''    async def warm_start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """{MARKER}: preconnect Live WebSocket only (no idle session.start)."""
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
        self._allowed_tools = []
        if "tools" in self._context:
            self._allowed_tools = [
                str(x).strip()
                for x in (self._context.get("tools") or [])
                if str(x).strip()
            ]
        self._wire_mode, _fmt, self._provider_output_rate = self._resolve_wire_format()
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
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._warm_ready = True
        logger.info(
            "LIVE_WARM_READY",
            extra={{"warm_s": round(time.time() - t0, 3), "mode": "ws_only"}},
        )

    async def adopt_for_call(
        self, call_id: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """{MARKER}: session.start+kick on warm WS; no wait/cold-restart tax."""
        ctx = dict(context or {{}})
        if not self.is_warm_healthy():
            await self.start_session(call_id, ctx)
            return False
        t0 = time.time()
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
        # Engine applied transport overrides on config before adopt.
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
                f"Сразу после соединения коротко поприветствуй одной фразой "
                f"(без длинной паузы в начале), затем слушай. Текст: {{greeting}}"
            ).strip()
        if not instructions:
            instructions = (
                "Ты — живой телефонный ассистент Quantum Labs. "
                "Говори по-русски, коротко и тепло."
            )
        if self._allowed_tools:
            instructions = (
                instructions
                + "\\n\\nИспользуй инструменты когда нужно: "
                + ", ".join(self._allowed_tools)
                + ". Прощание → hangup_call."
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

'''
    # Keep is_warm_healthy if we cut before it; if cut before send_audio, ensure helper exists
    if "def is_warm_healthy" not in text[h0 : h0 + 80]:
        block += f'''    def is_warm_healthy(self) -> bool:
        """{MARKER}: warm WS still open."""
        if not getattr(self, "_warm_ready", False) or getattr(self, "_closed", True):
            return False
        ws = getattr(self, "websocket", None)
        if ws is None:
            return False
        try:
            if getattr(ws, "close_code", None) is not None:
                return False
            state = getattr(ws, "state", None)
            if state is not None:
                name = getattr(state, "name", None) or str(state)
                if "OPEN" not in str(name):
                    return False
        except Exception:
            return False
        return True

'''

    text = text[:w0] + block + text[h0 + 1 :]  # drop leading newline from anchor

    # Silence gate for ulaw emit
    old_gate = '''            if self._emit_encoding in _PCM_TARGETS and len(outbound) >= 4:
                try:
                    rms = audioop.rms(outbound, 2)
                except Exception:
                    rms = 9999
                frame_ms = (len(outbound) / 2) / float(self._emit_rate or 8000) * 1000.0'''
    new_gate = f'''            # {MARKER}: gate ulaw too — digital silence must not hit AudioSocket
            pcm_for_rms = None
            try:
                if self._emit_encoding in _PCM_TARGETS and len(outbound) >= 4:
                    pcm_for_rms = outbound
                elif self._emit_encoding in _ULAW_TARGETS and len(outbound) >= 2:
                    pcm_for_rms = audioop.ulaw2lin(outbound, 2)
            except Exception:
                pcm_for_rms = None
            if pcm_for_rms is not None and len(pcm_for_rms) >= 4:
                try:
                    rms = audioop.rms(pcm_for_rms, 2)
                except Exception:
                    rms = 9999
                frame_ms = (len(pcm_for_rms) / 2) / float(self._emit_rate or 8000) * 1000.0'''
    if old_gate not in text:
        print("silence gate needle missing", file=sys.stderr)
        return 1
    text = text.replace(old_gate, new_gate, 1)
    # Fix the if condition that followed — was `if self._emit_encoding in _PCM_TARGETS`
    # After replace we have `if pcm_for_rms is not None` body starting with rms=...
    # but the original still has the structure inside the PCM if. Need to verify.

    # The original structure was:
    # if PCM:
    #   try rms...
    #   frame_ms...
    #   if not heard...
    # We replaced the start of the if body incorrectly - we replaced INSIDE the if condition block
    # Actually we replaced:
    #   if self._emit_encoding in _PCM_TARGETS and len(outbound) >= 4:
    #       try: rms...
    #       frame_ms...
    # with:
    #   # comment
    #   pcm_for_rms = ...
    #   if pcm_for_rms is not None:
    #       try rms...
    #       frame_ms...
    # So the old `if PCM:` line is gone and replaced by new if - good.
    # But wait - old_gate didn't include the `if self._emit_encoding` line!
    # Looking at old_gate - it starts with `if self._emit_encoding in _PCM_TARGETS` - YES it does.

    LIVE.write_text(text, encoding="utf-8")
    try:
        ast.parse(text)
    except SyntaxError as e:
        print(f"syntax error: {e}", file=sys.stderr)
        return 1
    if "SILENT_FALLBACK" in text:
        print("WARNING: SILENT_FALLBACK still present", file=sys.stderr)
    print("OK", MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
