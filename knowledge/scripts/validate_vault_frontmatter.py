#!/usr/bin/env python3
"""Validate vault markdown frontmatter (V3 gate)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

REQUIRED_TOP = ("tenant_id", "visibility", "classification", "channels", "publication")
SKIP_NAMES = {"readme.md"}
SKIP_DIRS = {"_meta", ".git"}


def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str | None]:
    if not text.startswith("---"):
        return None, "missing_frontmatter"
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, flags=re.S)
    if not m:
        return None, "invalid_frontmatter_fence"
    if yaml is None:
        return None, "pyyaml_missing"
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except Exception as exc:  # noqa: BLE001
        return None, f"yaml_error:{exc}"
    if not isinstance(data, dict):
        return None, "frontmatter_not_mapping"
    return data, None


def validate_file(path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    rel = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, err = parse_frontmatter(text)
    if err:
        return [f"{rel}: {err}"]
    assert meta is not None
    for key in REQUIRED_TOP:
        if key not in meta:
            errors.append(f"{rel}: missing {key}")
    vis = str(meta.get("visibility") or "")
    pub = meta.get("publication") if isinstance(meta.get("publication"), dict) else {}
    if vis == "public" and not (
        pub.get("manual_approve") or pub.get("approved") or pub.get("public_approved")
    ):
        errors.append(f"{rel}: public requires publication.manual_approve")
    cls = meta.get("classification") if isinstance(meta.get("classification"), dict) else {}
    if cls.get("contains_personal_data") and vis == "public":
        errors.append(f"{rel}: PII cannot be public")
    channels = meta.get("channels")
    if channels is not None and not isinstance(channels, list):
        errors.append(f"{rel}: channels must be a list")
    return errors


def validate_vault(root: Path) -> dict[str, Any]:
    files = sorted(root.rglob("*.md"))
    errors: list[str] = []
    checked = 0
    for path in files:
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.lower() in SKIP_NAMES:
            continue
        checked += 1
        errors.extend(validate_file(path, root))
    return {
        "ok": not errors,
        "checked": checked,
        "errors": errors,
        "vault": str(root),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate quantum-brain vault frontmatter")
    p.add_argument(
        "--vault",
        default=str(Path(__file__).resolve().parents[1] / "vault" / "quantum-brain"),
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    report = validate_vault(Path(args.vault))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"checked={report['checked']} ok={report['ok']}")
        for e in report["errors"]:
            print(f"ERROR {e}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
