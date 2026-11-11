# Quantum Labs disaster recovery (2026-11-11)

## Status

| Host | State |
|------|--------|
| `5.35.86.62` (QL Beget / a.47z.ru) | **IRREVOCABLY GONE** — disk and all data lost forever. Do **not** SSH, wait, or plan migration back. |
| `161.104.89.123` (Cloud4Box) | **New production** — rebuild from git + new secrets. DELNO + office stack + 3x-ui |

## Restored on Cloud4Box

| Service | Port | Route |
|---------|------|-------|
| mailer | 8000 | (internal / health) |
| text-bot | 8011 | `/_ava_secretary/` |
| outreach | 8012 | `/_ava_outreach/` |
| console | 8013 | `/_quantum_console/` |
| calendar | 8014 | health |
| files | 8015 | health |
| conference | 8016 | `/_ava_conference/` |
| knowledge | 8017 | `/_ava_knowledge/` |
| 3x-ui + xray | 2053 / 443 | panel + VLESS REALITY |

Bootstrap: `deploy/cloud4box/bootstrap_quantum_office.sh`  
Secrets file on server: `/opt/quantum-office/.env` (mode 600)  
Access note: `/root/QL_RECOVERY.txt`

## Lost with QL (re-enter)

- `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN` (office secretary)
- SMTP Mail.ru / Yandex OAuth + Telemost refresh tokens
- Mail.ru CalDAV password, Bitrix webhook, DaData
- Knowledge vault **content** beyond git
- Asterisk / AVA voice / Mango (telephony) — not restored here
- Polyhub trading — out of scope
- `a.47z.ru` DNS/TLS — point to Cloud4Box when ready

## Channel curate

`TELEGRAM_CHANNEL_BOT_TOKEN` for `@AIContentGPTBot` → `@epoch_z`  
Cloud4Box host has no Telegram egress; keep poller where Telegram works or add egress/proxy.
