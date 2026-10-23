#!/usr/bin/env python3
"""Force masculine self-reference for Cedar (male) voice in AVA prompts.

Idempotent marker: QUANTUM_MALE_VOICE_IDENTITY
Patches /root/ava/config/ai-agent.local.yaml contexts + openai_live fallbacks.
"""
from __future__ import annotations

import ast
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

AVA = Path("/root/ava")
CFG = AVA / "config" / "ai-agent.local.yaml"
LIVE = AVA / "src" / "providers" / "openai_live.py"
MARKER = "QUANTUM_MALE_VOICE_IDENTITY"

GENDER_BLOCK = """РОД И ГОЛОС (строго):
- Голос мужской. Говори о себе ТОЛЬКО в мужском роде: «понял», «готов», «слышал», «рад», «записал» — никогда «поняла», «готова», «слышала», «рада», «записала».
- Не представляйся женщиной и не используй женские формы глаголов/прилагательных о себе.
"""

LIVE_FALLBACK = (
    "Ты — живой телефонный ассистент Quantum Labs (мужской голос). "
    "Говори по-русски, коротко и тепло. "
    "О себе только в мужском роде: понял, готов, слышал — не поняла/готова."
)


def _ensure_gender(prompt: str) -> str:
    text = (prompt or "").strip()
    if "РОД И ГОЛОС" in text or "мужском роде" in text:
        return text
    if "ИДЕНТИЧНОСТЬ" in text:
        parts = text.split("\n\n", 1)
        if len(parts) == 2 and "ИДЕНТИЧНОСТЬ" in parts[0]:
            return parts[0] + "\n\n" + GENDER_BLOCK.strip() + "\n\n" + parts[1]
    return GENDER_BLOCK.strip() + "\n\n" + text


def patch_yaml() -> str:
    if not CFG.is_file():
        return "yaml: missing"
    text = CFG.read_text(encoding="utf-8")
    bak = CFG.with_name(
        f"{CFG.name}.bak.male_voice_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    bak.write_text(text, encoding="utf-8")
    cfg = yaml.safe_load(text)
    contexts = cfg.get("contexts") or {}
    changed: list[str] = []
    for name in ("default", "outbound", "live_pilot"):
        ctx = contexts.get(name)
        if not isinstance(ctx, dict):
            continue
        key = "prompt" if "prompt" in ctx else ("instructions" if "instructions" in ctx else None)
        if not key:
            continue
        old = ctx.get(key) or ""
        new = _ensure_gender(old)
        if new != old:
            ctx[key] = new
            changed.append(name)
    if not changed:
        return "yaml: already gendered"
    CFG.write_text(
        yaml.safe_dump(
            cfg,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    return "yaml: " + ",".join(changed)


def patch_live() -> str:
    if not LIVE.is_file():
        return "live: missing"
    text = LIVE.read_text(encoding="utf-8")
    if MARKER in text and "мужском роде" in text:
        return "live: already"

    pattern = r'"Ты — живой телефонный ассистент Quantum Labs\.[^"]*"'

    def repl(m: re.Match[str]) -> str:
        s = m.group(0)
        if "мужском роде" in s or "мужской голос" in s:
            return s
        return '"' + LIVE_FALLBACK + '"'

    text2, n = re.subn(pattern, repl, text)
    if n == 0:
        return "live: fallback strings missing"

    if MARKER not in text2:
        text2 = text2.replace(
            '"""GPT-Live provider (Cedar, full duplex)',
            f'"""GPT-Live provider (Cedar, full duplex)  # {MARKER}',
            1,
        )
    bak = LIVE.with_suffix(LIVE.suffix + f".bak-male-{int(time.time())}")
    shutil.copy2(LIVE, bak)
    LIVE.write_text(text2, encoding="utf-8")
    ast.parse(text2)
    return f"live: patched ({n})"


def main() -> int:
    if not AVA.is_dir():
        print(f"AVA root missing: {AVA}", file=sys.stderr)
        return 2
    for line in (patch_yaml(), patch_live()):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
