#!/usr/bin/env python3
"""Patch AVA for faster outbound greeting + barge-in shield on «алло».

Targets (/root/ava):
  - src/providers/openai_realtime.py  — GA: disable create/interrupt during greeting
  - src/engine.py                     — start realtime WS in parallel with AudioSocket
  - config/ai-agent.local.yaml        — jitter + local barge_in greeting protection

Idempotent (marker: QUANTUM_GREETING_LATENCY).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

AVA = Path("/root/ava")
PROVIDER = AVA / "src" / "providers" / "openai_realtime.py"
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

    # 3) Timing log on greeting send
    old_send_log = '''        logger.info(
            "🎤 Sending greeting response.create",
            call_id=self._call_id,
            greeting_preview=greeting[:50] + "..." if len(greeting) > 50 else greeting,
        )

        await self._send_json(response_payload)
        # Activate only after response.create is accepted by the websocket.
        # A failed greeting request must not leave caller input muted forever.
        self._greeting_transport_guard_active = True'''

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
        self._greeting_transport_guard_active = True'''

    if old_send_log not in text:
        return "provider: greeting send log needle missing"
    text = text.replace(old_send_log, new_send_log, 1)

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


def patch_engine() -> str:
    if not ENGINE.is_file():
        return f"skip engine: missing {ENGINE}"
    text = ENGINE.read_text(encoding="utf-8")
    if f"{MARKER}_PREWARM" in text:
        return "engine already patched"

    # Kick off realtime WS in parallel with AudioSocket originate (hybrid path).
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
        return "engine: hybrid AudioSocket needle missing"
    text = text.replace(needle, insert, 1)

    # Ensure conversation_state=greeting when overrides include greeting (for local barge_in)
    state_needle = 'session.provider_overrides["greeting"] = greeting_to_apply'
    if state_needle in text and f"{MARKER}_STATE" not in text:
        text = text.replace(
            state_needle,
            state_needle
            + f"\n                            session.conversation_state = \"greeting\"  # {MARKER}_STATE",
            1,
        )

    _backup(ENGINE)
    ENGINE.write_text(text, encoding="utf-8")
    return "engine patched"


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
    results = [patch_provider(), patch_engine(), patch_yaml()]
    for line in results:
        print(line)
    if any(x.startswith("provider:") or x.startswith("engine:") for x in results if "missing" in x):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
