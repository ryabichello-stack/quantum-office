#!/usr/bin/env python3
"""Harden Live warm pool after first QUANTUM_LIVE_WARM deploy.

Fixes:
  - Dead WS detection (ConnectionClosed clears warm)
  - Warm tools = full inbound set (calendar/email/kb/hangup)
  - Skip early GREETING_PREWARM when warm slot is ready (kick only after AudioSocket)
  - Health helper used by take/supervisor

Marker: QUANTUM_LIVE_WARM_V2
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

AVA = Path("/root/ava")
LIVE = AVA / "src" / "providers" / "openai_live.py"
ENGINE = AVA / "src" / "engine.py"
MARKER = "QUANTUM_LIVE_WARM_V2"


def _backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak-live-warm-v2")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())


def patch_live() -> str:
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text:
        return "live v2 already patched"
    if "QUANTUM_LIVE_WARM" not in text:
        return "live: warm v1 missing — run patch_live_warm_pool.py first"

    # 1) ConnectionClosed must invalidate warm slot
    old_cc = '''        except ConnectionClosed:
            logger.info("OpenAI Live websocket closed", extra={"call_id": self._call_id})
        except Exception:'''
    new_cc = f'''        except ConnectionClosed:
            logger.info("OpenAI Live websocket closed", extra={{"call_id": self._call_id}})
            # {MARKER}: idle warm must not be reused after remote close
            self._warm_ready = False
            self._closed = True
            self.websocket = None
        except Exception:'''
    if old_cc not in text:
        return "live: ConnectionClosed needle missing"
    text = text.replace(old_cc, new_cc, 1)

    # 2) Health helper after adopt_for_call
    if "def is_warm_healthy" not in text:
        marker = "        return True\n\n    async def send_audio("
        idx = text.find('            "LIVE_WARM_ADOPT"')
        if idx < 0:
            return "live: LIVE_WARM_ADOPT marker missing"
        sub = text[idx:]
        if marker not in sub:
            return "live: return True before send_audio missing"
        abs_idx = idx + sub.index(marker)
        insert = f'''        return True

    def is_warm_healthy(self) -> bool:
        """{MARKER}: local readiness for adopt/supervisor."""
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

    async def send_audio('''
        text = text[:abs_idx] + insert + text[abs_idx + len(marker) :]

    # 3) adopt uses is_warm_healthy
    old_adopt_guard = '''        if not (
            self._warm_ready
            and self.websocket is not None
            and self._session_started.is_set()
            and not self._closed
        ):
            await self.start_session(call_id, ctx)
            return False'''
    new_adopt_guard = f'''        if not (self.is_warm_healthy() and self._session_started.is_set()):  # {MARKER}
            await self.start_session(call_id, ctx)
            return False'''
    if old_adopt_guard not in text:
        return "live: adopt guard needle missing"
    text = text.replace(old_adopt_guard, new_adopt_guard, 1)

    _backup(LIVE)
    LIVE.write_text(text, encoding="utf-8")
    return "live v2 hardened"


def patch_engine() -> str:
    text = ENGINE.read_text(encoding="utf-8")
    if MARKER in text and "GREETING_PREWARM_SKIP_WARM" in text:
        return "engine v2 already patched"
    results = []

    # 1) Full tools on warm refill
    old_tools = '            warm_ctx = {"tools": ["hangup_call"]}\n'
    new_tools = (
        f"            # {MARKER}: match inbound tool surface so adopt works for default+outbound\n"
        '            warm_ctx = {\n'
        '                "tools": [\n'
        '                    "check_calendar",\n'
        '                    "create_calendar_event",\n'
        '                    "send_welcome_email",\n'
        '                    "send_email",\n'
        '                    "create_conference",\n'
        '                    "get_company_knowledge",\n'
        '                    "hangup_call",\n'
        '                ]\n'
        '            }\n'
    )
    if old_tools in text:
        text = text.replace(old_tools, new_tools, 1)
        results.append("tools expanded")
    elif "check_calendar" in text and "warm_ctx" in text:
        results.append("tools already expanded")
    else:
        return "engine: warm_ctx tools needle missing"

    # 2) take/supervisor use is_warm_healthy
    old_take = '''        try:
            if (
                getattr(slot, "_warm_ready", False)
                and getattr(slot, "websocket", None) is not None
                and not getattr(slot, "_closed", True)
            ):
                return slot
        except Exception:
            pass'''
    new_take = f'''        try:
            # {MARKER}
            if hasattr(slot, "is_warm_healthy"):
                if slot.is_warm_healthy():
                    return slot
            elif (
                getattr(slot, "_warm_ready", False)
                and getattr(slot, "websocket", None) is not None
                and not getattr(slot, "_closed", True)
            ):
                return slot
        except Exception:
            pass'''
    if old_take in text:
        text = text.replace(old_take, new_take, 1)
        results.append("take healthy")
    else:
        results.append("take already or missing")

    old_sup = '''                if slot is not None:
                    try:
                        healthy = bool(
                            getattr(slot, "_warm_ready", False)
                            and getattr(slot, "websocket", None) is not None
                            and not getattr(slot, "_closed", True)
                        )
                    except Exception:
                        healthy = False'''
    new_sup = f'''                if slot is not None:
                    try:
                        # {MARKER}
                        if hasattr(slot, "is_warm_healthy"):
                            healthy = bool(slot.is_warm_healthy())
                        else:
                            healthy = bool(
                                getattr(slot, "_warm_ready", False)
                                and getattr(slot, "websocket", None) is not None
                                and not getattr(slot, "_closed", True)
                            )
                    except Exception:
                        healthy = False'''
    if old_sup in text:
        text = text.replace(old_sup, new_sup, 1)
        results.append("supervisor healthy")
    else:
        results.append("supervisor already or missing")

    # 3) Skip early prewarm when warm slot ready — greeting only after AudioSocket
    old_pre = '''                # QUANTUM_GREETING_LATENCY_PREWARM: overlap OpenAI WS + session.update with AudioSocket setup
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
                    )'''
    new_pre = f'''                # QUANTUM_GREETING_LATENCY_PREWARM: cold-path only.
                # {MARKER} / GREETING_PREWARM_SKIP_WARM: if idle Live warm is ready, wait for
                # AudioSocket attach before adopt+kick (otherwise greeting audio is dropped).
                try:
                    _warm = getattr(self, "_live_warm_slot", None)
                    _warm_ok = bool(
                        _warm is not None
                        and (
                            _warm.is_warm_healthy()
                            if hasattr(_warm, "is_warm_healthy")
                            else getattr(_warm, "_warm_ready", False)
                        )
                    )
                    if _warm_ok:
                        logger.info(
                            "GREETING_PREWARM_SKIP_WARM",
                            call_id=caller_channel_id,
                        )
                    elif not getattr(session, "provider_session_active", False):
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
                    )'''
    if old_pre not in text:
        return "engine: prewarm needle missing; " + "; ".join(results)
    text = text.replace(old_pre, new_pre, 1)
    results.append("prewarm gated")

    # stamp marker once in helpers section
    if MARKER not in text:
        text = text.replace(
            "    # QUANTUM_LIVE_WARM_HELPERS\n",
            f"    # QUANTUM_LIVE_WARM_HELPERS\n    # {MARKER}\n",
            1,
        )

    _backup(ENGINE)
    ENGINE.write_text(text, encoding="utf-8")
    return "; ".join(results)


def main() -> int:
    if not AVA.is_dir():
        print("AVA missing", file=sys.stderr)
        return 2
    r1, r2 = patch_live(), patch_engine()
    print(r1)
    print(r2)
    if "missing" in r1 or r2.startswith("engine:"):
        return 1
    ast.parse(LIVE.read_text(encoding="utf-8"))
    ast.parse(ENGINE.read_text(encoding="utf-8"))
    print("AST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
