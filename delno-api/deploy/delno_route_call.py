#!/usr/bin/python3
"""Asterisk AGI: resolve the inbound DID and select the tenant's voice agent."""
import json
import re
import subprocess
import sys


def agi_set(name, value):
    if not re.fullmatch(r"[A-Z_]{2,40}", name):
        return
    safe = re.sub(r"[^a-zA-Z0-9_.:-]", "", str(value))[:120]
    print(f"SET VARIABLE {name} {safe}", flush=True)
    sys.stdin.readline()


def agi_get(name):
    if not re.fullmatch(r"[A-Z_]{2,40}", name):
        return ""
    print(f"GET VARIABLE {name}", flush=True)
    response = sys.stdin.readline()
    match = re.match(r"200 result=1 \(([^)]*)\)", response)
    return match.group(1) if match else ""


def main():
    env = {}
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if not line:
            break
        key, _, value = line.partition(": ")
        env[key] = value
    dialed = agi_get("DELNO_DID")
    channel = env.get("agi_channel", "")
    trunk_match = re.fullmatch(r"PJSIP/([a-zA-Z0-9_-]+)-[0-9a-fA-F]+", channel)
    trunk_id = trunk_match.group(1) if trunk_match else ""
    args = [
        "/usr/local/bin/asterisk_delno_bridge.sh",
        "start",
        env.get("agi_uniqueid", ""),
        env.get("agi_callerid", ""),
        dialed or env.get("agi_extension", ""),
        env.get("agi_dnid", ""),
        trunk_id,
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
        data = json.loads(result.stdout or "{}")
        slug = str(data.get("voice_agent_slug") or "")
        tenant = str(data.get("tenant_id") or "")
        if not data.get("ok") or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", slug):
            agi_set("DELNO_ROUTE_OK", "0")
            return
        agi_set("AI_AGENT", slug)
        agi_set("DELNO_TENANT_ID", tenant)
        agi_set("DELNO_ROUTE_OK", "1")
    except Exception:
        agi_set("DELNO_ROUTE_OK", "0")


if __name__ == "__main__":
    main()
