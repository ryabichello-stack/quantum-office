"""File ingest from allowlisted server roots."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from brain_platform.db.repository import BrainRepository

logger = logging.getLogger("brain.ingest.files")

TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".py",
    ".ts",
    ".js",
    ".html",
    ".xml",
    ".log",
    ".rst",
}


def default_roots() -> list[Path]:
    raw = (os.getenv("BRAIN_FILE_ROOTS") or "").strip()
    if raw:
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]
    # Safe defaults for office stack content (no secrets dirs)
    candidates = [
        Path("/opt/ava-knowledge/content"),
        Path("/opt/ava-files/assets"),
        Path("/opt/ava-mailer/assets"),
        Path(__file__).resolve().parents[2] / "content",
        Path(__file__).resolve().parents[2] / "vault",
    ]
    return [p for p in candidates if p.exists()]


def _is_under(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _read_excerpt(path: Path, max_bytes: int = 200_000) -> str:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return f"(binary or unsupported type: {path.suffix})"
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def ingest_files(
    repo: BrainRepository,
    *,
    tenant_id: str,
    roots: list[Path] | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    roots = roots or default_roots()
    if not roots:
        return {"ok": False, "error": "no_roots", "created": 0}

    created = 0
    skipped = 0
    scanned = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if any(part in {".git", "node_modules", "__pycache__", "venv", ".venv"} for part in path.parts):
                continue
            if not _is_under(path, roots):
                continue
            scanned += 1
            if scanned > limit:
                break
            try:
                data = path.read_bytes()
                content_hash = hashlib.sha256(data).hexdigest()
                excerpt = _read_excerpt(path)
                result = repo.upsert_file_asset(
                    tenant_id=tenant_id,
                    path=str(path.resolve()),
                    filename=path.name,
                    content_hash=content_hash,
                    source="server_root",
                    text_excerpt=excerpt,
                    visibility="company",
                )
                # upsert always refreshes; count as created when indexed
                if result.get("index", {}).get("chunks", 0) >= 0:
                    created += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("file ingest failed %s: %s", path, exc)
                skipped += 1
        if scanned > limit:
            break

    repo.set_ingest_state("files:last", f"created={created};scanned={scanned}")
    return {"ok": True, "created": created, "skipped": skipped, "scanned": scanned, "roots": [str(r) for r in roots]}
