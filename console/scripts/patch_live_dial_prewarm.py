#!/usr/bin/env python3
"""Ring-time Live prewarm for outbound (≤1.5s answer→voice) without 24/7 idle warm.

Flow:
  1) Console ARI originate returns channel_id while PSTN still rings.
  2) Console POST http://127.0.0.1:15000/live-prewarm {channel_id, greeting, ...}
  3) Engine opens Live + mic keepalive keyed by channel_id (TTL ≤ ring timeout).
  4) On answer (Stasis) adopt that slot → greeting kick only.
  5) On ChannelDestroyed without adopt → stop_session (no orphan paid sockets).

Env:
  AVA_LIVE_DIAL_PREWARM=1  — allow dial-scoped warm_start (idle pool still OFF)
  AVA_LIVE_DIAL_PREWARM_TTL_S=75 — hard expire unused prewarm

Does NOT enable AVA_LIVE_WARM (24/7). Marker: QUANTUM_LIVE_DIAL_PREWARM
"""
from __future__ import annotations

import ast
import shutil
import sys
import time
from pathlib import Path

AVA = Path("/root/ava")
ENGINE = AVA / "src" / "engine.py"
LIVE = AVA / "src" / "providers" / "openai_live.py"
MARKER = "QUANTUM_LIVE_DIAL_PREWARM"


def _backup(path: Path) -> None:
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-dial-prewarm-{int(time.time())}"))


def patch_live_cost_gate() -> str:
    """Allow warm_start / keepalive when AVA_LIVE_DIAL_PREWARM=1 (dial-scoped only)."""
    if not LIVE.is_file():
        return "live: missing"
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text and "AVA_LIVE_DIAL_PREWARM" in text:
        return "live: already dial-prewarm gated"

    old_gate = (
        "        if _warm not in ('1', 'true', 'yes', 'on') or "
        "_ok not in ('1', 'true', 'yes', 'on'):\n"
        "            logger.warning('LIVE_WARM_START_BLOCKED_COST_GUARD',\n"
        "                           extra={'warm': _warm, 'cost_ok': _ok})\n"
        "            raise RuntimeError(\n"
        "                'Live warm blocked by cost guard "
        "(set AVA_LIVE_WARM=1 and AVA_LIVE_WARM_COST_OK=1 explicitly)'\n"
        "            )\n"
    )
    new_gate = (
        f"        # {MARKER}: dial-scoped prewarm OR idle dual opt-in\n"
        "        _dial = str(_os_cg.getenv('AVA_LIVE_DIAL_PREWARM', '0')).strip().lower()\n"
        "        _dial_ok = _dial in ('1', 'true', 'yes', 'on')\n"
        "        _idle_ok = (\n"
        "            _warm in ('1', 'true', 'yes', 'on')\n"
        "            and _ok in ('1', 'true', 'yes', 'on')\n"
        "        )\n"
        "        if not (_dial_ok or _idle_ok):\n"
        "            logger.warning('LIVE_WARM_START_BLOCKED_COST_GUARD',\n"
        "                           extra={'warm': _warm, 'cost_ok': _ok, 'dial_prewarm': _dial})\n"
        "            raise RuntimeError(\n"
        "                'Live warm blocked (need AVA_LIVE_DIAL_PREWARM=1 "
        "or AVA_LIVE_WARM+COST_OK)'\n"
        "            )\n"
    )
    if old_gate not in text:
        return "live: cost gate needle missing"
    text = text.replace(old_gate, new_gate, 1)

    old_ka = (
        "        if str(_os_cg2.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower() "
        "not in ('1', 'true', 'yes', 'on'):\n"
        "            logger.warning('LIVE_WARM_KEEPALIVE_BLOCKED_COST_GUARD')\n"
        "            return\n"
    )
    new_ka = (
        f"        # {MARKER}\n"
        "        _ka_ok = str(_os_cg2.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower() "
        "in ('1', 'true', 'yes', 'on')\n"
        "        _ka_dial = str(_os_cg2.getenv('AVA_LIVE_DIAL_PREWARM', '0')).strip().lower() "
        "in ('1', 'true', 'yes', 'on')\n"
        "        if not (_ka_ok or _ka_dial):\n"
        "            logger.warning('LIVE_WARM_KEEPALIVE_BLOCKED_COST_GUARD')\n"
        "            return\n"
    )
    if old_ka in text:
        text = text.replace(old_ka, new_ka, 1)

    _backup(LIVE)
    LIVE.write_text(text, encoding="utf-8")
    return "live: dial-prewarm gate ok"


def patch_engine() -> str:
    if not ENGINE.is_file():
        return "engine: missing"
    text = ENGINE.read_text(encoding="utf-8")
    if MARKER in text and "/live-prewarm" in text:
        return "engine: already dial-prewarm"

    results: list[str] = []

    # 1) init fields next to warm slot
    init_needle = "        self._live_warm_refilling = False\n"
    if init_needle in text and "_live_dial_prewarm" not in text:
        text = text.replace(
            init_needle,
            init_needle
            + f"        # {MARKER}\n"
            + "        self._live_dial_prewarm = {}\n"
            + "        self._live_dial_prewarm_lock = asyncio.Lock()\n"
            + "        self._live_dial_prewarm_tasks = {}\n",
            1,
        )
        results.append("init")

    # 2) HTTP routes
    routes_needle = "            app.router.add_get('/sessions/stats', self._sessions_stats_handler)\n"
    if routes_needle in text and "/live-prewarm" not in text:
        text = text.replace(
            routes_needle,
            routes_needle
            + f"            # {MARKER}\n"
            + "            app.router.add_post('/live-prewarm', self._live_prewarm_handler)\n"
            + "            app.router.add_post('/live-prewarm/cancel', self._live_prewarm_cancel_handler)\n",
            1,
        )
        results.append("routes")

    # 3) Replace take to prefer dial prewarm by call_id
    old_take_call = (
        '                if "live" in str(provider_name or "").lower():\n'
        "                    provider = await self._take_live_warm_provider()\n"
        "                    _used_live_warm = provider is not None\n"
    )
    new_take_call = (
        f'                if "live" in str(provider_name or "").lower():\n'
        f"                    # {MARKER}: prefer ring-time slot for this channel\n"
        "                    provider = await self._take_live_warm_provider(call_id)\n"
        "                    _used_live_warm = provider is not None\n"
    )
    if old_take_call in text:
        text = text.replace(old_take_call, new_take_call, 1)
        results.append("adopt-call")

    # 4) Rewrite _take_live_warm_provider signature + dial map
    old_take_def = (
        '    async def _take_live_warm_provider(self):\n'
        '        """QUANTUM_LIVE_WARM: pop idle warm Live provider if ready."""\n'
        "        async with self._live_warm_lock:\n"
        '            slot = getattr(self, "_live_warm_slot", None)\n'
        "            self._live_warm_slot = None\n"
    )
    new_take_def = f'''    async def _take_live_warm_provider(self, call_id=None):
        """QUANTUM_LIVE_WARM / {MARKER}: dial slot first, then idle warm."""
        if call_id:
            async with self._live_dial_prewarm_lock:
                slot = self._live_dial_prewarm.pop(str(call_id), None)
                self._live_dial_prewarm_tasks.pop(str(call_id), None)
            if slot is not None:
                try:
                    if hasattr(slot, "is_warm_healthy") and slot.is_warm_healthy():
                        logger.info("LIVE_DIAL_PREWARM_USED", call_id=call_id)
                        return slot
                    if (
                        getattr(slot, "_warm_ready", False)
                        and getattr(slot, "websocket", None) is not None
                        and not getattr(slot, "_closed", True)
                    ):
                        logger.info("LIVE_DIAL_PREWARM_USED", call_id=call_id)
                        return slot
                except Exception:
                    pass
                try:
                    await slot.stop_session()
                except Exception:
                    pass
        async with self._live_warm_lock:
            slot = getattr(self, "_live_warm_slot", None)
            self._live_warm_slot = None
'''
    if old_take_def in text:
        text = text.replace(old_take_def, new_take_def, 1)
        results.append("take-def")
    else:
        results.append("take-def MISSING")

    # 5) ChannelDestroyed: drop unused prewarm
    destroy_needle = (
        '            # Remove from pre-stasis tracking if present\n'
        "            self._pre_stasis_channels.discard(channel_id)\n"
    )
    if destroy_needle in text and "LIVE_DIAL_PREWARM_DROP" not in text:
        text = text.replace(
            destroy_needle,
            destroy_needle
            + f"            # {MARKER}: kill unused ring-time Live (no orphan bill)\n"
            + "            try:\n"
            + "                await self._drop_live_dial_prewarm(channel_id, reason='channel_destroyed')\n"
            + "            except Exception:\n"
            + "                pass\n",
            1,
        )
        results.append("destroy")

    # 6) Helpers + HTTP handlers (plain string — no f-string so {cid} stays runtime)
    helpers = '''
    async def _drop_live_dial_prewarm(self, channel_id: str, reason: str = "") -> None:
        """__MARKER__: close unused dial Live session."""
        cid = str(channel_id or "")
        if not cid:
            return
        async with self._live_dial_prewarm_lock:
            slot = self._live_dial_prewarm.pop(cid, None)
            task = self._live_dial_prewarm_tasks.pop(cid, None)
        if task and not task.done():
            task.cancel()
        if slot is None:
            return
        try:
            await slot.stop_session()
        except Exception:
            pass
        logger.info("LIVE_DIAL_PREWARM_DROP", channel_id=cid, reason=reason)

    async def _run_live_dial_prewarm(self, channel_id: str, payload: dict) -> None:
        """__MARKER__: connect Live during ring; store for adopt on answer."""
        cid = str(channel_id)
        ttl = float(os.getenv("AVA_LIVE_DIAL_PREWARM_TTL_S", "75") or "75")
        provider_name = str(payload.get("provider") or "openai_live_pilot")
        factory = self.provider_factories.get(provider_name)
        if not factory:
            for name in ("openai_live_pilot", "openai_live"):
                factory = self.provider_factories.get(name)
                if factory:
                    break
        if not factory:
            logger.warning("LIVE_DIAL_PREWARM_NO_FACTORY", channel_id=cid)
            return
        t0 = time.time()
        try:
            prov = factory()
            tools = payload.get("tools") or ["hangup_call"]
            if not isinstance(tools, list):
                tools = ["hangup_call"]
            ctx = {
                "tools": [str(x) for x in tools if str(x).strip()],
                "greeting": str(payload.get("greeting") or ""),
                "instructions": str(payload.get("script") or payload.get("prompt") or ""),
                "prompt": str(payload.get("script") or payload.get("prompt") or ""),
            }
            await prov.warm_start(ctx)
            try:
                prov._warm_born_at = time.time()
            except Exception:
                pass
            async with self._live_dial_prewarm_lock:
                old = self._live_dial_prewarm.get(cid)
                self._live_dial_prewarm[cid] = prov
            if old is not None:
                try:
                    await old.stop_session()
                except Exception:
                    pass
            logger.info(
                "LIVE_DIAL_PREWARM_READY",
                channel_id=cid,
                warm_s=round(time.time() - t0, 3),
                ttl_s=ttl,
            )
            await asyncio.sleep(max(5.0, ttl))
            # still unused?
            async with self._live_dial_prewarm_lock:
                cur = self._live_dial_prewarm.get(cid)
                if cur is prov:
                    self._live_dial_prewarm.pop(cid, None)
                    self._live_dial_prewarm_tasks.pop(cid, None)
                    expire = True
                else:
                    expire = False
            if expire:
                try:
                    await prov.stop_session()
                except Exception:
                    pass
                logger.warning("LIVE_DIAL_PREWARM_EXPIRED", channel_id=cid)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("LIVE_DIAL_PREWARM_FAILED", channel_id=cid, exc_info=True)
            await self._drop_live_dial_prewarm(cid, reason="failed")

    async def _live_prewarm_handler(self, request):
        """__MARKER__: POST {channel_id, greeting?, script?, tools?, provider?}"""
        if not self._is_request_authorized(request):
            peer = request.remote or ""
            if peer not in ("127.0.0.1", "::1") and not str(peer).startswith("172."):
                return web.json_response({"ok": False, "error": "forbidden"}, status=403)
        if str(os.getenv("AVA_LIVE_DIAL_PREWARM", "0")).strip().lower() not in (
            "1", "true", "yes", "on",
        ):
            return web.json_response(
                {"ok": False, "error": "AVA_LIVE_DIAL_PREWARM disabled"}, status=503
            )
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad json"}, status=400)
        cid = str((payload or {}).get("channel_id") or "").strip()
        if not cid:
            return web.json_response({"ok": False, "error": "channel_id required"}, status=400)
        async with self._live_dial_prewarm_lock:
            prev = self._live_dial_prewarm_tasks.get(cid)
            if prev and not prev.done():
                return web.json_response({"ok": True, "status": "already_warming", "channel_id": cid})
            task = asyncio.create_task(
                self._run_live_dial_prewarm(cid, payload or {}),
                name="live-dial-prewarm-" + cid,
            )
            self._live_dial_prewarm_tasks[cid] = task
        logger.info("LIVE_DIAL_PREWARM_QUEUED", channel_id=cid)
        return web.json_response({"ok": True, "status": "queued", "channel_id": cid})

    async def _live_prewarm_cancel_handler(self, request):
        """__MARKER__: POST {channel_id} — drop unused prewarm."""
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        cid = str((payload or {}).get("channel_id") or "").strip()
        if not cid:
            return web.json_response({"ok": False, "error": "channel_id required"}, status=400)
        await self._drop_live_dial_prewarm(cid, reason="cancel")
        return web.json_response({"ok": True, "channel_id": cid})

'''.replace("__MARKER__", MARKER)

    # Insert helpers before first QUANTUM_LIVE_WARM_HELPERS block or before _on_playback_finished
    if f"{MARKER}_HELPERS" not in text:
        anchor = "    # QUANTUM_LIVE_WARM_HELPERS\n"
        if anchor in text:
            text = text.replace(
                anchor,
                f"    # {MARKER}_HELPERS\n" + helpers + anchor,
                1,
            )
            results.append("helpers")
        else:
            pb = "    async def _on_playback_finished(self, event: Dict[str, Any]):\n"
            if pb in text:
                text = text.replace(pb, f"    # {MARKER}_HELPERS\n" + helpers + pb, 1)
                results.append("helpers-pb")
            else:
                results.append("helpers MISSING")

    # Skip refill after dial-prewarm adopt (don't start idle pool)
    old_refill = (
        "                try:\n"
        "                    asyncio.create_task(self._refill_live_warm_provider())\n"
        "                except Exception:\n"
        "                    pass\n"
    )
    if old_refill in text and f"{MARKER}_NO_REFILL" not in text:
        text = text.replace(
            old_refill,
            f"                # {MARKER}_NO_REFILL: dial prewarm must not spawn idle pool\n"
            "                try:\n"
            "                    if str(os.getenv('AVA_LIVE_WARM', '0')).strip().lower() in "
            "('1', 'true', 'yes', 'on'):\n"
            "                        asyncio.create_task(self._refill_live_warm_provider())\n"
            "                except Exception:\n"
            "                    pass\n",
            1,
        )
        results.append("no-idle-refill")

    _backup(ENGINE)
    ENGINE.write_text(text, encoding="utf-8")
    return "engine: " + ", ".join(results)


def main() -> int:
    if not AVA.is_dir():
        print(f"missing {AVA}", file=sys.stderr)
        return 2
    lines = [patch_live_cost_gate(), patch_engine()]
    for line in lines:
        print(line)
    if any("MISSING" in x or "missing" in x for x in lines):
        return 1
    for path in (ENGINE, LIVE):
        if path.is_file():
            ast.parse(path.read_text(encoding="utf-8"))
    print("syntax ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
