# Quantum Office — полный аудит инструментов

**Дата:** 2026-11-11 (Europe/Moscow)  
**Назначение:** канонический реестр всего, что уже реализовано в Quantum Office / связанных ветках, чтобы при переносе на ядро **DELNO** (tenant `quantum-labs`) ничего не забыть.  
**Источники:** `main` / `control-panel`, `office-mcp`, `messenger-channels`, `messenger-mcp-history`, `files-upload-mcp`, `mcp-mail-kb-fix`, `mini-crm-mcp`, `delno-api-scaffold`, vault `tools/*`.

> **Правило dogfood:** всё ниже = функционал первого тенанта DELNO (`quantum-labs`). Новые клиенты получают подмножество через feature flags / connectors.

---

## 1. Сервисы (runtime)

| Сервис | Порт | Unit / путь | Роль |
|--------|------|-------------|------|
| mailer | 8000 | `ava-mailer` | post-call, legacy calendar/Telemost, knowledge proxy, SMTP welcome |
| text-bot | 8011 | `ava-text-bot` | Telegram (+ Business), HTTP chat, каналы WA/MAX/VK |
| outreach | 8012 | `ava-outreach` | Bitrix sync, SMTP sequences, DaData, mini-CRM accounts, UI |
| console | 8013 | `quantum-console` | ops UI телефонии, dial, scenarios, campaign proxy |
| calendar | 8014 | `ava-calendar` | CalDAV check/suggest/create (+ Telemost hook) |
| files | 8015 | `ava-files` | Mail.ru Cloud WebDAV list/search/fetch/read/send/upload |
| conference | 8016 | `ava-conference` | Яндекс Телемост + OAuth + invites |
| knowledge | 8017 | `ava-knowledge` | FAQ knowledge + Second Brain (`brain_platform`) |
| sheets-campaign | 8018 | `ava-sheets-campaign` | обзвон из Google Sheet |
| office-mcp gateway | 8019 | `quantum-office-mcp-gateway` | HTTP/MCP façade для агентов |
| AVA voice | 15000 / docker | `/root/ava` | Asterisk + ai_engine + Live/Realtime |
| AVA Admin UI | 3003 | docker | upstream admin / scheduling |

Публичные UI (исторически): `_quantum_console/`, `_ava_outreach/ui/`, `_office_mcp/`, `_ava_secretary/`.

---

## 2. Коннекторы и интеграции (внешние системы)

| Коннектор | Реализация | Статус кода | Заметки для DELNO |
|-----------|------------|-------------|-------------------|
| **DaData** (party findById + suggest) | `outreach/modules/dadata/`, DELNO `party_lookup.py` | ✅ | Обогащение по ИНН: директор, адрес, ОКВЭД, ОГРН/КПП → Bitrix/CRM/leads |
| **Bitrix24 CRM** | `outreach/bitrix_client.py`, sync/clients/accounts | ✅ | Компании/контакты/сделки; REST нужен активный тариф |
| **SMTP cold / office** | outreach sender + mailer | ✅ | Рассылка + transactional |
| **IMAP replies** | outreach reply_watcher / check-replies | ✅ | Классификация ответов |
| **Mail.ru CalDAV** | `calendar/` | ✅ | check / suggest / create |
| **Яндекс Телемост** | `conference/` + OAuth | ✅ | create meeting + invite |
| **Mail.ru Облако (WebDAV)** | `files/` | ✅ | корпоративные файлы |
| **Telegram Bot API** | text-bot | ✅ | guest + owner ACL |
| **Telegram Business** | `telegram_business.py` | ✅ (ветка messenger) | ответы от human-аккаунта |
| **MAX** | `channels/max_messenger.py` + MCP `max.*` | ✅ | send / history |
| **WhatsApp Cloud (Meta)** | `channels/whatsapp.py` | ✅ adapter | MCP-обёртки ещё тонкие / через messenger |
| **VK** | `channels/vk.py` | ✅ adapter | то же |
| **Instagram** | — | ⬜ нет кода | заложить adapter (Meta) в DELNO backlog |
| **Mango Office SIP / VPBX** | Asterisk PJSIP + console callback | ✅ | telephony adapter |
| **OpenAI Realtime / Live** | ai_engine / openai_live | ✅ | cost guard + dial prewarm |
| **Google Sheets** | sheets-campaign + SA upload | ✅ | campaign source |
| **Google Calendar** | docs/imported tool notes | ⚠ частично/legacy | не путать с Mail.ru CalDAV |
| **Yandex OAuth** | conference + mailer remnants | ✅ | Telemost tokens |

---

## 3. MCP tool catalog (union по веткам)

Канон для агентов (Cursor / Grok / Hermes). Имена — как в `office-mcp` (включая `mini-crm-mcp` + messenger history + files upload).

### 3.1 Ops
- `office.health` — health всех сервисов  
- `office.status` — полный статус console (Asterisk, units, line, outbound)

### 3.2 Телефония
- `telephony.inbound_line_get` / `telephony.inbound_line_set` (+ aliases `line.*`)  
- `telephony.scenario_get` / `telephony.scenario_set` (inbound `default` / `outbound`, изолированно)  
- `telephony.list_tools` — каталог in-call tools  
- `telephony.dial` / `telephony.assign_task` / `telephony.callback`  
- `telephony.calls_list` / `telephony.calls_get`  
- aliases: `calls.dial`, `calls.assign_task`, `calls.list`, `calls.get`

**In-call HTTP tools (AVA → mailer):**  
`check_calendar`, `create_calendar_event`, `get_company_knowledge`, `hangup_call`

### 3.3 Sheets campaign
- `campaign.status` / `preview` / `results` / `start` / `stop`  
- `campaign.get_script` / `campaign.set_script`  
(+ HTTP: reset script, writeback, google-sa, flush-writebacks)

### 3.4 Second Brain / Knowledge
- Brain: `kb.search`, `kb.get`, `kb.related`, `kb.find_contact`, `kb.list_threads`, `kb.ingest_status`, `kb.health`  
- Legacy FAQ: `knowledge.query`, `knowledge.topics`, `knowledge.get`  
- HTTP brain: `/api/brain/search|get|contacts/find|threads/list|ingest/run|ingest/status|graph/expand|graph/rebuild`  
- Ingest sources: FAQ vault, files, **mail** (вложения/письма)

### 3.5 Календарь / ВКС
- `calendar.check` / `calendar.suggest` / `calendar.create`  
- `conference.create`  
- create часто = слот + Telemost + invite email/TG

### 3.6 Мессенджеры
- `messenger.status`  
- `messenger.send` / `messenger.chat` / `messenger.chat_reset`  
- `messenger.chats` / `messenger.history` / `messenger.messages`  
- `telegram.send` / `telegram.history`  
- `max.send` / `max.history`  
- aliases: `messenger.telegram_send`, `messenger.max_send`, `*.history`

**Каналы text-bot (не все ещё 1:1 в MCP):** WhatsApp, VK, Telegram Business, MAX.

### 3.7 Outreach / email marketing
- `outreach.dashboard` / `outreach.status`  
- `outreach.outbox` / `outreach.outbox_set_status`  
- `outreach.replies` / `outreach.replies_backfill` / `outreach.check_replies`  
- `outreach.settings_get` / `outreach.settings_set`  
- `outreach.packs` / `outreach.pack_get` / `outreach.pack_apply`  
- `outreach.preview` / `outreach.send_one` / `outreach.send_batch`  
- `outreach.sync` / `outreach.rebuild_outbox`  
- `outreach.leads_import` / `outreach.lead_check`  
- `mail.send` — произвольное письмо (office/cold)

### 3.8 Mini-CRM (Revenue OS stage1)
- `crm.funnel`  
- `crm.companies` / `crm.company_get` / `crm.company_upsert`  
- `crm.lifecycle_set` / `crm.suggest_next`  
Lifecycle: NEW → ENRICHED → IN_SEQUENCE → REPLIED → INTERESTED → MEETING_BOOKED → DISQUALIFIED / NO_RESPONSE / BLACKLISTED

### 3.9 Файлы / Mail.ru Cloud
- `files.status|list|search|fetch|read|send|upload`  
- `mailru.*` — те же операции, source=mailru  
- send via email **или** Telegram

### 3.10 DaData — важно
**Отдельного MCP `dadata.*` в office-mcp пока нет**, но модуль **реализован и рабочий**:

| Где | Что умеет |
|-----|-----------|
| `outreach/modules/dadata` | `findById/party`, `suggest/party`, кэш, extract director/address/OKVED/OGRN/KPP |
| Sync в Bitrix / clients | обогащение компаний по ИНН |
| Personalization писем | ФИО директора в greeting |
| DELNO | `PartyLookupAdapter` + `GET /v1/tenant/party/lookup`, suggest на сайте, lead enrichment |

**В DELNO обязательно вынести как connector + tools:**  
`party.lookup_by_inn`, `party.suggest`, `party.enrich_company` (и хук в CRM upsert).

---

## 4. Outreach modules (внутренняя кухня)

| Module | Назначение |
|--------|------------|
| `clients` | зеркало Bitrix компаний/контактов |
| `accounts` | local Account/Person/Lead/Events (mini-CRM) |
| `dadata` | обогащение по ИНН |
| `sequences` | многошаговые цепочки писем |
| `runner` / `schedule_worker` | планировщик отправок |
| `replies` + classify | разбор входящих |
| `deliverability` / bounce / policy | репутация, pause rules |
| `verification` | проверка адресов |
| `tracking` | open pixel `/t/o/{token}.gif` |
| `analytics` | метрики |
| `telephony` | bridge post-call / lead from calls |
| `callback_cta` | CTA «перезвоните» в письмах |
| presentations / packs / brand logo | контент рассылок |

HTTP UI outreach: sync, send-batch/one, dry-run, dashboard, outbox, replies, settings, packs, presentations, auth/login.

---

## 5. Console / voice ops (HTTP)

- Auth: login / logout / me  
- `/api/status`, `/api/line`, `/api/scenario`  
- `/api/tools`, knowledge topics/get/put  
- `/api/outbound/dial`, `/api/outbound/callback`, outbound script  
- `/api/calls`, `/api/calls/{id}`  
- campaign proxy → sheets-campaign  
- actions: restart-engine, backup, reload-dialplan  
- secrets-checklist  
- Live dial prewarm / cost guards (скрипты console)  
- Male voice identity / lombards outbound script content

---

## 6. Text-bot / секретарь

- Health + Telegram poll  
- Owner full ACL / guest mode  
- HTTP chat endpoints (secretary)  
- Channel adapters: Telegram, Telegram Business, MAX, WhatsApp, VK  
- Employee sales training mode (PIN) — ветка messenger  
- Files + voice STT в Business Telegram  
- Owner alerts / channel publish — отдельные ветки (не потерять при merge)

---

## 7. Mailer (post-call pipeline)

- `POST /api/ava/post-call` — транскрипт → extract → email → CRM fan-out  
- Knowledge query proxy  
- Legacy calendar/Telemost (дублирует calendar/conference — при миграции оставить один путь)  
- Welcome presentation email  
- Yandex OAuth remnants

---

## 8. DELNO-уже (не QO, но часть «набора»)

Чтобы не забыть при сборке ядра:

- multi-tenant auth, feature flags, usage, events  
- channel router Telegram/MAX connect wizards  
- onboarding chat + file/URL ingest → brain  
- Crystal widget (voice+text) + site `dlno.ru`  
- CMS FAQ, party suggest (DaData), leads  
- admin/web cabinets  
- webhook delivery retry / operational events  

---

## 9. Пробелы (есть в продуктовой голове / частично в коде)

| Тема | Факт |
|------|------|
| Instagram connector | нет реализации |
| MCP `dadata.*` / `whatsapp.*` / `vk.*` | adapters есть → нужны явные tools |
| Hermes profiles | ещё не в проде QO |
| Любая телефония кроме Mango | контракт нужен в DELNO E4 |
| Любая почта кроме текущих SMTP/IMAP/Mail.ru | нужен mail connector abstraction |
| Google Calendar as first-class | docs есть, прод = Mail.ru CalDAV |
| Полный restore Beget secrets/vault | отдельно от git |

---

## 10. Чеклист переноса в DELNO (ничего не выкинуть)

- [ ] Knowledge / Second Brain + mail/files ingest + ACL  
- [ ] **DaData** party lookup/suggest/enrich + cache  
- [ ] Bitrix CRM sync + mini-CRM lifecycle tools  
- [ ] Email: transactional `mail.send` + cold outreach packs/sequences/replies/deliverability  
- [ ] Calendar CalDAV + Conference Telemost  
- [ ] Files / Mail.ru Cloud (list/search/read/upload/send)  
- [ ] Messengers: Telegram (+Business), MAX, WhatsApp, VK (+ Instagram later)  
- [ ] Telephony: inbound line, scenarios, dial, assign_task, callback, calls, in-call tools, cost/prewarm  
- [ ] Sheets campaign  
- [ ] Console/ops + MCP gateway (= Tool Registry)  
- [ ] Widget + onboarding + party enrichment (из DELNO)  
- [ ] Hermes profile `quantum-labs` на том же toolset  

---

## 11. Сводка счётчиков

| Класс | Оценка |
|-------|--------|
| HTTP-сервисы office | 9 (+ AVA + MCP GW) |
| MCP tools (unique names, без schema noise) | ~90 |
| Channel adapters messengers | 5 (TG, TG Business, MAX, WA, VK) |
| Outreach internal modules | 11+ |
| External systems | DaData, Bitrix, Mail.ru (mail/cal/cloud), Yandex Telemost, Mango, OpenAI, Google Sheets, Telegram/MAX/Meta/VK |

*Документ обновлять при появлении новых tools в PR; это source of truth для восстановления на DELNO.*
