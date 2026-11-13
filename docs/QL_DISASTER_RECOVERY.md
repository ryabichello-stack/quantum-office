# Quantum Labs disaster recovery (2026-11-11)

## Status

| Host | State |
|------|--------|
| `<OLD_QL_HOST>` (QL Beget / a.47z.ru) | **IRREVOCABLY GONE** — disk and all data lost forever. Do **not** SSH, wait, or plan migration back. Address is not stored in git; see `deploy/cloud4box/README.md`. |
| `<C4B_HOST>` (Cloud4Box) | **New production** — rebuild from git + new secrets. DELNO + office stack + 3x-ui. Take the address from the host inventory, not from this file. |

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

## Secrets status (Cloud4Box `/opt/quantum-office/.env`)

| Key | Status |
|-----|--------|
| `OPENAI_API_KEY` | **set** |
| `TELEGRAM_CHANNEL_BOT_TOKEN` | **set** (`@AIContentGPTBot` → `@epoch_z`) |
| `TELEGRAM_BOT_TOKEN` (personal secretary) | empty — send when ready |
| SMTP `MAIL_*` | empty |
| Yandex OAuth / Telemost | empty |
| Mail.ru CalDAV user/password | empty |
| Bitrix webhook / DaData | empty |

## Knowledge

Git vault remounted into `qo-knowledge` (`content/quantum_labs.md` exported from
`vault/quantum-brain`). Live QL-only notes are gone forever — rebuild further content in vault.

## Voice

See [`QL_VOICE_RESTORE.md`](QL_VOICE_RESTORE.md) (Asterisk + AVA media up; Mango password pending).  
**Product target (multi-tenant office):** [`DELNO_OFFICE_OS_ARCHITECTURE.md`](DELNO_OFFICE_OS_ARCHITECTURE.md) — Hermes + Frontline; QL as dogfood tenant.

## Channel curate

Live poller runs where Telegram egress works (agent tmux). Compose profile
`curate` is ready (`docker compose --profile curate up -d channel-curate`) once
Cloud4Box can reach `api.telegram.org` (proxy/VPN).

## DNS

Point `a.47z.ru` (or new hostname) A-record → `<C4B_HOST>`, then TLS. The address lives in the host inventory (`deploy/cloud4box/README.md`).
