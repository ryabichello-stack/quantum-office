# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs + DELNO**, не Polyhub trading.

## Что здесь

| Папка | Сервис |
|-------|--------|
| `outreach/` | Bitrix outreach `:8012` |
| `mailer/` | post-call / calendar·Telemost `:8000` |
| `text-bot/` | Telegram + HTTP `:8011` |
| `console/` | пульт `:8013` |
| `knowledge/` | Second Brain / KB `:8017` |
| `calendar/` `conference/` `files/` | office brokers |
| `delno-api/` `delno-web/` `delno-admin/` `DELNO-site-v23/` | DELNO SaaS |
| `delno-office/` | DELNO brokers under `/opt/delno` |
| `docs/` | планы, DNS, restore |

## DELNO

- **Prod host:** Cloud4Box **`161.104.89.123`** (Beget `5.35.86.62` уничтожен — не SSH туда)
- Site: https://dlno.ru · Cabinet: https://app.dlno.ru · API: https://api.dlno.ru
- **Restore from git:** [`docs/DELNO_RESTORE.md`](docs/DELNO_RESTORE.md)
- DNS: [`docs/DLNO_DOMAINS.md`](docs/DLNO_DOMAINS.md)
- Env template: `delno-api/.env.example` → `/opt/delno/.env` only (never git)
- Master plan: [`docs/DELNO_MASTER_PLAN.md`](docs/DELNO_MASTER_PLAN.md)

## Дисциплина

1. Любое изменение → commit + push + PR  
2. Журнал → [`CHANGELOG.md`](CHANGELOG.md)  
3. **Реестр агентов Cursor↔Codex** → [`docs/AGENT_CHANGE_REGISTER.md`](docs/AGENT_CHANGE_REGISTER.md)
   (прод: `/opt/delno/docs/AGENT_CHANGE_REGISTER.md`) — читать до правок, писать после  
4. Секреты не в git  
5. **DELNO: DEV → UAT → PROD.** Любое изменение сначала проверять в DEV, затем выкладывать в постоянный UAT и выполнять полный автоматический набор тестов и сквозные проверки на запущенном UAT.
6. **Штатная выкладка PROD запускается только после полного успешного прогона UAT для того же commit и образов.** Release pipeline автоматически продвигает проверенные образы; отдельное ручное согласование штатного релиза не требуется. Перед продвижением обязательны backup и проверенный откат, после — production smoke и сверка версий. Push, merge или зелёный локальный CI без UAT не запускают deploy.
7. Если UAT недоступен или тесты не прошли, PROD не менять. Исключение — только отдельное явное решение владельца для конкретного аварийного исправления с описанными проверкой и откатом.

## Не ломать

Asterisk / AVA docker / Mango / VPN / `/opt/polyhub` / 3x-ui Reality (после ingress на **:8443**).

## DELNO телефония — жёстко multi-tenant (N клиентов)

Кабинет = **любая** компания (не только quantum-labs). Dogfood QL — один из N.

1. **Один Mango-аккаунт → одна PJSIP registration** (`delno-<slug>-reg` в `pjsip.d/`).  
   Запрещено держать рядом legacy `mango-registration` Registered — двойной INVITE рвёт голос Ava уже на одном клиенте.
2. Входящий: `trunk_id` → tenant DID → `voice_agent_slug` → Stasis. Без `voice_agent_slug` AGI даёт Busy.
3. Не чинить «для QL в обход» общим транком/общим SIP/общим voice profile для чужих tenant.
4. Apply helper: `delno-api/deploy/apply_mango_sip_server.py` (на проде ещё `/opt/delno/scripts/…`) сам гасит legacy shared reg при появлении tenant conf.
