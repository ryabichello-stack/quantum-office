#!/usr/bin/env python3
"""Warm-pool OpenAI Live so greeting uses the same Cedar voice within ~1.5s.

Idle ai_engine keeps one Live WS + session.started ready. On answer we adopt it
and only send the greeting kick (no 6s cold connect on the call path).

Idempotent marker: QUANTUM_LIVE_WARM.
"""
from __future__ import annotations

import sys
from pathlib import Path

AVA = Path("/root/ava")
LIVE = AVA / "src" / "providers" / "openai_live.py"
ENGINE = AVA / "src" / "engine.py"
MARKER = "QUANTUM_LIVE_WARM"


def _backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak-live-warm")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())


def patch_live() -> str:
    if not LIVE.is_file():
        return f"skip live: missing {LIVE}"
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text:
        return "live already patched"

    # Track warm state on the instance
    init_needle = "        self._full_config = None\n"
    init_insert = (
        "        self._full_config = None\n"
        f"        self._warm_ready = False  # {MARKER}\n"
    )
    if init_needle not in text:
        return "live: init needle missing"
    text = text.replace(init_needle, init_insert, 1)

    # Extract greeting kick into helper + add warm_start / adopt_for_call
    old_kick = '''        # Live does not reliably auto-greet on answer. Kick with instructions.append
        # (+ commentary.append). Do NOT use bare response.create — that stalls Live.
        if greeting:
            try:
                greet_instr = (
                    "Speak first immediately in Russian before the caller says anything. "
                    "Do not wait for the caller. Say exactly this greeting once, then pause "
                    f"and listen: {greeting}"
                )
                await self._send_json(
                    {
                        "type": "session.instructions.append",
                        "event_id": f"greet-instr-{call_id}",
                        "delegation_id": None,
                        "content": greet_instr,
                    }
                )
                await self._send_json(
                    {
                        "type": "session.commentary.append",
                        "event_id": f"greet-kick-{call_id}",
                        "delegation_id": None,
                        "content": (
                            "Begin speaking the greeting now. "
                            f"Say exactly: {greeting}"
                        ),
                    }
                )
                logger.info(
                    "OpenAI Live greeting kick sent",
                    extra={"call_id": call_id, "greeting_chars": len(greeting)},
                )
            except Exception:
                logger.warning(
                    "OpenAI Live greeting kick failed",
                    extra={"call_id": call_id},
                    exc_info=True,
                )

        if self.on_event:
            try:
                await self.on_event(
                    {
                        "type": "ProviderAudioFormat",
                        "call_id": call_id,
                        "encoding": self._emit_encoding,
                        "sample_rate": self._emit_rate,
                    }
                )
            except Exception:
                logger.debug("Failed to emit ProviderAudioFormat", exc_info=True)

    async def send_audio('''

    new_kick = f'''        # Live does not reliably auto-greet on answer. Kick with instructions.append
        # (+ commentary.append). Do NOT use bare response.create — that stalls Live.
        await self._send_greeting_kick(call_id, greeting)
        await self._emit_audio_format(call_id)

    async def _send_greeting_kick(self, call_id: str, greeting: str) -> None:
        """{MARKER}: shared greeting kick for cold start and warm adopt."""
        greeting = (greeting or "").strip()
        if not greeting:
            return
        try:
            greet_instr = (
                "Speak first immediately in Russian before the caller says anything. "
                "Do not wait for the caller. Say exactly this greeting once, then pause "
                f"and listen: {{greeting}}"
            )
            await self._send_json(
                {{
                    "type": "session.instructions.append",
                    "event_id": f"greet-instr-{{call_id}}",
                    "delegation_id": None,
                    "content": greet_instr,
                }}
            )
            await self._send_json(
                {{
                    "type": "session.commentary.append",
                    "event_id": f"greet-kick-{{call_id}}",
                    "delegation_id": None,
                    "content": (
                        "Begin speaking the greeting now. "
                        f"Say exactly: {{greeting}}"
                    ),
                }}
            )
            logger.info(
                "OpenAI Live greeting kick sent",
                extra={{"call_id": call_id, "greeting_chars": len(greeting)}},
            )
        except Exception:
            logger.warning(
                "OpenAI Live greeting kick failed",
                extra={{"call_id": call_id}},
                exc_info=True,
            )

    async def _emit_audio_format(self, call_id: str) -> None:
        if not self.on_event:
            return
        try:
            await self.on_event(
                {{
                    "type": "ProviderAudioFormat",
                    "call_id": call_id,
                    "encoding": self._emit_encoding,
                    "sample_rate": self._emit_rate,
                }}
            )
        except Exception:
            logger.debug("Failed to emit ProviderAudioFormat", exc_info=True)

    async def warm_start(self, context: Optional[Dict[str, Any]] = None) -> None:
        """{MARKER}: connect + session.start without greeting (idle standby)."""
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
        self._wire_mode, audio_format, self._provider_output_rate = self._resolve_wire_format()
        self._emit_encoding = self._engine_encoding()
        self._emit_rate = self._engine_rate()

        instructions = (
            (self._context.get("instructions") or self._context.get("prompt") or "")
            or (getattr(self.config, "instructions", None) or "")
            or (
                "Ты — живой телефонный ассистент Quantum Labs. Говори по-русски, коротко и тепло. "
                "Слушай собеседника и отвечай с минимальной задержкой."
            )
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
            extra={{"model": self._model(), "voice": self._voice()}},
        )
        self.websocket = await websockets.connect(
            LIVE_WS_URL,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
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
        self._warm_ready = True
        logger.info(
            "LIVE_WARM_READY",
            extra={{"warm_s": round(time.time() - t0, 3)}},
        )

    async def adopt_for_call(
        self, call_id: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """{MARKER}: bind a warm session to a real call and kick greeting (same Cedar voice)."""
        ctx = dict(context or {{}})
        if not (
            self._warm_ready
            and self.websocket is not None
            and self._session_started.is_set()
            and not self._closed
        ):
            await self.start_session(call_id, ctx)
            return False
        t0 = time.time()
        self._call_id = call_id
        self._context = ctx
        self._warm_ready = False
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
        if "tools" in ctx:
            self._allowed_tools = [
                str(x).strip() for x in (ctx.get("tools") or []) if str(x).strip()
            ]
        greeting = (
            ctx.get("greeting") or getattr(self.config, "greeting", None) or ""
        ).strip()
        prompt = (
            ctx.get("instructions") or ctx.get("prompt") or ""
        ).strip()
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
        await self._send_greeting_kick(call_id, greeting)
        await self._emit_audio_format(call_id)
        logger.info(
            "LIVE_WARM_ADOPT",
            extra={{
                "call_id": call_id,
                "adopt_s": round(time.time() - t0, 3),
                "greeting_chars": len(greeting),
            }},
        )
        return True

    async def send_audio('''

    if old_kick not in text:
        return "live: greeting kick needle missing"
    text = text.replace(old_kick, new_kick, 1)

    _backup(LIVE)
    LIVE.write_text(text, encoding="utf-8")
    return "live warm methods patched"


def patch_engine() -> str:
    if not ENGINE.is_file():
        return f"skip engine: missing {ENGINE}"
    text = ENGINE.read_text(encoding="utf-8")
    results: list[str] = []

    # Remove wrong-voice local Playback leftovers if still present
    import re

    text2, n = re.subn(
        r"\n            # QUANTUM_GREETING_LATENCY_LOCAL:.*?\n            # Create CallSession and store in SessionStore",
        "\n            # Create CallSession and store in SessionStore",
        text,
        count=1,
        flags=re.S,
    )
    if n:
        text = text2
        results.append("stripped LOCAL play")
    text2, n = re.subn(
        r"\n            # QUANTUM_GREETING_LATENCY_HIST:.*?\n            # Read called_number:",
        "\n            # Read called_number:",
        text,
        count=1,
        flags=re.S,
    )
    if n:
        text = text2
        results.append("stripped HIST")

    if f"{MARKER}_POOL" in text:
        results.append("engine pool already patched")
        if results:
            _backup(ENGINE)
            ENGINE.write_text(text, encoding="utf-8")
        return "; ".join(results)

    # Init warm slot after outbound dialer fields
    init_needle = '        self._outbound_pbx_type = str(os.getenv("AAVA_OUTBOUND_PBX_TYPE", "freepbx")).strip().lower() or "freepbx"\n'
    if init_needle not in text:
        # try looser
        init_needle = None
        for line in text.splitlines():
            if "_outbound_pbx_type" in line and "os.getenv" in line:
                init_needle = line + "\n"
                break
    if not init_needle or init_needle not in text:
        results.append("engine: init needle missing")
        return "; ".join(results)

    init_insert = init_needle + (
        f"        # {MARKER}_POOL: idle Live WS ready for sub-second greeting\n"
        "        self._live_warm_slot = None\n"
        "        self._live_warm_task = None\n"
        "        self._live_warm_lock = asyncio.Lock()\n"
    )
    text = text.replace(init_needle, init_insert, 1)
    results.append("engine init")

    # Start warm loop near outbound scheduler start
    sched_needle = '        logger.info("Outbound scheduler started")\n'
    if sched_needle in text and f"{MARKER}_LOOP" not in text:
        text = text.replace(
            sched_needle,
            sched_needle
            + f"        # {MARKER}_LOOP\n"
            + "        try:\n"
            + "            if str(os.getenv('AVA_LIVE_WARM', '1')).strip() not in ('0', 'false', 'False'):\n"
            + "                self._live_warm_task = asyncio.create_task(\n"
            + "                    self._live_warm_supervisor(), name='live-warm-pool'\n"
            + "                )\n"
            + "        except Exception:\n"
            + "            logger.debug('Live warm supervisor start failed', exc_info=True)\n",
            1,
        )
        results.append("engine loop start")
    else:
        results.append("engine loop skipped")

    # Inject warm take/refill/supervisor + adopt path before provider = factory()
    factory_needle = (
        "            # Create a per-call provider instance "
        "(providers are NOT concurrency-safe across calls).\n"
        "            provider = factory()\n"
    )
    if factory_needle not in text:
        results.append("engine: factory needle missing")
        return "; ".join(results)

    factory_insert = f'''            # Create a per-call provider instance (providers are NOT concurrency-safe across calls).
            # {MARKER}_ADOPT: prefer idle warm Live session (same Cedar voice, ~ms kick).
            provider = None
            _used_live_warm = False
            try:
                if "live" in str(provider_name or "").lower():
                    provider = await self._take_live_warm_provider()
                    _used_live_warm = provider is not None
            except Exception:
                logger.debug("Live warm take failed", call_id=call_id, exc_info=True)
                provider = None
                _used_live_warm = False
            if provider is None:
                provider = factory()
'''
    text = text.replace(factory_needle, factory_insert, 1)
    results.append("engine adopt take")

    # Replace start_session call with warm adopt branch
    start_needle = (
        "            await provider.start_session(call_id, context=provider_context if provider_context else None)\n"
        '            logger.info("Provider session started", call_id=call_id, provider=provider_name)\n'
    )
    if start_needle not in text:
        results.append("engine: start_session needle missing")
        return "; ".join(results)

    start_insert = f'''            if _used_live_warm and hasattr(provider, "adopt_for_call"):
                adopted = await provider.adopt_for_call(
                    call_id, context=provider_context if provider_context else None
                )
                logger.info(
                    "LIVE_WARM_USED" if adopted else "LIVE_WARM_FALLBACK_COLD",
                    call_id=call_id,
                    provider=provider_name,
                )
                try:
                    asyncio.create_task(self._refill_live_warm_provider())
                except Exception:
                    pass
            else:
                await provider.start_session(call_id, context=provider_context if provider_context else None)
            logger.info("Provider session started", call_id=call_id, provider=provider_name)
'''
    text = text.replace(start_needle, start_insert, 1)
    results.append("engine start branch")

    # Append helper methods before _on_playback_finished
    helpers = f'''
    async def _take_live_warm_provider(self):
        """{MARKER}: pop idle warm Live provider if ready."""
        async with self._live_warm_lock:
            slot = getattr(self, "_live_warm_slot", None)
            self._live_warm_slot = None
        if slot is None:
            return None
        try:
            if (
                getattr(slot, "_warm_ready", False)
                and getattr(slot, "websocket", None) is not None
                and not getattr(slot, "_closed", True)
            ):
                return slot
        except Exception:
            pass
        try:
            await slot.stop_session()
        except Exception:
            pass
        return None

    async def _refill_live_warm_provider(self) -> None:
        """{MARKER}: create a fresh idle Live session in the background."""
        if str(os.getenv("AVA_LIVE_WARM", "1")).strip() in ("0", "false", "False"):
            return
        async with self._live_warm_lock:
            if getattr(self, "_live_warm_slot", None) is not None:
                return
        factory = None
        for name in ("openai_live_pilot", "openai_live"):
            factory = self.provider_factories.get(name)
            if factory:
                break
        if not factory:
            return
        try:
            prov = factory()
            # Prefer outbound hangup tool so adopt has a sane default allowlist.
            warm_ctx = {{"tools": ["hangup_call"]}}
            await prov.warm_start(warm_ctx)
            async with self._live_warm_lock:
                if getattr(self, "_live_warm_slot", None) is None:
                    self._live_warm_slot = prov
                else:
                    await prov.stop_session()
        except Exception:
            logger.warning("LIVE_WARM_REFILL_FAILED", exc_info=True)

    async def _live_warm_supervisor(self) -> None:
        """{MARKER}: keep one warm Live session ready."""
        logger.info("LIVE_WARM_SUPERVISOR_STARTED")
        while True:
            try:
                slot = getattr(self, "_live_warm_slot", None)
                healthy = False
                if slot is not None:
                    try:
                        healthy = bool(
                            getattr(slot, "_warm_ready", False)
                            and getattr(slot, "websocket", None) is not None
                            and not getattr(slot, "_closed", True)
                        )
                    except Exception:
                        healthy = False
                if not healthy:
                    if slot is not None:
                        try:
                            await slot.stop_session()
                        except Exception:
                            pass
                        self._live_warm_slot = None
                    await self._refill_live_warm_provider()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Live warm supervisor tick failed", exc_info=True)
            await asyncio.sleep(3.0)

'''

    pb_needle = "    async def _on_playback_finished(self, event: Dict[str, Any]):\n"
    if pb_needle not in text:
        results.append("engine: playback needle missing")
        return "; ".join(results)
    if f"{MARKER}_HELPERS" not in text:
        text = text.replace(
            pb_needle,
            f"    # {MARKER}_HELPERS\n" + helpers + pb_needle,
            1,
        )
        results.append("engine helpers")

    _backup(ENGINE)
    ENGINE.write_text(text, encoding="utf-8")
    return "; ".join(results)


def main() -> int:
    if not AVA.is_dir():
        print(f"AVA root missing: {AVA}", file=sys.stderr)
        return 2
    results = [patch_live(), patch_engine()]
    for line in results:
        print(line)
    bad = any(
        ("missing" in x) and (x.startswith("live:") or x.startswith("engine:") or "engine:" in x)
        for x in results
    )
    if bad:
        return 1
    # syntax check
    import ast

    for path in (LIVE, ENGINE):
        if path.is_file():
            ast.parse(path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
