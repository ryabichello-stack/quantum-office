#!/usr/bin/env python3
"""Hard cost guard for OpenAI Live: no idle paid sessions by default.

Rules (never spend money on idle Live):
1. AVA_LIVE_WARM defaults to OFF ('0').
2. Warm pool only starts if BOTH are truthy:
     AVA_LIVE_WARM=1  AND  AVA_LIVE_WARM_COST_OK=1
3. Idle warm sessions hard-expire (AVA_LIVE_WARM_MAX_IDLE_S, default 45).
4. warm_start / mic keepalive refuse without the dual opt-in.

Idempotent marker: QUANTUM_LIVE_COST_GUARD
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
MARKER = "QUANTUM_LIVE_COST_GUARD"


def _backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + f".bak-cost-guard-{int(time.time())}")
    shutil.copy2(path, bak)


def _truthy(expr: str) -> str:
    """Python snippet: env name -> bool."""
    return (
        f"(str(__import__('os').getenv({expr!r}, '0')).strip().lower() "
        f"in ('1', 'true', 'yes', 'on'))"
    )


def _warm_allowed_snippet() -> str:
    return (
        "str(os.getenv('AVA_LIVE_WARM', '0')).strip().lower() in "
        "('1', 'true', 'yes', 'on') and "
        "str(os.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower() in "
        "('1', 'true', 'yes', 'on')"
    )


def patch_engine() -> str:
    if not ENGINE.is_file():
        return "engine: missing"
    text = ENGINE.read_text(encoding="utf-8")
    if MARKER in text and "AVA_LIVE_WARM_COST_OK" in text:
        # Still force-replace dangerous defaults if any remain.
        text2 = text.replace(
            "os.getenv('AVA_LIVE_WARM', '1')",
            "os.getenv('AVA_LIVE_WARM', '0')",
        ).replace(
            'os.getenv("AVA_LIVE_WARM", "1")',
            'os.getenv("AVA_LIVE_WARM", "0")',
        )
        if text2 != text:
            _backup(ENGINE)
            ENGINE.write_text(text2, encoding="utf-8")
            return "engine: already guarded, defaults forced to 0"
        return "engine: already guarded"

    # 1) Flip all dangerous defaults 1 -> 0
    text = text.replace(
        "os.getenv('AVA_LIVE_WARM', '1')",
        "os.getenv('AVA_LIVE_WARM', '0')",
    ).replace(
        'os.getenv("AVA_LIVE_WARM", "1")',
        'os.getenv("AVA_LIVE_WARM", "0")',
    )

    # 2) Supervisor start: require dual opt-in
    old_start = (
        "            if str(os.getenv('AVA_LIVE_WARM', '0')).strip() "
        "not in ('0', 'false', 'False'):\n"
        "                self._live_warm_task = asyncio.create_task(\n"
        "                    self._live_warm_supervisor(), name='live-warm-pool'\n"
        "                )\n"
    )
    new_start = (
        f"            # {MARKER}: dual opt-in required (never idle Live by accident)\n"
        "            if (\n"
        "                str(os.getenv('AVA_LIVE_WARM', '0')).strip().lower()\n"
        "                in ('1', 'true', 'yes', 'on')\n"
        "                and str(os.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower()\n"
        "                in ('1', 'true', 'yes', 'on')\n"
        "            ):\n"
        "                self._live_warm_task = asyncio.create_task(\n"
        "                    self._live_warm_supervisor(), name='live-warm-pool'\n"
        "                )\n"
        "            else:\n"
        "                logger.info(\n"
        "                    'LIVE_WARM_DISABLED_COST_GUARD',\n"
        "                    extra={'warm': os.getenv('AVA_LIVE_WARM', '0'),\n"
        "                           'cost_ok': os.getenv('AVA_LIVE_WARM_COST_OK', '0')},\n"
        "                )\n"
    )
    if old_start in text:
        text = text.replace(old_start, new_start, 1)
    else:
        # Broader replace for older default='1' already flipped above
        alt = old_start.replace("'0'", "'1'")
        if alt in text:
            text = text.replace(alt, new_start, 1)
        else:
            return "engine: supervisor start needle missing"

    # 3) Refill gate: dual opt-in + max idle tracking
    old_refill_gate = (
        '        if str(os.getenv("AVA_LIVE_WARM", "0")).strip() '
        'in ("0", "false", "False"):\n'
        "            return\n"
    )
    new_refill_gate = (
        f"        # {MARKER}\n"
        "        if not (\n"
        "            str(os.getenv('AVA_LIVE_WARM', '0')).strip().lower()\n"
        "            in ('1', 'true', 'yes', 'on')\n"
        "            and str(os.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower()\n"
        "            in ('1', 'true', 'yes', 'on')\n"
        "        ):\n"
        "            return\n"
    )
    if old_refill_gate in text:
        text = text.replace(old_refill_gate, new_refill_gate, 1)
    else:
        alt = old_refill_gate.replace('"0"', '"1"')
        if alt in text:
            text = text.replace(alt, new_refill_gate, 1)
        else:
            return "engine: refill gate needle missing"

    # 4) Replace supervisor body with cost-safe loop (max idle + refuse without opt-in)
    sup_start = '        """QUANTUM_LIVE_WARM: keep one warm Live session ready."""\n'
    if sup_start not in text:
        # after harden markers docstring may differ
        for cand in (
            '        """QUANTUM_LIVE_WARM: keep one warm Live session ready."""\n',
            '        """Keep one warm Live session ready."""\n',
        ):
            if cand in text:
                sup_start = cand
                break
        else:
            # find by log line
            if 'logger.info("LIVE_WARM_SUPERVISOR_STARTED")\n' not in text:
                return "engine: supervisor body missing"

    # Find supervisor method and rewrite from LIVE_WARM_SUPERVISOR_STARTED through sleep
    needle = '        logger.info("LIVE_WARM_SUPERVISOR_STARTED")\n'
    if needle not in text:
        return "engine: SUPERVISOR_STARTED missing"
    idx = text.find(needle)
    # Find end: await asyncio.sleep(3.0)\n\n (end of method before next def)
    end_marker = "            await asyncio.sleep(3.0)\n"
    end = text.find(end_marker, idx)
    if end < 0:
        return "engine: supervisor sleep missing"
    end = end + len(end_marker)

    new_body = f'''        logger.info("LIVE_WARM_SUPERVISOR_STARTED")
        # {MARKER}: hard expire idle paid Live; refuse without dual opt-in
        while True:
            try:
                allowed = (
                    str(os.getenv("AVA_LIVE_WARM", "0")).strip().lower()
                    in ("1", "true", "yes", "on")
                    and str(os.getenv("AVA_LIVE_WARM_COST_OK", "0")).strip().lower()
                    in ("1", "true", "yes", "on")
                )
                if not allowed:
                    slot = getattr(self, "_live_warm_slot", None)
                    if slot is not None:
                        try:
                            await slot.stop_session()
                        except Exception:
                            pass
                        self._live_warm_slot = None
                        logger.warning("LIVE_WARM_KILLED_COST_GUARD")
                    await asyncio.sleep(30.0)
                    continue
                max_idle = float(os.getenv("AVA_LIVE_WARM_MAX_IDLE_S", "45") or "45")
                slot = getattr(self, "_live_warm_slot", None)
                healthy = False
                if slot is not None:
                    try:
                        born = float(getattr(slot, "_warm_born_at", 0) or 0)
                        if born and (time.time() - born) > max_idle:
                            logger.warning(
                                "LIVE_WARM_IDLE_EXPIRED",
                                extra={{"idle_s": round(time.time() - born, 1),
                                        "max_s": max_idle}},
                            )
                            try:
                                await slot.stop_session()
                            except Exception:
                                pass
                            self._live_warm_slot = None
                            slot = None
                        else:
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
    text = text[:idx] + new_body + text[end:]

    # Track born time on successful refill assign
    assign = "                if getattr(self, \"_live_warm_slot\", None) is None:\n                    self._live_warm_slot = prov\n"
    if assign in text and "_warm_born_at" not in text:
        text = text.replace(
            assign,
            "                if getattr(self, \"_live_warm_slot\", None) is None:\n"
            "                    try:\n"
            "                        prov._warm_born_at = time.time()  # "
            + MARKER
            + "\n"
            "                    except Exception:\n"
            "                        pass\n"
            "                    self._live_warm_slot = prov\n",
            1,
        )

    if "import time\n" not in text and "\nimport time\n" not in text:
        # engine almost certainly already imports time; skip if present as `import time`
        if "import time" not in text.split("\n")[0:80]:
            # best-effort: after import os
            if "import os\n" in text:
                text = text.replace("import os\n", "import os\nimport time\n", 1)

    _backup(ENGINE)
    ENGINE.write_text(text, encoding="utf-8")
    return "engine: cost guard applied"


def patch_live() -> str:
    if not LIVE.is_file():
        return "live: missing"
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text and "AVA_LIVE_WARM_COST_OK" in text:
        return "live: already guarded"

    # Gate right after warm_start docstring (type hints break simple regex)
    anchor = (
        '        """QUANTUM_LIVE_WARM_KEEPALIVE: connect + session.start + '
        'mic keepalive (no greeting yet)."""\n'
    )
    if anchor not in text:
        # fallback: any warm_start docstring line
        import re

        m = re.search(
            r'(    async def warm_start\([\s\S]*?\n)'
            r'(        """[\s\S]*?"""\n)',
            text,
        )
        if not m:
            return "live: warm_start missing"
        insert_at = m.end(2)
        gate = (
            f"        # {MARKER}: refuse idle Live unless dual opt-in\n"
            "        import os as _os_cg\n"
            "        _warm = str(_os_cg.getenv('AVA_LIVE_WARM', '0')).strip().lower()\n"
            "        _ok = str(_os_cg.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower()\n"
            "        if _warm not in ('1', 'true', 'yes', 'on') or "
            "_ok not in ('1', 'true', 'yes', 'on'):\n"
            "            logger.warning('LIVE_WARM_START_BLOCKED_COST_GUARD',\n"
            "                           extra={'warm': _warm, 'cost_ok': _ok})\n"
            "            raise RuntimeError(\n"
            "                'Live warm blocked by cost guard "
            "(set AVA_LIVE_WARM=1 and AVA_LIVE_WARM_COST_OK=1 explicitly)'\n"
            "            )\n"
            "        self._warm_born_at = __import__('time').time()\n"
        )
        text = text[:insert_at] + gate + text[insert_at:]
    else:
        gate = (
            anchor
            + f"        # {MARKER}: refuse idle Live unless dual opt-in\n"
            + "        import os as _os_cg\n"
            + "        _warm = str(_os_cg.getenv('AVA_LIVE_WARM', '0')).strip().lower()\n"
            + "        _ok = str(_os_cg.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower()\n"
            + "        if _warm not in ('1', 'true', 'yes', 'on') or "
            + "_ok not in ('1', 'true', 'yes', 'on'):\n"
            + "            logger.warning('LIVE_WARM_START_BLOCKED_COST_GUARD',\n"
            + "                           extra={'warm': _warm, 'cost_ok': _ok})\n"
            + "            raise RuntimeError(\n"
            + "                'Live warm blocked by cost guard "
            + "(set AVA_LIVE_WARM=1 and AVA_LIVE_WARM_COST_OK=1 explicitly)'\n"
            + "            )\n"
            + "        self._warm_born_at = __import__('time').time()\n"
        )
        text = text.replace(anchor, gate, 1)

    # Gate keepalive loop entry
    kanchor = (
        '        """QUANTUM_LIVE_WARM_KEEPALIVE: paced silence so idle Live '
        'still emits real TTS on kick."""\n'
    )
    if kanchor in text:
        text = text.replace(
            kanchor,
            kanchor
            + f"        # {MARKER}\n"
            + "        import os as _os_cg2\n"
            + "        if str(_os_cg2.getenv('AVA_LIVE_WARM_COST_OK', '0')).strip().lower() "
            + "not in ('1', 'true', 'yes', 'on'):\n"
            + "            logger.warning('LIVE_WARM_KEEPALIVE_BLOCKED_COST_GUARD')\n"
            + "            return\n",
            1,
        )

    _backup(LIVE)
    LIVE.write_text(text, encoding="utf-8")
    return "live: cost guard applied"


def main() -> int:
    if not AVA.is_dir():
        print(f"AVA root missing: {AVA}", file=sys.stderr)
        return 2
    results = [patch_engine(), patch_live()]
    for line in results:
        print(line)
    if any("missing" in r for r in results):
        return 1
    for path in (ENGINE, LIVE):
        if path.is_file():
            ast.parse(path.read_text(encoding="utf-8"))
    print("syntax ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
