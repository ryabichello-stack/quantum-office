#!/usr/bin/env python3
"""Clear outbound initial playbook; keep inbound Quantum Labs secretary intact."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

OUTBOUND_PROMPT = """Ты — голосовой ассистент на исходящем звонке.
У тебя НЕТ заранее заданного продукта, оффера или компании.
Говори и действуй ТОЛЬКО по сценарию, переданному для ЭТОГО звонка (per-call script в dial API).
Если сценарий для звонка не передан — коротко представься как ассистент (без названия компании)
и спроси, чем помочь. Не начинай питч и не предлагай встречу.
ЗАПРЕЩЕНО по своей инициативе: массовые выплаты, СБП, Quantum Labs, ломбарды, запись на созвон.
Не выдумывай факты. Не вызывай hangup_call в первые 60 секунд и не на первой реплике собеседника.
"""


def main() -> None:
    p = Path("/root/ava/config/ai-agent.local.yaml")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bak = p.with_name(f"{p.name}.bak.empty_outbound_{ts}")
    text = p.read_text(encoding="utf-8")
    bak.write_text(text, encoding="utf-8")
    cfg = yaml.safe_load(text)
    inbound = cfg["contexts"]["default"]
    outbound = cfg["contexts"]["outbound"]
    inbound_prompt = inbound.get("prompt") or ""
    if "выплат" not in inbound_prompt.lower() and "Quantum" not in inbound_prompt:
        raise SystemExit("refusing: inbound prompt unexpected; abort")

    outbound["greeting"] = ""
    outbound["prompt"] = OUTBOUND_PROMPT
    outbound["provider"] = "openai_realtime_outbound"
    # No calendar / KB by default — those invite QL booking & product pitch.
    # Per-call dial can re-enable tools via call_scripts JSON + engine patch.
    outbound["tools"] = ["hangup_call"]
    outbound.setdefault("post_call_tools", ["mailru_post_call"])

    p.write_text(
        yaml.safe_dump(
            cfg,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    print("bak", bak)
    print("inbound greeting unchanged:", (inbound.get("greeting") or "")[:70])
    print("outbound greeting:", repr(outbound["greeting"]))
    print("outbound prompt_len", len(outbound["prompt"]))
    print("outbound mentions массовые выплаты?", "массовые выплаты" in outbound["prompt"])


if __name__ == "__main__":
    main()
