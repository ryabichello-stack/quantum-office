"""Path allowlist helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


def parse_allowlist(env_value: str) -> List[Path]:
    roots: List[Path] = []
    for part in (env_value or "").split(","):
        part = part.strip()
        if not part:
            continue
        roots.append(Path(part).expanduser().resolve())
    return roots


def resolve_under_allowlist(path: str, allowlist: List[Path]) -> Path:
    """
    Resolve path and ensure it stays under one of the allowlisted roots.
    Absolute paths must be under allowlist; relative paths are joined to the first root.
    """
    if not allowlist:
        raise ValueError("allowlist_empty")

    raw = Path(path).expanduser()
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (allowlist[0] / raw).resolve()

    for root in allowlist:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    raise ValueError("path_not_allowed")


def default_local_allowlist() -> List[Path]:
    return parse_allowlist(
        os.getenv(
            "FILES_LOCAL_ALLOWLIST",
            "/opt/ava-files/assets,/opt/ava-mailer/assets,/opt/ava-conference/assets",
        )
    )
