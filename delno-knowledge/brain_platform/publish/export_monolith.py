"""V4 — export vault shards back to a single quantum_labs.md (generated SoT artifact)."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.S)


def default_vault() -> Path:
    env = (os.getenv("BRAIN_VAULT_PATH") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "vault" / "quantum-brain"


def default_out() -> Path:
    return Path(__file__).resolve().parents[2] / "content" / "quantum_labs.md"


def _strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1).lstrip()


def _shard_paths(vault: Path) -> list[Path]:
    manifest = vault / "_meta" / "shards.yaml"
    ordered: list[Path] = []
    if manifest.exists() and yaml is not None:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        for item in data.get("shards") or []:
            rel = (item or {}).get("path")
            if rel:
                p = vault / rel
                if p.exists():
                    ordered.append(p)
    if ordered:
        return ordered
    # fallback: all md except README/_meta
    out = []
    for p in sorted(vault.rglob("*.md")):
        if "_meta" in p.parts or p.name.lower() == "readme.md":
            continue
        out.append(p)
    return out


def export_monolith(
    *,
    vault: Path | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    vault = vault or default_vault()
    out_path = out_path or default_out()
    if not vault.exists():
        return {"ok": False, "error": f"vault_missing:{vault}"}

    shards = _shard_paths(vault)
    if not shards:
        return {"ok": False, "error": "no_shards"}

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    parts = [
        "# Quantum Labs — единая база знаний для ИИ-секретаря\n\n",
        f"> Generated from vault `{vault}` at {stamp}. Do not edit by hand — edit vault shards.\n\n",
        "## Оглавление корпуса\n\n",
    ]
    for p in shards:
        parts.append(f"- `{p.relative_to(vault).as_posix()}`\n")
    parts.append("\n")

    total_chars = 0
    for p in shards:
        body = _strip_frontmatter(p.read_text(encoding="utf-8", errors="replace")).rstrip() + "\n\n"
        parts.append(body)
        total_chars += len(body)

    text = "".join(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(out_path)
    return {
        "ok": True,
        "vault": str(vault),
        "out": str(out_path),
        "shards": [str(p.relative_to(vault)) for p in shards],
        "chars": len(text),
        "generated_at": stamp,
    }
