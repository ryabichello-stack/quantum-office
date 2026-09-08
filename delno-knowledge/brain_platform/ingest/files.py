"""File ingest from allowlisted server roots.

- Skips FAQ SoT (`quantum_labs.md`) — owned by faq ingest
- Skips archive/venv/.git noise
- Unchanged content_hash → no reindex
- Duplicate body content → skip second copy
- New text files under roots (incl. content/inbox, content/topics) are ingested
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.legacy_faq import resolve_faq_path

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

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    "venv",
    ".venv",
    "archive",
    ".pytest_cache",
}

SKIP_FILE_NAMES = {
    "readme.md",  # meta, not knowledge
}


def default_roots() -> list[Path]:
    raw = (os.getenv("BRAIN_FILE_ROOTS") or "").strip()
    if raw:
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]
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


def _faq_sot_paths() -> set[str]:
    out: set[str] = set()
    p = resolve_faq_path()
    if p is not None:
        try:
            out.add(str(p.resolve()))
        except OSError:
            out.add(str(p))
    # Always skip canonical names even if resolve failed
    for name in ("quantum_labs.md", "quantum_labs.v1.md"):
        out.add(name.lower())
    return out


def _should_skip_file(path: Path, faq_sot: set[str]) -> str | None:
    if path.name.startswith("."):
        return "dotfile"
    if path.name.lower() in SKIP_FILE_NAMES:
        return "meta"
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return "noise_dir"
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    if resolved in faq_sot or path.name.lower() in faq_sot:
        return "faq_sot"
    # vault legacy snapshot of main FAQ
    if path.name.lower() == "quantum_labs.v1.md":
        return "faq_sot"
    return None


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
    limit: int = 2000,
) -> dict[str, Any]:
    roots = roots or default_roots()
    if not roots:
        return {"ok": False, "error": "no_roots", "created": 0}

    faq_sot = _faq_sot_paths()
    created = 0
    updated = 0
    unchanged = 0
    skipped = 0
    skipped_dup = 0
    skipped_sot = 0
    scanned = 0

    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            reason = _should_skip_file(path, faq_sot)
            if reason == "faq_sot":
                skipped_sot += 1
                continue
            if reason:
                skipped += 1
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
                if result.get("skipped_duplicate_content"):
                    skipped_dup += 1
                elif result.get("unchanged") or result.get("index", {}).get("unchanged"):
                    unchanged += 1
                elif result.get("index", {}).get("version", 1) <= 1 and not result.get(
                    "index", {}
                ).get("unchanged"):
                    created += 1
                else:
                    updated += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("file ingest failed %s: %s", path, exc)
                skipped += 1
        if scanned > limit:
            break

    repo.set_ingest_state(
        "files:last",
        f"created={created};updated={updated};unchanged={unchanged};"
        f"dup={skipped_dup};sot={skipped_sot};scanned={scanned}",
    )
    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "skipped_duplicate_content": skipped_dup,
        "skipped_faq_sot": skipped_sot,
        "scanned": scanned,
        "roots": [str(r) for r in roots],
    }
