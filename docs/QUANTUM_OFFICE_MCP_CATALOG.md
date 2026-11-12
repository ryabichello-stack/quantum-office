# Quantum Office MCP — архивный каталог tools

Источник: `office-mcp/quantum_office_mcp/tools.py` @ `9f715c4`.
QO на Cloud4Box: `/opt/quantum-office/src`. AVA MCP framework (in-call): `/root/ava/src/mcp` + `mcp_servers` (weather/aviation) — это **не** office-mcp.
Всего tools в office-mcp: **90**.

Документ для восстановления в DELNO Hermes/MCP. Без секретов.

## calendar.* (3)
- `calendar.check`
- `calendar.suggest`
- `calendar.create`

## calls.* (4)
- `calls.dial`
- `calls.assign_task`
- `calls.list`
- `calls.get`

## campaign.* (7)
- `campaign.status`
- `campaign.preview`
- `campaign.results`
- `campaign.start`
- `campaign.stop`
- `campaign.get_script`
- `campaign.set_script`

## conference.* (1)
- `conference.create`

## crm.* (6)
- `crm.funnel`
- `crm.companies`
- `crm.company_get`
- `crm.company_upsert`
- `crm.lifecycle_set`
- `crm.suggest_next`

## files.* (7)
- `files.status`
- `files.list`
- `files.search`
- `files.fetch`
- `files.read`
- `files.send`
- `files.upload`

## kb.* (7)
- `kb.search`
- `kb.get`
- `kb.related`
- `kb.find_contact`
- `kb.list_threads`
- `kb.ingest_status`
- `kb.health`

## knowledge.* (3)
- `knowledge.query`
- `knowledge.topics`
- `knowledge.get`

## line.* (2)
- `line.get`
- `line.set`

## mail.* (1)
- `mail.send`

## mailru.* (7)
- `mailru.status`
- `mailru.list`
- `mailru.search`
- `mailru.read`
- `mailru.fetch`
- `mailru.send`
- `mailru.upload`

## max.* (2)
- `max.send`
- `max.history`

## messenger.* (7)
- `messenger.status`
- `messenger.chats`
- `messenger.history`
- `messenger.messages`
- `messenger.send`
- `messenger.chat`
- `messenger.chat_reset`

## office.* (2)
- `office.health`
- `office.status`

## outreach.* (19)
- `outreach.dashboard`
- `outreach.status`
- `outreach.outbox`
- `outreach.outbox_set_status`
- `outreach.replies`
- `outreach.replies_backfill`
- `outreach.settings_get`
- `outreach.settings_set`
- `outreach.packs`
- `outreach.pack_get`
- `outreach.pack_apply`
- `outreach.preview`
- `outreach.send_one`
- `outreach.send_batch`
- `outreach.sync`
- `outreach.check_replies`
- `outreach.rebuild_outbox`
- `outreach.leads_import`
- `outreach.lead_check`

## telegram.* (2)
- `telegram.send`
- `telegram.history`

## telephony.* (10)
- `telephony.inbound_line_get`
- `telephony.inbound_line_set`
- `telephony.scenario_get`
- `telephony.scenario_set`
- `telephony.list_tools`
- `telephony.dial`
- `telephony.assign_task`
- `telephony.callback`
- `telephony.calls_list`
- `telephony.calls_get`

## Restore status (DELNO)

- Пакет восстановлен: `office-mcp/` + vendored `delno-api/third_party/quantum_office_mcp`.
- Bridge: `delno-api/app/operator/tools/qo_mcp_bridge.py` → Hermes CABINET (~83 tools).
- Пропущены только алиасы `calls.*` / `line.*` / meta `office.health` (DELNO уже владеет).
- `campaign.*` требует сервис на `:8018` (sheets-campaign) — на Cloud4Box может отсутствовать.

