"""V3 publish helpers callable from CLI."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any


def default_vault() -> Path:
    env = (os.getenv("BRAIN_VAULT_PATH") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "vault" / "quantum-brain"


def build_bundle(
    *,
    vault: Path | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    vault = vault or default_vault()
    out_dir = out_dir or (root / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)

    validate = root / "scripts" / "validate_vault_frontmatter.py"
    report_raw = subprocess.check_output(
        ["python3", str(validate), "--vault", str(vault), "--json"],
        text=True,
    )
    report = json.loads(report_raw)
    if not report.get("ok"):
        return {"ok": False, "validation": report}

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        sha = "nogit"
    name = f"quantum-brain-{sha}-{stamp}"
    stage = out_dir / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    (stage / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copytree(vault, stage / "vault" / "quantum-brain")

    files = sorted(p for p in (stage / "vault" / "quantum-brain").rglob("*") if p.is_file())
    checksum_lines = []
    h_all = hashlib.sha256()
    for p in files:
        dig = hashlib.sha256(p.read_bytes()).hexdigest()
        rel = p.relative_to(stage).as_posix()
        checksum_lines.append(f"{dig}  {rel}")
        h_all.update(dig.encode())
        h_all.update(rel.encode())
    (stage / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    manifest = {
        "name": name,
        "git_sha": sha,
        "created_at": stamp,
        "vault_files": len(files),
        "bundle_sha256": h_all.hexdigest(),
        "publication": {"public_requires_manual_approve": True},
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    tar_path = out_dir / f"{name}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(stage, arcname=name)
    return {
        "ok": True,
        "bundle": str(tar_path),
        "manifest": manifest,
        "validation": report,
    }
