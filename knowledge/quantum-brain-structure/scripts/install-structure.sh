#!/usr/bin/env bash
# Materialize empty vault+content dirs on a target host path (default /opt/ava-knowledge).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-/opt/ava-knowledge}"

echo "==> install structure → ${DEST}"
mkdir -p "${DEST}/vault" "${DEST}/content" "${DEST}/data"
rsync -a --delete \
  --exclude '.git' \
  "${ROOT}/vault/" "${DEST}/vault/quantum-brain/"
rsync -a "${ROOT}/content/" "${DEST}/content/"
chmod 700 "${DEST}/data" 2>/dev/null || true

if [ ! -f "${DEST}/.env" ] && [ -f "${ROOT}/.env.example" ]; then
  echo "==> note: copy ${ROOT}/.env.example → ${DEST}/.env and fill secrets"
fi

echo "==> done. Vault stubs:"
find "${DEST}/vault/quantum-brain" -type f | sort | head -40
