#!/usr/bin/env python3
"""Patch AVA for faster outbound greeting + barge-in shield on «алло».

Targets (/root/ava):
  - src/providers/openai_realtime.py  — GA: disable create/interrupt during greeting
  - src/providers/openai_live.py      — skip Live greeting kick when local Playback played
  - src/engine.py                     — instant ARI Playback + pre-warm Live WS
  - config/ai-agent.local.yaml        — jitter + local barge_in greeting protection

Idempotent (marker: QUANTUM_GREETING_LATENCY).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

AVA = Path("/root/ava")
PROVIDER = AVA / "src" / "providers" / "openai_realtime.py"
LIVE_PROVIDER = AVA / "src" / "providers" / "openai_live.py"
ENGINE = AVA / "src" / "engine.py"
YAML_LOCAL = AVA / "config" / "ai-agent.local.yaml"
MARKER = "QUANTUM_GREETING_LATENCY"


def _backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak-greeting-latency")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())


def patch_provider() -> str:
    if not PROVIDER.is_file():
        return f"skip provider: missing {PROVIDER}"
    text = PROVIDER.read_text(encoding="utf-8")
    if MARKER in text:
        return "provider already patched"

    # 1) Longer hard interrupt floor while greeting plays
    old_min = (
        "self._min_response_time_before_interrupt: float = 2.5  "
        "# Minimum seconds of audio before allowing interruption (increased for farewells)"
    )
    new_min = (
        "self._min_response_time_before_interrupt: float = 2.5  "
        "# Minimum seconds of audio before allowing interruption (increased for farewells)\n"
        f"        self._greeting_min_interrupt_s: float = 8.0  # {MARKER}: shield short «алло»"
    )
    if old_min not in text:
        return "provider: min_response needle missing"
    text = text.replace(old_min, new_min, 1)

    # 2) Replace GA-skip in _send_explicit_greeting with proper GA turn_detection mute
    old_greet = '''        # Disable VAD before greeting (Beta only - GA doesn't accept turn_detection)
        if not self._is_ga:
            disable_vad_payload: Dict[str, Any] = {
                "type": "session.update",
                "event_id": f"sess-disable-vad-{uuid.uuid4()}",
                "session": self._ga_session_type({
                    "turn_detection": None  # Disable automatic VAD
                })
            }
            await self._send_json(disable_vad_payload)
        
        # Small delay to ensure VAD disable is processed
        await asyncio.sleep(0.1)'''

    new_greet = f'''        # {MARKER}: mute server VAD barge-in for greeting (Beta + GA).
        # GA nests turn_detection under audio.input; create_response/interrupt off
        # so short «Алло»/«Приём» does not cancel or cut the first phrase.
        try:
            if self._is_ga:
                td_off: Dict[str, Any] = {{
                    "type": "server_vad",
                    "create_response": False,
                    "interrupt_response": False,
                    "silence_duration_ms": 1700,
                    "threshold": 0.7,
                    "prefix_padding_ms": 200,
                }}
                if getattr(self.config, "turn_detection", None):
                    td = self.config.turn_detection
                    td_off.update({{
                        "type": getattr(td, "type", None) or "server_vad",
                        "silence_duration_ms": getattr(td, "silence_duration_ms", 1700),
                        "threshold": max(float(getattr(td, "threshold", 0.62) or 0.62), 0.65),
                        "prefix_padding_ms": getattr(td, "prefix_padding_ms", 200),
                    }})
                    td_off["create_response"] = False
                    td_off["interrupt_response"] = False
                disable_vad_payload = {{
                    "type": "session.update",
                    "event_id": f"sess-disable-vad-{{uuid.uuid4()}}",
                    "session": {{
                        "type": "realtime",
                        "audio": {{"input": {{"turn_detection": td_off}}}},
                    }},
                }}
            else:
                disable_vad_payload = {{
                    "type": "session.update",
                    "event_id": f"sess-disable-vad-{{uuid.uuid4()}}",
                    "session": self._ga_session_type({{
                        "turn_detection": None
                    }})
                }}
            await self._send_json(disable_vad_payload)
            logger.info(
                "GREETING_VAD_MUTED",
                call_id=self._call_id,
                is_ga=self._is_ga,
            )
        except Exception:
            logger.debug("Failed to mute VAD before greeting", call_id=self._call_id, exc_info=True)

        await asyncio.sleep(0.05)
        self._greeting_transport_guard_active = True
        self._greeting_completed = False
        self._response_audio_start_time = None'''

    if old_greet not in text:
        return "provider: greeting VAD needle missing"
    text = text.replace(old_greet, new_greet, 1)

    # 3) Timing log on greeting send (prod AVA is slightly older than upstream)
    old_send_log_new = '''        logger.info(
            "🎤 Sending greeting response.create",
            call_id=self._call_id,
            greeting_preview=greeting[:50] + "..." if len(greeting) > 50 else greeting,
        )

        await self._send_json(response_payload)
        # Activate only after response.create is accepted by the websocket.
        # A failed greeting request must not leave caller input muted forever.
        self._greeting_transport_guard_active = True'''

    old_send_log_prod = '''        logger.info(
            "🎤 Sending greeting response.create",
            call_id=self._call_id,
            greeting_preview=greeting[:50] + "..." if len(greeting) > 50 else greeting,
        )

        await self._send_json(response_payload)
        self._pending_response = True'''

    new_send_log = f'''        logger.info(
            "🎤 Sending greeting response.create",
            call_id=self._call_id,
            greeting_preview=greeting[:50] + "..." if len(greeting) > 50 else greeting,
        )
        logger.info(
            "GREETING_CREATE",  # {MARKER}
            call_id=self._call_id,
            greeting_chars=len(greeting),
            ts=time.time(),
        )

        await self._send_json(response_payload)
        # Guard already armed before create; keep armed after accept.
        self._greeting_transport_guard_active = True
        self._pending_response = True'''

    if old_send_log_new in text:
        text = text.replace(old_send_log_new, new_send_log, 1)
    elif old_send_log_prod in text:
        text = text.replace(old_send_log_prod, new_send_log, 1)
    else:
        return "provider: greeting send log needle missing"

    # 4) Use greeting-specific interrupt floor
    old_elapsed = '''                elif self._response_audio_start_time:
                    elapsed = time.time() - self._response_audio_start_time
                    if elapsed < self._min_response_time_before_interrupt:
                        logger.info(
                            "🛡️  Barge-in blocked - response too young",
                            call_id=self._call_id,
                            response_id=self._current_response_id,
                            elapsed_seconds=round(elapsed, 2),
                            min_required=self._min_response_time_before_interrupt
                        )'''
    new_elapsed = f'''                elif self._response_audio_start_time:
                    elapsed = time.time() - self._response_audio_start_time
                    min_req = self._min_response_time_before_interrupt
                    if (
                        self._greeting_transport_guard_active
                        or (
                            self._current_response_id == self._greeting_response_id
                            and not self._greeting_completed
                        )
                    ):
                        min_req = max(min_req, float(getattr(self, "_greeting_min_interrupt_s", 8.0)))
                    if elapsed < min_req:
                        logger.info(
                            "🛡️  Barge-in blocked - response too young",
                            call_id=self._call_id,
                            response_id=self._current_response_id,
                            elapsed_seconds=round(elapsed, 2),
                            min_required=min_req,
                        )'''
    if old_elapsed not in text:
        return "provider: elapsed interrupt needle missing"
    text = text.replace(old_elapsed, new_elapsed, 1)

    # 5) Fix GA _re_enable_vad to actually restore create/interrupt (nested audio.input)
    old_re = '''        # GA API does not accept turn_detection in session.update; skip entirely
        if self._is_ga:
            logger.info(
                "🔊 GA mode: skipping turn_detection re-enable (server manages VAD)",
                call_id=self._call_id,
            )
        else:
            # If no config in YAML, let OpenAI use its defaults by not setting the field
            # This is better than hardcoding default values
            session_update = {}
            if turn_detection_config:
                session_update["turn_detection"] = turn_detection_config
            else:
                # Use OpenAI's default server_vad configuration
                session_update["turn_detection"] = {"type": "server_vad"}
            
            enable_vad_payload: Dict[str, Any] = {
                "type": "session.update",
                "event_id": f"sess-enable-vad-{uuid.uuid4()}",
                "session": self._ga_session_type(session_update)
            }
            
            await self._send_json(enable_vad_payload)
            logger.info(
                "🔊 Turn_detection re-enabled after greeting",
                call_id=self._call_id,
                config=turn_detection_config if turn_detection_config else "OpenAI defaults"
            )'''

    new_re = f'''        # {MARKER}: restore VAD after greeting (GA nested + Beta flat).
        td_on: Dict[str, Any] = {{
            "type": "server_vad",
            "create_response": True,
            "interrupt_response": True,
            "silence_duration_ms": 1700,
            "threshold": 0.62,
            "prefix_padding_ms": 200,
        }}
        if turn_detection_config:
            td_on.update(turn_detection_config)
        td_on["create_response"] = True
        td_on["interrupt_response"] = True
        if self._is_ga:
            enable_vad_payload = {{
                "type": "session.update",
                "event_id": f"sess-enable-vad-{{uuid.uuid4()}}",
                "session": {{
                    "type": "realtime",
                    "audio": {{"input": {{"turn_detection": td_on}}}},
                }},
            }}
        else:
            enable_vad_payload = {{
                "type": "session.update",
                "event_id": f"sess-enable-vad-{{uuid.uuid4()}}",
                "session": self._ga_session_type({{"turn_detection": td_on}}),
            }}
        await self._send_json(enable_vad_payload)
        logger.info(
            "GREETING_VAD_RESTORED",
            call_id=self._call_id,
            is_ga=self._is_ga,
            config=td_on,
        )'''

    if old_re not in text:
        return "provider: re_enable_vad needle missing"
    text = text.replace(old_re, new_re, 1)

    _backup(PROVIDER)
    PROVIDER.write_text(text, encoding="utf-8")
    return "provider patched"


def patch_live_provider() -> str:
    """Skip Live greeting kick when engine already played local Asterisk greeting."""
    if not LIVE_PROVIDER.is_file():
        return f"skip live: missing {LIVE_PROVIDER}"
    text = LIVE_PROVIDER.read_text(encoding="utf-8")
    if f"{MARKER}_LIVE_SKIP" in text:
        return "live already patched"

    old_greet_block = '''        greeting = (
            self._context.get("greeting") or getattr(self.config, "greeting", None) or ""
        ).strip()
        if greeting:
            instructions = (
                f"{instructions}\\n\\n"
                f"Сразу после соединения коротко поприветствуй одной фразой (без длинной паузы в начале), "
                f"затем слушай собеседника и отвечай. Текст приветствия: {greeting}"
            ).strip()'''

    new_greet_block = f'''        greeting = (
            self._context.get("greeting") or getattr(self.config, "greeting", None) or ""
        ).strip()
        # {MARKER}_LIVE_SKIP: local ARI Playback already spoke; do not instruct Live to greet again.
        local_greeting_played = bool(self._context.get("local_greeting_played"))
        if greeting and not local_greeting_played:
            instructions = (
                f"{{instructions}}\\n\\n"
                f"Сразу после соединения коротко поприветствуй одной фразой (без длинной паузы в начале), "
                f"затем слушай собеседника и отвечай. Текст приветствия: {{greeting}}"
            ).strip()
        elif local_greeting_played:
            instructions = (
                f"{{instructions}}\\n\\n"
                "Приветствие уже прозвучало абоненту по телефону. "
                "НЕ повторяй приветствие. Сразу слушай собеседника и отвечай."
            ).strip()'''

    if old_greet_block not in text:
        return "live: greeting instructions needle missing"
    text = text.replace(old_greet_block, new_greet_block, 1)

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
                )'''

    new_kick = f'''        # Live does not reliably auto-greet on answer. Kick with instructions.append
        # (+ commentary.append). Do NOT use bare response.create — that stalls Live.
        # {MARKER}_LIVE_SKIP: when local ARI Playback already greeted, skip the kick
        # (Live WS connect is ~6s — that was the post-answer silence).
        if greeting and not local_greeting_played:
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
        elif local_greeting_played:
            logger.info(
                "LOCAL_GREETING_SKIP_LIVE_KICK",
                extra={{
                    "call_id": call_id,
                    "greeting_chars": len(greeting or ""),
                    "ts": time.time(),
                }},
            )'''

    if old_kick not in text:
        return "live: greeting kick needle missing"
    text = text.replace(old_kick, new_kick, 1)

    _backup(LIVE_PROVIDER)
    LIVE_PROVIDER.write_text(text, encoding="utf-8")
    return "live patched"


def patch_engine() -> str:
    if not ENGINE.is_file():
        return f"skip engine: missing {ENGINE}"
    text = ENGINE.read_text(encoding="utf-8")
    results: list[str] = []

    # --- A) Instant local ARI Playback right after caller joins bridge ---
    if f"{MARKER}_LOCAL" not in text:
        needle_local = '''            logger.info("🎯 HYBRID ARI - Step 3: ✅ Caller added to bridge", 
                       channel_id=caller_channel_id, 
                       bridge_id=bridge_id)
            self.bridges[caller_channel_id] = bridge_id
            
            # Create CallSession and store in SessionStore'''
        insert_local = f'''            logger.info("🎯 HYBRID ARI - Step 3: ✅ Caller added to bridge", 
                       channel_id=caller_channel_id, 
                       bridge_id=bridge_id)
            self.bridges[caller_channel_id] = bridge_id

            # {MARKER}_LOCAL: play cached greeting NOW (before Live WS ~6s).
            # openai_live skips its own greeting kick when local_greeting_played is set.
            try:
                import os as _os_greet
                import time as _time_greet
                _media = (
                    _os_greet.getenv("AVA_LOCAL_GREETING_URI", "sound:custom/ql_secretary_hello")
                    or ""
                ).strip()
                _prov_hint = ""
                try:
                    _resp_p = await self.ari_client.send_command(
                        "GET",
                        f"channels/{{caller_channel_id}}/variable",
                        params={{"variable": "AI_PROVIDER"}},
                        tolerate_statuses=[404],
                    )
                    if isinstance(_resp_p, dict):
                        _prov_hint = (_resp_p.get("value") or "").strip()
                except Exception:
                    _prov_hint = ""
                _default_p = str(getattr(self.config, "default_provider", "") or "")
                _is_live = "live" in (_prov_hint or _default_p).lower()
                if _media and _is_live:
                    if not hasattr(self, "_local_greeting_played"):
                        self._local_greeting_played = {{}}
                    self._local_greeting_played[caller_channel_id] = True
                    logger.info(
                        "LOCAL_GREETING_PLAY",
                        call_id=caller_channel_id,
                        media_uri=_media,
                        provider_hint=_prov_hint or _default_p,
                        ts=_time_greet.time(),
                    )
                    asyncio.create_task(
                        self.ari_client.play_sound(caller_channel_id, _media),
                        name=f"local-greeting-{{caller_channel_id}}",
                    )
            except Exception:
                logger.debug(
                    "Local greeting playback kickoff failed",
                    call_id=caller_channel_id,
                    exc_info=True,
                )
            
            # Create CallSession and store in SessionStore'''
        if needle_local not in text:
            results.append("engine: local greeting needle missing")
        else:
            text = text.replace(needle_local, insert_local, 1)
            results.append("engine local play inserted")
    else:
        results.append("engine local already patched")

    # --- B) Stamp local_greeting_played onto provider_overrides when greeting stored ---
    if f"{MARKER}_LOCAL_FLAG" not in text:
        state_needle = (
            'session.provider_overrides["greeting"] = greeting_to_apply\n'
            f'                            session.conversation_state = "greeting"  # {MARKER}_STATE'
        )
        state_needle_alt = 'session.provider_overrides["greeting"] = greeting_to_apply'
        stamp = f'''session.provider_overrides["greeting"] = greeting_to_apply
                            session.conversation_state = "greeting"  # {MARKER}_STATE
                            if getattr(self, "_local_greeting_played", {{}}).pop(session.call_id, False):
                                session.provider_overrides["local_greeting_played"] = True  # {MARKER}_LOCAL_FLAG
                                logger.info(
                                    "LOCAL_GREETING_FLAG",
                                    call_id=session.call_id,
                                )'''
        if state_needle in text:
            text = text.replace(state_needle, stamp, 1)
            results.append("engine local flag stamped")
        elif state_needle_alt in text and f"{MARKER}_LOCAL_FLAG" not in text:
            text = text.replace(
                state_needle_alt,
                stamp,
                1,
            )
            results.append("engine local flag stamped (alt)")
        else:
            results.append("engine: local flag needle missing")
    else:
        results.append("engine local flag already patched")

    # --- C) Pass local_greeting_played into provider_context ---
    if f"{MARKER}_LOCAL_CTX" not in text:
        ctx_needle = '''                        if isinstance(greeting_override, str) and greeting_override.strip():
                            provider_context["greeting"] = greeting_override
                        elif hasattr(context_config, 'greeting') and context_config.greeting:
                            provider_context['greeting'] = context_config.greeting'''
        # There may be two similar blocks; patch the last occurrence used before start_session.
        ctx_insert = f'''                        if isinstance(greeting_override, str) and greeting_override.strip():
                            provider_context["greeting"] = greeting_override
                        elif hasattr(context_config, 'greeting') and context_config.greeting:
                            provider_context['greeting'] = context_config.greeting
                        # {MARKER}_LOCAL_CTX: prefer override, else pending dict from early Playback
                        _local_played = bool(overrides.get("local_greeting_played"))
                        if not _local_played:
                            _local_played = bool(
                                getattr(self, "_local_greeting_played", {{}}).pop(call_id, False)
                            )
                        if _local_played:
                            provider_context["local_greeting_played"] = True
                            overrides["local_greeting_played"] = True'''
        if ctx_needle not in text:
            results.append("engine: local ctx needle missing")
        else:
            # Only the final greeting assignment block (before start_session) — last match.
            idx = text.rfind(ctx_needle)
            if idx < 0:
                results.append("engine: local ctx needle missing")
            else:
                text = text[:idx] + ctx_insert + text[idx + len(ctx_needle) :]
                results.append("engine local ctx passed")
    else:
        results.append("engine local ctx already patched")

    # --- D) Pre-warm Live WS parallel with AudioSocket ---
    if f"{MARKER}_PREWARM" not in text:
        needle = '''            else:
                logger.info("🎯 HYBRID ARI - Step 5: Originating AudioSocket channel", channel_id=caller_channel_id)
                await self._originate_audiosocket_channel_hybrid(caller_channel_id)'''

        insert = f'''            else:
                # {MARKER}_PREWARM: overlap OpenAI WS + session.update with AudioSocket setup
                # so greeting TTS is ready when media bridges (cuts post-answer silence).
                try:
                    if not getattr(session, "provider_session_active", False):
                        logger.info(
                            "GREETING_PREWARM_PROVIDER",
                            call_id=caller_channel_id,
                            ts=__import__("time").time(),
                        )
                        self._kickoff_provider_session_start(caller_channel_id)
                except Exception:
                    logger.debug(
                        "Pre-warm provider start failed",
                        call_id=caller_channel_id,
                        exc_info=True,
                    )
                logger.info("🎯 HYBRID ARI - Step 5: Originating AudioSocket channel", channel_id=caller_channel_id)
                await self._originate_audiosocket_channel_hybrid(caller_channel_id)'''

        if needle not in text:
            results.append("engine: hybrid AudioSocket needle missing")
        else:
            text = text.replace(needle, insert, 1)
            results.append("engine prewarm inserted")
    else:
        results.append("engine prewarm already patched")

    # Ensure conversation_state=greeting when overrides include greeting (for local barge_in)
    state_only = 'session.provider_overrides["greeting"] = greeting_to_apply'
    if (
        state_only in text
        and f"{MARKER}_STATE" not in text
        and f"{MARKER}_LOCAL_FLAG" not in text
    ):
        text = text.replace(
            state_only,
            state_only
            + f'\n                            session.conversation_state = "greeting"  # {MARKER}_STATE',
            1,
        )
        results.append("engine state stamped")

    if any("missing" in r for r in results):
        return "; ".join(results)

    _backup(ENGINE)
    ENGINE.write_text(text, encoding="utf-8")
    return "; ".join(results)


def _yaml_set(text: str, key: str, value: str, *, under: str | None = None) -> str:
    """Set a simple `key: value` line (first match under optional parent)."""
    if under:
        m = re.search(rf"(?m)^{re.escape(under)}:\s*$", text)
        if not m:
            return text
        start = m.end()
        # next top-level key
        m2 = re.search(r"(?m)^[a-zA-Z_][a-zA-Z0-9_]*:\s*", text[start:])
        end = start + m2.start() if m2 else len(text)
        block = text[start:end]
        pat = rf"(?m)^(\s*){re.escape(key)}:\s*.*$"
        if re.search(pat, block):
            block2 = re.sub(pat, rf"\1{key}: {value}", block, count=1)
        else:
            # insert after parent line with 2-space indent default
            block2 = f"\n  {key}: {value}" + block
        return text[:start] + block2 + text[end:]
    pat = rf"(?m)^(\s*){re.escape(key)}:\s*.*$"
    if re.search(pat, text):
        return re.sub(pat, rf"\1{key}: {value}", text, count=1)
    return text


def patch_yaml() -> str:
    path = YAML_LOCAL if YAML_LOCAL.is_file() else AVA / "config" / "ai-agent.yaml"
    if not path.is_file():
        return f"skip yaml: missing {path}"
    text = path.read_text(encoding="utf-8")
    if f"# {MARKER}" in text:
        return "yaml already patched"

    header = f"# {MARKER}: faster greeting playback + barge-in shield\n"
    text = header + text

    # barge_in knobs
    for key, val in (
        ("initial_protection_ms", "2000"),
        ("greeting_protection_ms", "8000"),
        ("min_ms", "400"),
        ("energy_threshold", "1600"),
    ):
        text = _yaml_set(text, key, val, under="barge_in")

    # streaming knobs — 950ms jitter alone ≈ 1s of silence after TTS starts
    for key, val in (
        ("jitter_buffer_ms", "120"),
        ("min_start_ms", "40"),
        ("greeting_min_start_ms", "20"),
        ("greeting_rtp_wait_ms", "100"),
        ("low_watermark_ms", "40"),
    ):
        text = _yaml_set(text, key, val, under="streaming")

    _backup(path)
    path.write_text(text, encoding="utf-8")
    return f"yaml patched ({path})"


def main() -> int:
    if not AVA.is_dir():
        print(f"AVA root missing: {AVA}", file=sys.stderr)
        return 2
    results = [
        patch_provider(),
        patch_live_provider(),
        patch_engine(),
        patch_yaml(),
    ]
    for line in results:
        print(line)
    if any(
        ("missing" in x)
        and (
            x.startswith("provider:")
            or x.startswith("live:")
            or x.startswith("engine:")
            or "engine:" in x
        )
        for x in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
