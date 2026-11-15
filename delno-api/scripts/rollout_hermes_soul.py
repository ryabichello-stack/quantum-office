"""Safely stage updated Hermes SOUL.md and onboarding skill into existing profiles.

Does not run on deploy. Run by hand, after a backup of /opt/delno:

    python scripts/rollout_hermes_soul.py --root /var/lib/delno/tenants --dry-run
    python scripts/rollout_hermes_soul.py --root /var/lib/delno/tenants --apply

Rules:
- Never overwrite a file Hermes (or a person) already changed.
- A profile file is "stock" only when it byte-matches --baseline (the previous
  template). Stock files are replaced with the current template.
- Anything else is left in place. A sibling *.update-candidate is written so
  the diff can be reviewed.
- Every replaced file is copied to *.bak-<timestamp> first.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "hermes_runtime" / "templates" / "home"
FILES = ("SOUL.md", "skills/onboarding.md")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _apply_one(src: Path, dest: Path, baseline: Path | None, *, apply: bool) -> str:
    if not src.is_file():
        return f"skip missing template {src}"
    new = src.read_bytes()
    if not dest.exists():
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new)
        return f"create {dest}"
    current = dest.read_bytes()
    if current == new:
        return f"current {dest}"
    stock = baseline is not None and baseline.is_file() and current == baseline.read_bytes()
    if not stock:
        candidate = dest.with_name(dest.name + ".update-candidate")
        if apply:
            candidate.write_bytes(new)
        return f"keep edited {dest} (candidate {candidate.name})"
    if apply:
        backup = dest.with_name(f"{dest.name}.bak-{_stamp()}")
        shutil.copy2(dest, backup)
        dest.write_bytes(new)
        return f"replace {dest} backup {backup.name}"
    return f"would replace {dest}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Roll Hermes SOUL/skills into existing profiles")
    parser.add_argument("--root", required=True, help="Directory of tenant homes (each contains hermes/)")
    parser.add_argument("--baseline", default="", help="Directory of the previous templates (SOUL.md, skills/)")
    parser.add_argument("--apply", action="store_true", help="Write files. Without this flag, only print the plan.")
    args = parser.parse_args()
    root = Path(args.root)
    baseline_root = Path(args.baseline) if args.baseline else None
    homes = sorted(p for p in root.glob("*/hermes") if p.is_dir())
    if not homes and (root / "SOUL.md").is_file():
        homes = [root]
    print(f"profiles={len(homes)} apply={args.apply}")
    for home in homes:
        for rel in FILES:
            src = TEMPLATES / rel
            dest = home / rel
            base = (baseline_root / rel) if baseline_root else None
            print(_apply_one(src, dest, base, apply=args.apply))


if __name__ == "__main__":
    main()
