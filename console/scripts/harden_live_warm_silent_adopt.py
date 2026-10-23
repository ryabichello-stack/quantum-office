#!/usr/bin/env python3
"""Fix warm-adopt greeting silence (call2 ~20s digital silence).

Root causes addressed:
  1) adopt_for_call did not refresh _emit_encoding/_emit_rate after engine
     transport overrides (warm kept ulaw while AudioSocket is slin).
  2) Leading-silence drop only ran for PCM emit — ulaw silence was forwarded
     and streaming played ~20s of zeros to the phone.
  3) Bulky prompt append before greeting kick could stall Live TTS on an idle
     warm session; kick first, append prompt after first real audio.
  4) If kick yields no real audio within ~1.1s → cold start_session fallback.

Marker: QUANTUM_LIVE_WARM_V3
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

AVA = Path("/root/ava")
LIVE = AVA / "src" / "providers" / "openai_live.py"
ENGINE = AVA / "src" / "engine.py"
MARKER = "QUANTUM_LIVE_WARM_V3"


def _backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak-live-warm-v3")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())


def patch_live() -> str:
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text:
        return "live v3 already patched"
    if "QUANTUM_LIVE_WARM" not in text:
        return "live: warm v1 missing — run patch_live_warm_pool.py first"

    # --- Replace adopt_for_call body (refresh emit, kick-first, silence wait) ---
    old_adopt = '''    async def adopt_for_call(
        self, call_id: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """QUANTUM_LIVE_WARM: bind a warm session to a real call and kick greeting (same Cedar voice)."""
        ctx = dict(context or {})
        if not (self.is_warm_healthy() and self._session_started.is_set()):  # QUANTUM_LIVE_WARM_V2
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
                    {
                        "type": "session.instructions.append",
                        "event_id": f"adopt-instr-{call_id}",
                        "delegation_id": None,
                        "content": prompt[:6000],
                    }
                )
            except Exception:
                logger.debug("Warm adopt prompt append failed", exc_info=True)
        await self._send_greeting_kick(call_id, greeting)
        await self._emit_audio_format(call_id)
        logger.info(
            "LIVE_WARM_ADOPT",
            extra={
                "call_id": call_id,
                "adopt_s": round(time.time() - t0, 3),
                "greeting_chars": len(greeting),
            },
        )
        return True'''

    new_adopt = f'''    async def adopt_for_call(
        self, call_id: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """QUANTUM_LIVE_WARM: bind a warm session to a real call and kick greeting (same Cedar voice)."""
        ctx = dict(context or {{}})
        if not (self.is_warm_healthy() and self._session_started.is_set()):  # QUANTUM_LIVE_WARM_V2
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
        # {MARKER}: engine applies transport overrides on config before adopt —
        # refresh emit so we match AudioSocket (slin) instead of warm-time ulaw default.
        self._emit_encoding = self._engine_encoding()
        self._emit_rate = self._engine_rate()
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
        # {MARKER}: kick FIRST — large prompt append before kick caused silent TTS
        # on idle warm sessions (20s of digital silence to the phone).
        await self._emit_audio_format(call_id)
        await self._send_greeting_kick(call_id, greeting)
        got_audio = await self._wait_greeting_energy(timeout_s=1.15)
        if not got_audio:
            logger.warning(
                "LIVE_WARM_SILENT_FALLBACK",
                extra={{
                    "call_id": call_id,
                    "wait_s": round(time.time() - t0, 3),
                    "emit_encoding": self._emit_encoding,
                    "dropped_ms": round(
                        getattr(self, "_leading_silence_dropped_ms", 0.0), 1
                    ),
                }},
            )
            await self.start_session(call_id, ctx)
            return False
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
                "emit_rate": self._emit_rate,
            }},
        )
        return True

    async def _wait_greeting_energy(self, timeout_s: float = 1.15) -> bool:
        """{MARKER}: True once Live emits non-silent audio after kick."""
        deadline = time.time() + float(timeout_s)
        while time.time() < deadline:
            if getattr(self, "_heard_real_audio", False):
                return True
            if getattr(self, "_closed", True) or self.websocket is None:
                return False
            await asyncio.sleep(0.02)
        return bool(getattr(self, "_heard_real_audio", False))'''

    if old_adopt not in text:
        return "live: adopt_for_call needle missing"
    text = text.replace(old_adopt, new_adopt, 1)

    # --- Silence gate: measure PCM energy for BOTH pcm and ulaw emit ---
    old_gate = '''            outbound = self._from_wire_audio(raw)
            if not outbound:
                return
            # Drop leading/trailing digital silence so greeting stream ends and
            # mic ungates — otherwise Live keeps sending silence and the call
            # feels "dead" after the first phrase.
            if self._emit_encoding in _PCM_TARGETS and len(outbound) >= 4:
                try:
                    rms = audioop.rms(outbound, 2)
                except Exception:
                    rms = 9999
                frame_ms = (len(outbound) / 2) / float(self._emit_rate or 8000) * 1000.0
                if not getattr(self, "_heard_real_audio", False):
                    if rms < 50:
                        self._leading_silence_dropped_ms = (
                            getattr(self, "_leading_silence_dropped_ms", 0.0) + frame_ms
                        )
                        return
                    self._heard_real_audio = True
                    logger.info(
                        "OpenAI Live leading silence skipped",
                        extra={
                            "call_id": self._call_id,
                            "dropped_ms": round(
                                getattr(self, "_leading_silence_dropped_ms", 0.0), 1
                            ),
                            "rms": rms,
                        },
                    )
                    self._trailing_silence_ms = 0.0
                elif rms < 50:
                    self._trailing_silence_ms = getattr(self, "_trailing_silence_ms", 0.0) + frame_ms
                    if self._trailing_silence_ms >= 320 and self._in_audio_burst:
                        await self._emit_audio_done()
                    # Do not forward trailing silence — keeps stream/mic alive wrongly.
                    if self._trailing_silence_ms >= 320:
                        return
                else:
                    self._trailing_silence_ms = 0.0'''

    new_gate = f'''            outbound = self._from_wire_audio(raw)
            if not outbound:
                return
            # Drop leading/trailing digital silence so greeting stream ends and
            # mic ungates — otherwise Live keeps sending silence and the call
            # feels "dead" after the first phrase.
            # {MARKER}: also gate ulaw emit (warm default) — previously only PCM
            # was measured, so ulaw silence streamed ~20s to AudioSocket.
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
                samples = len(pcm_for_rms) / 2
                frame_ms = samples / float(self._emit_rate or 8000) * 1000.0
                if not getattr(self, "_heard_real_audio", False):
                    if rms < 50:
                        self._leading_silence_dropped_ms = (
                            getattr(self, "_leading_silence_dropped_ms", 0.0) + frame_ms
                        )
                        return
                    self._heard_real_audio = True
                    logger.info(
                        "OpenAI Live leading silence skipped",
                        extra={{
                            "call_id": self._call_id,
                            "dropped_ms": round(
                                getattr(self, "_leading_silence_dropped_ms", 0.0), 1
                            ),
                            "rms": rms,
                            "emit_encoding": self._emit_encoding,
                        }},
                    )
                    self._trailing_silence_ms = 0.0
                elif rms < 50:
                    self._trailing_silence_ms = getattr(self, "_trailing_silence_ms", 0.0) + frame_ms
                    if self._trailing_silence_ms >= 320 and self._in_audio_burst:
                        await self._emit_audio_done()
                    # Do not forward trailing silence — keeps stream/mic alive wrongly.
                    if self._trailing_silence_ms >= 320:
                        return
                else:
                    self._trailing_silence_ms = 0.0'''

    if old_gate not in text:
        return "live: silence gate needle missing"
    text = text.replace(old_gate, new_gate, 1)

    # warm_start: prime model to speak when kicked
    old_warm_instr = '''            or (
                "Ты — живой телефонный ассистент Quantum Labs. Говори по-русски, коротко и тепло. "
                "Слушай собеседника и отвечай с минимальной задержкой."
            )
        ).strip()'''
    new_warm_instr = f'''            or (
                "Ты — живой телефонный ассистент Quantum Labs. Говори по-русски, коротко и тепло. "
                "Слушай собеседника и отвечай с минимальной задержкой."
            )
        ).strip()
        # {MARKER}: idle warm must be ready to TTS on commentary kick
        instructions = (
            instructions
            + "\\n\\nWhen you receive a greeting kick / commentary to speak first, "
            + "immediately produce spoken audio in Russian — never stay silent."
        ).strip()'''
    if old_warm_instr not in text:
        return "live: warm instructions needle missing"
    text = text.replace(old_warm_instr, new_warm_instr, 1)

    LIVE.write_text(text, encoding="utf-8")
    try:
        ast.parse(text)
    except SyntaxError as exc:
        return f"live: syntax error after patch: {exc}"
    return "live v3 patched"


def patch_engine() -> str:
    text = ENGINE.read_text(encoding="utf-8")
    if MARKER in text:
        return "engine v3 already patched"
    # Soft marker near warm helpers so we can detect deploy
    needle = "    # QUANTUM_LIVE_WARM_HELPERS\n"
    if needle not in text:
        # V2 may have annotated this line
        needle2 = "    # QUANTUM_LIVE_WARM_HELPERS\n    # QUANTUM_LIVE_WARM_V2\n"
        if needle2 in text:
            text = text.replace(
                needle2,
                f"    # QUANTUM_LIVE_WARM_HELPERS\n    # QUANTUM_LIVE_WARM_V2\n    # {MARKER}\n",
                1,
            )
            ENGINE.write_text(text, encoding="utf-8")
            return "engine v3 marker added"
        return "engine: warm helpers marker missing"
    text = text.replace(
        needle,
        f"    # QUANTUM_LIVE_WARM_HELPERS\n    # {MARKER}\n",
        1,
    )
    ENGINE.write_text(text, encoding="utf-8")
    return "engine v3 marker added"


def main() -> int:
    if not LIVE.exists() or not ENGINE.exists():
        print("AVA paths missing", file=sys.stderr)
        return 2
    _backup(LIVE)
    _backup(ENGINE)
    r1 = patch_live()
    r2 = patch_engine()
    print(r1)
    print(r2)
    ok = ("patched" in r1 or "already" in r1) and (
        "marker" in r2 or "already" in r2 or "added" in r2
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
