"""V2 — shard monolith FAQ into vault/quantum-brain markdown files (copy, not delete)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

FRONTMATTER = """\
---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: legacy#{anchor}
shard: {shard_id}
---

"""

# Inclusive line ranges are 1-based; end=None means EOF
SHARDS: list[dict[str, Any]] = [
    {
        "id": "part-a-quantum-payouts",
        "path": "products/part-a-quantum-payouts.md",
        "title": "Часть A. Quantum Payouts — общий продукт",
        "start": 18,
        "end": 463,
        "anchor": "part-a",
    },
    {
        "id": "appendix-a-short-faq",
        "path": "products/appendix-a-short-faq.md",
        "title": "Приложение А. Короткие ответы на частые вопросы",
        "start": 464,
        "end": 505,
        "anchor": "appendix-a",
    },
    {
        "id": "appendix-b-ava-ops",
        "path": "ops/appendix-b-ava-ops.md",
        "title": "Приложение Б. Стандарт закрытия / AVA ops",
        "start": 506,
        "end": 774,
        "anchor": "appendix-b",
    },
    {
        "id": "lombards-playbook",
        "path": "lombards/part-b-playbook.md",
        "title": "Часть B. Вертикаль: массовые выплаты для ломбардов",
        "start": 775,
        "end": None,
        "anchor": "part-b-lombards",
    },
]


def default_monolith() -> Path:
    return Path(__file__).resolve().parents[2] / "content" / "quantum_labs.md"


def default_vault_root() -> Path:
    return Path(__file__).resolve().parents[2] / "vault" / "quantum-brain"


def shard_monolith(
    *,
    source: Path | None = None,
    vault_root: Path | None = None,
) -> dict[str, Any]:
    src = source or default_monolith()
    root = vault_root or default_vault_root()
    if not src.exists():
        return {"ok": False, "error": f"missing_source:{src}"}

    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    written: list[dict[str, Any]] = []
    for spec in SHARDS:
        start = int(spec["start"]) - 1
        end = spec["end"]
        chunk_lines = lines[start:] if end is None else lines[start:int(end)]
        body = "".join(chunk_lines).strip() + "\n"
        fm = FRONTMATTER.format(anchor=spec["anchor"], shard_id=spec["id"])
        out_path = root / spec["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(fm + f"# {spec['title']}\n\n" + body, encoding="utf-8")
        written.append(
            {
                "id": spec["id"],
                "path": str(out_path.relative_to(root)),
                "chars": len(body),
                "lines": len(chunk_lines),
            }
        )

    manifest = root / "_meta" / "shards.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        "source: "
        + str(src)
        + "\n"
        + "shards:\n"
        + "".join(
            f"  - id: {w['id']}\n    path: {w['path']}\n    chars: {w['chars']}\n"
            for w in written
        ),
        encoding="utf-8",
    )
    return {"ok": True, "source": str(src), "vault": str(root), "shards": written}
