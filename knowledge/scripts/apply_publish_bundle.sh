#!/usr/bin/env bash
# V3: apply a quantum-brain release bundle on prod and reindex.
set -euo pipefail
BUNDLE="${1:?usage: apply_publish_bundle.sh /path/to/quantum-brain-*.tar.gz}"
DEST="${AVA_KNOWLEDGE_ROOT:-/opt/ava-knowledge}"
RELEASES="$DEST/releases/quantum-brain"
PY="$DEST/venv/bin/python"

if [ ! -f "$BUNDLE" ]; then
  echo "bundle not found: $BUNDLE" >&2
  exit 1
fi
if [ ! -x "$PY" ]; then
  echo "missing venv python: $PY" >&2
  exit 1
fi

mkdir -p "$RELEASES"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$BUNDLE" -C "$TMP"
NAME="$(ls "$TMP" | head -1)"
SRC="$TMP/$NAME"
if [ ! -f "$SRC/manifest.json" ] || [ ! -d "$SRC/vault/quantum-brain" ]; then
  echo "invalid bundle layout" >&2
  exit 1
fi

# Validate frontmatter before cutover
PYTHONPATH="$DEST" "$PY" "$DEST/scripts/validate_vault_frontmatter.py" \
  --vault "$SRC/vault/quantum-brain"

TARGET="$RELEASES/$NAME"
rm -rf "$TARGET"
mkdir -p "$RELEASES"
cp -a "$SRC" "$TARGET"

# Atomic symlink swap
ln -sfn "$TARGET/vault/quantum-brain" "$DEST/vault/quantum-brain.active"
# Keep stable path used by BRAIN_VAULT_PATH
if [ -e "$DEST/vault/quantum-brain" ] && [ ! -L "$DEST/vault/quantum-brain" ]; then
  # Preserve previous tree as backup once
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$DEST/vault/quantum-brain" "$DEST/vault/quantum-brain.bak-$ts" || true
fi
ln -sfn "$TARGET/vault/quantum-brain" "$DEST/vault/quantum-brain"

export PYTHONPATH="$DEST"
set -a
# shellcheck disable=SC1091
source "$DEST/.env"
set +a
export BRAIN_VAULT_PATH="$DEST/vault/quantum-brain"

"$PY" -m brain_platform ingest --sources vault
"$PY" -m brain_platform embed-backfill --limit 800 || true
"$PY" -m brain_platform graph rebuild || true
"$PY" -m brain_platform sync-pg || true
"$PY" -m brain_platform eval --min-pass-rate "${BRAIN_EVAL_MIN_PASS_RATE:-0.6}" || true

echo "applied=$NAME"
echo "vault=$(readlink -f "$DEST/vault/quantum-brain")"
cat "$TARGET/manifest.json"
