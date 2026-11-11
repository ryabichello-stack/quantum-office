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

## Current status (2026-11-11)

- Office mailer / calendar / conference / knowledge: **up** (stubs where secrets missing).
- Asterisk / AVA / Mango: **not present** on Cloud4Box.
- Knowledge corpus: restored from **git vault** (not from dead QL disk).
