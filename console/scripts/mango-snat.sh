#!/bin/bash
# Force SIP/RTP to Mango from secondary IP 45.147.178.172.
# Beget default egress is 5.35.86.62; Mango PSTN often rejects that source.
# Idempotent — safe on every boot / install.
set -euo pipefail

SRC_IP="${MANGO_SNAT_SOURCE:-45.147.178.172}"

for net in 81.88.86.0/24 81.88.87.0/24 137.74.16.0/24; do
  iptables -t nat -C POSTROUTING -d "$net" -p udp --dport 5060 -j SNAT --to-source "$SRC_IP" 2>/dev/null \
    || iptables -t nat -I POSTROUTING 1 -d "$net" -p udp --dport 5060 -j SNAT --to-source "$SRC_IP"
  iptables -t nat -C POSTROUTING -d "$net" -p udp --dport 10000:20000 -j SNAT --to-source "$SRC_IP" 2>/dev/null \
    || iptables -t nat -I POSTROUTING 1 -d "$net" -p udp --dport 10000:20000 -j SNAT --to-source "$SRC_IP"
done
