#!/usr/bin/env python3
"""Warm = session.start + paced mic keepalive; adopt = kick only (≤1.5s).

Root cause of 20s silence: idle Live session without input audio → kick emits
digital silence. Keepalive mic frames keep the TTS path alive.
"""
from __future__ import annotations

import ast
from pathlib import Path

LIVE = Path("/root/ava/src/providers/openai_live.py")
MARKER = "QUANTUM_LIVE_WARM_KEEPALIVE"


def main() -> int:
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text:
        print("already keepalive")
        return 0

    w0 = text.find("    async def warm_start(")
    h0 = text.find("\n    def is_warm_healthy(self)", w0)
    if w0 < 0 or h0 < 0:
        print("anchors missing")
        return 1

    block = f'''    async def warm_start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """{MARKER}: connect + session.start + mic keepalive (no greeting yet)."""
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
        self._warm_mic_task = None
        if "tools" in self._context:
            self._allowed_tools = [
                str(x).strip()
                for x in (self._context.get("tools") or [])
                if str(x).strip()
            ]
        else:
            self._allowed_tools = [
                "check_calendar",
                "create_calendar_event",
                "send_welcome_email",
                "send_email",
                "create_conference",
                "get_company_knowledge",
                "hangup_call",
            ]
        self._wire_mode, audio_format, self._provider_output_rate = self._resolve_wire_format()
        self._emit_encoding = self._engine_encoding()
        self._emit_rate = self._engine_rate()

        instructions = (
            (self._context.get("instructions") or self._context.get("prompt") or "")
            or (getattr(self.config, "instructions", None) or "")
            or (
                "Ты — живой телефонный ассистент Quantum Labs. Говори по-русски, коротко и тепло."
            )
        ).strip()
        instructions = (
            instructions
            + "\\n\\nWhen you receive a greeting kick / commentary to speak first, "
            + "immediately produce spoken audio in Russian — never stay silent."
        ).strip()

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
            extra={{"model": self._model(), "voice": self._voice(), "mode": "keepalive"}},
        )
        _proxy = _live_ws_proxy()
        self.websocket = await websockets.connect(
            LIVE_WS_URL,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
            **({{"proxy": _proxy}} if _proxy else {{}}),
        )
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
        await self._send_json(
            {{
                "type": "session.start",
                "event_id": f"warm-start-{{int(time.time()*1000)}}",
                "session": session_cfg,
            }}
        )
        self._receive_task = asyncio.create_task(self._receive_loop())
        try:
            await asyncio.wait_for(self._session_started.wait(), timeout=8.0)
        except asyncio.TimeoutError as exc:
            await self.stop_session()
            raise RuntimeError("OpenAI Live warm session.started timeout") from exc
        self._warm_mic_task = asyncio.create_task(self._warm_mic_keepalive())
        self._warm_ready = True
        logger.info(
            "LIVE_WARM_READY",
            extra={{"warm_s": round(time.time() - t0, 3), "mode": "keepalive"}},
        )

    async def _warm_mic_keepalive(self) -> None:
        """{MARKER}: paced silence so idle Live still emits real TTS on kick."""
        try:
            sil = audioop.lin2ulaw(b"\\x00\\x00" * 160, 2)
            b64 = base64.b64encode(sil).decode("ascii")
            while (
                getattr(self, "_warm_ready", False)
                and not getattr(self, "_closed", True)
                and self.websocket is not None
            ):
                await self._send_json(
                    {{"type": "session.input_audio.append", "audio": b64}}
                )
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.debug("Warm mic keepalive stopped", exc_info=True)

    async def adopt_for_call(
        self, call_id: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """{MARKER}: kick greeting on keepalive warm session (no reconnect)."""
        ctx = dict(context or {{}})
        if not (self.is_warm_healthy() and self._session_started.is_set()):
            await self.start_session(call_id, ctx)
            return False
        t0 = time.time()
        self._call_id = call_id
        self._context = ctx
        self._warm_ready = False
        # stop keepalive — real AudioSocket mic takes over
        task = getattr(self, "_warm_mic_task", None)
        self._warm_mic_task = None
        if task and not task.done():
            task.cancel()
        self._first_audio_logged = False
        self._skip_leading_silence = True
        self._leading_silence_dropped_ms = 0.0
        self._heard_real_audio = False
        self._trailing_silence_ms = 0.0
        self._in_audio_burst = False
        self._hangup_after_response = False
        self._user_transcript_buf = ""
        self._agent_transcript_buf = ""
        self._farewell_waiting_for_audio_done = False
        self._user_requested_hangup = False
        self._forced_hangup_armed = False
        self._pending_tool_call_ids.clear()
        self._emit_encoding = self._engine_encoding()
        self._emit_rate = self._engine_rate()
        if "tools" in ctx:
            self._allowed_tools = [
                str(x).strip() for x in (ctx.get("tools") or []) if str(x).strip()
            ]
        greeting = (
            ctx.get("greeting") or getattr(self.config, "greeting", None) or ""
        ).strip()
        prompt = (ctx.get("instructions") or ctx.get("prompt") or "").strip()
        await self._emit_audio_format(call_id)
        await self._send_greeting_kick(call_id, greeting)
        if prompt:
            try:
                await self._send_json(
                    {{
                        "type": "session.instructions.append",
                        "event_id": f"adopt-instr-{{call_id}}",
                        "delegation_id": None,
                        "content": prompt[:6000],
                    }}
                )
            except Exception:
                logger.debug("Warm adopt prompt append failed", exc_info=True)
        logger.info(
            "LIVE_WARM_ADOPT",
            extra={{
                "call_id": call_id,
                "adopt_s": round(time.time() - t0, 3),
                "greeting_chars": len(greeting),
                "emit_encoding": self._emit_encoding,
                "mode": "keepalive",
            }},
        )
        return True

'''
    text = text[:w0] + block + text[h0 + 1 :]

    # stop_session should cancel warm mic task
    old_stop = "    async def stop_session(self):\n        self._closed = True\n"
    new_stop = (
        "    async def stop_session(self):\n"
        "        self._closed = True\n"
        "        self._warm_ready = False\n"
        "        _wmt = getattr(self, \"_warm_mic_task\", None)\n"
        "        self._warm_mic_task = None\n"
        "        if _wmt and not _wmt.done():\n"
        "            _wmt.cancel()\n"
    )
    if old_stop in text and "_warm_mic_task" not in text[text.find("async def stop_session"): text.find("async def stop_session") + 400]:
        text = text.replace(old_stop, new_stop, 1)

    LIVE.write_text(text, encoding="utf-8")
    try:
        ast.parse(text)
    except SyntaxError as e:
        print("syntax", e)
        return 1
    print("OK", MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
