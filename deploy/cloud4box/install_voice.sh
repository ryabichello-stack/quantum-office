#!/usr/bin/env bash
# Install / refresh Quantum voice stack on Cloud4Box.
# Prerequisites: Asterisk packages, Docker, /root/ava tree (upstream clone),
# OPENAI_API_KEY in /opt/quantum-office/.env.
# After install: set MANGO_SIP_PASSWORD and update Mango LK trunk IP → this host.
set -euo pipefail

AVA_ROOT="${AVA_ROOT:-/root/ava}"
OFFICE_ENV="${OFFICE_ENV:-/opt/quantum-office/.env}"
PUBLIC_IP="${PUBLIC_IP:-$(curl -4 -s --max-time 5 ifconfig.me || echo 161.104.89.123)}"

if [ ! -d "$AVA_ROOT/src" ]; then
  echo "missing $AVA_ROOT — clone https://github.com/hkjarral/Asterisk-AI-Voice-Agent first" >&2
  exit 1
fi

systemctl enable --now asterisk
asterisk -rx 'core show version' >/dev/null

cd "$AVA_ROOT"
export ASTERISK_UID="$(id -u asterisk)"
export ASTERISK_GID="$(id -g asterisk)"
docker compose build ai_engine
docker compose up -d --no-deps ai_engine
sleep 5
curl -sf "http://127.0.0.1:15000/health" | python3 -m json.tool | head -40

echo "public_ip=$PUBLIC_IP"
echo "Check: asterisk -rx 'pjsip show registrations'"
echo "If Rejected → set MANGO_SIP_PASSWORD and reload pjsip; point Mango trunk to $PUBLIC_IP:5060"
