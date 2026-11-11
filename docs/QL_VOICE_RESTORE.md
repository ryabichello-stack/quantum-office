# Voice / AVA restore on Cloud4Box (from scratch)

QL Beget (`5.35.86.62`) is **irrevocably gone**. Asterisk, `/root/ava`, Mango SIP
objects and AVA docker images lived only there — **not in this git repo**.

## Target host

`161.104.89.123` (Cloud4Box) — office stack already on ports `8000–8017`.

## What we need from you

| Item | Why |
|------|-----|
| Mango Office SIP / VPBX credentials | PSTN trunk into Asterisk |
| Public SIP UDP `5060` allowed on Cloud4Box firewall | inbound calls |
| AVA engine source or backup tarball (if any copy exists outside QL) | otherwise rebuild from upstream Asterisk AI Voice Agent + Quantum local YAML |
| Confirm OpenAI Realtime access on the same `OPENAI_API_KEY` | voice model |
| Mail.ru CalDAV + SMTP + Yandex Telemost OAuth | in-call calendar / invite / post-call mail |

## Rebuild stages

1. **Asterisk** — install PJSIP, ARI `:8088`, AudioSocket `:8090`, dialplan `from-mango`.
2. **AVA ai_engine** — Docker host-network, `/root/ava` tree, `ai-agent.local.yaml` Quantum prompt.
3. **Wire to office** — tools → `http://127.0.0.1:8000` (mailer) / knowledge `:8017`.
4. **Smoke** — ARI auth, local SIP test call, one live Mango inbound.

Compose scaffold (placeholders only until AVA tree is restored):

`deploy/cloud4box/docker-compose.voice.yml`

## Current status (2026-11-11, Europe/Moscow)

| Component | State |
|-----------|--------|
| Asterisk 20 | **running** — SIP `:5060/udp`, ARI `127.0.0.1:8088`, dialplan `from-mango` |
| `/root/ava` | **installed** from upstream [Asterisk-AI-Voice-Agent](https://github.com/hkjarral/Asterisk-AI-Voice-Agent) + Quantum `ai-agent.local.yaml` |
| `ai_engine` | **healthy** — `ari_connected=true`, `openai_realtime` ready, AudioSocket `:8090` |
| Mango registration | **Rejected** until `MANGO_SIP_PASSWORD` is set + Mango LK trunk IP → `161.104.89.123:5060` |
| Knowledge / mailer | office stack up; calendar/Telemost stubs until SMTP/CalDAV/OAuth filled |

Ops note on server: `/root/QL_VOICE_STATUS.txt`  
Install helper: `deploy/cloud4box/install_voice.sh`

### Unblock live calls

1. Put Mango SIP password into `/etc/asterisk/pjsip.conf` (replace `__MANGO_SIP_PASSWORD__`) and `/opt/quantum-office/.env` → `MANGO_SIP_PASSWORD=...`
2. `asterisk -rx 'module reload res_pjsip.so'` then `asterisk -rx 'pjsip send register mango-registration'`
3. In Mango LK: external SIP trunk / PBX address = **`161.104.89.123:5060`** UDP
4. Smoke: inbound to company number → Stasis → greeting
