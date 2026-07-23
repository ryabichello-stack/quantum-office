#!/usr/bin/env bash
# Deploy ava-knowledge to prod (/opt/ava-knowledge :8017).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="/opt/ava-knowledge"
SERVICE="ava-knowledge.service"

echo "==> sync to ${DEST}"
mkdir -p "${DEST}"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude venv --exclude .env \
    "${SRC_DIR}/" "${DEST}/"
else
  find "${DEST}" -mindepth 1 -maxdepth 1 ! -name venv ! -name .env -exec rm -rf {} +
  cp -a "${SRC_DIR}/." "${DEST}/"
  rm -rf "${DEST}/venv" 2>/dev/null || true
fi

# Prefer live AVA knowledge markdown when available
if [ -f /root/ava/config/knowledge/quantum_labs.md ]; then
  mkdir -p "${DEST}/content"
  cp -f /root/ava/config/knowledge/quantum_labs.md "${DEST}/content/quantum_labs.md"
  echo "==> synced quantum_labs.md from /root/ava/config/knowledge"
fi

if [ ! -d "${DEST}/venv" ]; then
  python3 -m venv "${DEST}/venv"
fi
"${DEST}/venv/bin/pip" install -q -r "${DEST}/requirements.txt"

if [ ! -f "${DEST}/.env" ]; then
  cp "${DEST}/.env.example" "${DEST}/.env"
  chmod 600 "${DEST}/.env"
fi

install -m 644 "${SRC_DIR}/ava-knowledge.service" "/etc/systemd/system/${SERVICE}"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2
curl -sf "http://127.0.0.1:8017/health" | python3 -m json.tool || true
systemctl --no-pager status "${SERVICE}" | head -12
