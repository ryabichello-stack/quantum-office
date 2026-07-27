#!/usr/bin/env bash
# V3: build a release tar.gz from vault/quantum-brain
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${BRAIN_VAULT_PATH:-$ROOT/vault/quantum-brain}"
OUT_DIR="${1:-$ROOT/dist}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)"
NAME="quantum-brain-${SHA}-${STAMP}"
STAGE="$OUT_DIR/$NAME"

mkdir -p "$STAGE"
python3 "$ROOT/scripts/validate_vault_frontmatter.py" --vault "$VAULT" --json \
  > "$STAGE/validation_report.json"
python3 "$ROOT/scripts/validate_vault_frontmatter.py" --vault "$VAULT"

mkdir -p "$STAGE/vault"
cp -a "$VAULT" "$STAGE/vault/quantum-brain"

python3 - <<PY
import json, hashlib, os
from pathlib import Path
stage = Path("$STAGE")
vault = stage / "vault" / "quantum-brain"
files = sorted(p for p in vault.rglob("*") if p.is_file())
checksums = []
h_all = hashlib.sha256()
for p in files:
    data = p.read_bytes()
    dig = hashlib.sha256(data).hexdigest()
    rel = p.relative_to(stage).as_posix()
    checksums.append(f"{dig}  {rel}")
    h_all.update(dig.encode()); h_all.update(rel.encode())
(stage / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
manifest = {
    "name": "$NAME",
    "git_sha": "$SHA",
    "created_at": "$STAMP",
    "vault_files": len(files),
    "bundle_sha256": h_all.hexdigest(),
    "publication": {"public_requires_manual_approve": True},
}
(stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
PY

mkdir -p "$OUT_DIR"
tar -C "$OUT_DIR" -czf "$OUT_DIR/${NAME}.tar.gz" "$NAME"
echo "bundle=$OUT_DIR/${NAME}.tar.gz"
ls -lh "$OUT_DIR/${NAME}.tar.gz"
