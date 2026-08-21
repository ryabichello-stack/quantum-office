#!/usr/bin/env bash
# Deploy Quantum Labs console to /opt/quantum-console and enable outbound dialplan.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="/opt/quantum-console"
SERVICE="quantum-console.service"
AVA_EXT_SRC="${SRC_DIR}/asterisk/extensions.quantum-labs.conf"
AVA_EXT_DST="/root/ava/config/asterisk/extensions.quantum-labs.conf"

echo "==> sync console → ${DEST}"
mkdir -p "${DEST}"
rsync -a --delete \
  --exclude venv --exclude .env --exclude '__pycache__' \
  "${SRC_DIR}/" "${DEST}/"

if [ ! -d "${DEST}/venv" ]; then
  python3 -m venv "${DEST}/venv"
fi
"${DEST}/venv/bin/pip" install -q -r "${DEST}/requirements.txt"

if [ ! -f "${DEST}/.env" ]; then
  echo "==> creating .env"
  cp "${DEST}/.env.example" "${DEST}/.env"
  TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
  sed -i "s|^CONSOLE_TOKEN=.*|CONSOLE_TOKEN=${TOKEN}|" "${DEST}/.env"
  chmod 600 "${DEST}/.env"
  echo "CONSOLE_TOKEN generated (see ${DEST}/.env)"
fi

echo "==> install outbound dialplan canon"
if [ -f "${AVA_EXT_SRC}" ]; then
  cp -a "${AVA_EXT_SRC}" "${AVA_EXT_DST}"
  if [ -x /root/ava/scripts/ensure_asterisk_config.sh ]; then
    # force refresh extensions even if marker exists
    cp -a "${AVA_EXT_DST}" /etc/asterisk/extensions.conf
    chown asterisk:asterisk /etc/asterisk/extensions.conf 2>/dev/null || true
    asterisk -rx "dialplan reload" || true
  fi
fi

echo "==> enable AVA outbound env (generic Asterisk + Local)"
AVA_ENV="/root/ava/.env"
if [ -f "${AVA_ENV}" ]; then
  touch_set() {
    local key="$1" val="$2"
    if grep -qE "^[# ]*${key}=" "${AVA_ENV}"; then
      sed -i -E "s|^[# ]*${key}=.*|${key}=${val}|" "${AVA_ENV}"
    else
      printf '\n%s=%s\n' "${key}" "${val}" >> "${AVA_ENV}"
    fi
  }
  touch_set AAVA_OUTBOUND_PBX_TYPE generic
  touch_set AAVA_OUTBOUND_CHANNEL_TECH local_only
  touch_set AAVA_OUTBOUND_DIAL_CONTEXT from-internal
  touch_set AAVA_OUTBOUND_DIAL_PREFIX ""
  touch_set AAVA_OUTBOUND_EXTENSION_IDENTITY 6789
  touch_set AAVA_OUTBOUND_AMD_CONTEXT aava-outbound-amd
fi

install -m 644 "${SRC_DIR}/quantum-console.service" "/etc/systemd/system/${SERVICE}"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"

# restart ai_engine so outbound env is picked up (no rebuild)
if [ -d /root/ava ]; then
  (cd /root/ava && docker compose up -d --no-build ai_engine) || true
fi

sleep 2
curl -sf "http://127.0.0.1:8013/health" | python3 -m json.tool || true
echo "==> dialplan check"
asterisk -rx "dialplan show from-internal" | head -20 || true
asterisk -rx "dialplan show aava-outbound-amd" | head -15 || true
systemctl --no-pager status "${SERVICE}" | head -12
echo "UI: ssh -L 8013:127.0.0.1:8013 polyhub  →  http://127.0.0.1:8013/"
echo "Token: grep CONSOLE_TOKEN ${DEST}/.env"
