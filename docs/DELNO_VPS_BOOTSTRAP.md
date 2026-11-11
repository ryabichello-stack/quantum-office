# DELNO на Cloud4Box — bootstrap status

**Хост:** `161.104.89.123` (Cloud4Box «Производительный»)  
**Дата:** 2026-11-11  
**Цель:** быстрее всего получить **пользуемый** dogfood-контур (tenant `quantum-labs`), не дожидаясь телефонии и полного переноса Quantum Office.

## Что поднято (Phase A — готово)

| Компонент | URL / путь | Статус |
|-----------|------------|--------|
| Marketing site **v2** (canonical) | http://161.104.89.123/ | ✅ «Клиенты пишут и звонят…» |
| Кабинет (`delno-web`) | http://161.104.89.123:3020/ | ✅ |
| API | http://161.104.89.123/delno-api/v1/health | ✅ |
| Brain / knowledge | http://161.104.89.123/delno-brain/api/brain/health | ✅ |
| Widget CDN | http://161.104.89.123/widget/v1/ | ✅ |
| `delno-site` container | `127.0.0.1:18019` → nginx `/` | ✅ restored `DELNO-site-v23` |
| Postgres (internal) | docker `delno-postgres` | ✅ healthy |
| systemd | `delno-stack.service` | ✅ active |

Код на сервере: `/opt/delno/{api,knowledge,web,cdn}` + `/opt/delno/docker-compose.yml` + `/opt/delno/.env` (mode 600).  
Доступы (пароли): `/root/DELNO_ACCESS.txt` на VPS.

### Tenant dogfood

- slug: `quantum-labs`
- owner: `owner@quantumlabs.ru` (пароль в `DELNO_ACCESS.txt` — **сменить после первого входа**)
- `site_key` / public_key: в ответе `GET /v1/tenant/widget`
- onboarding: **started** (`in_progress`)
- knowledge: seed-документ Quantum Labs
- LLM: `MODEL_PROVIDER=stub` → кабинет / виджет / onboarding **уже отвечают** без OpenAI

### Smoke (проверено)

- `POST /v1/auth/login` → JWT
- `GET /v1/tenant/me`, `/v1/tenant/widget`, `/v1/tenant/knowledge/documents`
- `POST /v1/public/widget/session` + `/message` (stub reply)
- `POST /v1/tenant/onboarding/start`

## Не только Quantum Office — что ещё в наборе

Источник кода: ветка `cursor/delno-api-scaffold-14e9` (worktree `/tmp/delno-src` у агента).

| Пакет | Есть в коде | На VPS сейчас | Заметка |
|-------|-------------|---------------|---------|
| **delno-api** multi-tenant | ✅ | ✅ | auth, tenants, leads, operator, channels, onboarding, party |
| **delno-knowledge** (second-brain) | ✅ | ✅ | tenant vault, search |
| **delno-web** cabinet | ✅ | ✅ :3020 | dashboard / onboarding / knowledge / inbox / settings |
| **delno-widget** crystal v28 | ✅ | ✅ CDN | text chat работает на stub |
| **delno-admin** | ✅ | ⬜ | следующий шаг UI платформы |
| **DELNO-site-v23** marketing | ⚠️ без package.json | ⬜ | не блокирует dogfood |
| Party / DaData | ✅ API | ⬜ ключи | `DADATA_*` пусто |
| Telegram channel | ✅ connect + webhook | ⬜ токен | flag `telegram=true` (ожидает `TELEGRAM_BOT_TOKEN`) |
| MAX channel | ✅ | ⬜ | flag `max=false` |
| Instant demo | ✅ | ⬜ polish | зависит от публичных URL |
| Voice web widget / TTS | ✅ | ⬜ OpenAI | flag `web_voice=true`, нужен ключ |
| Telephony (Asterisk/AVA/Mango) | QO / AVA | ⬜ Phase D | **не трогаем** до стабильного A–B |
| Hermes multi-user profiles | отдельно | ⬜ | на VPS пока нет; не блокер кабинета |
| Beget backup restore | — | ⬜ | DC block `backup.beget.com`; только ручной scp → `/root/beget-backup/incoming/` |
| Старый QO MCP (`a.47z.ru`) | — | ❌ down | Beget недоступен; dogfood идёт через DELNO |

Полный реестр QO-инструментов для переноса: [`QUANTUM_OFFICE_TOOLS_AUDIT.md`](QUANTUM_OFFICE_TOOLS_AUDIT.md) (PR аудита).

## Как пользоваться прямо сейчас

1. Открыть **маркетинговый сайт v2**: http://161.104.89.123/ (hero «Клиенты пишут и звонят…», демо-орб, Crystal widget)
2. Кабинет: http://161.104.89.123:3020/ → `owner@quantumlabs.ru`
3. Пройти **Onboarding** (уже стартован)
4. **Knowledge** — seed + свои документы
5. Embed — snippet из `GET /v1/tenant/widget`

## Следующие шаги (порядок «скорее пользоваться»)

### Phase B1 — ключи (разблокируют умный чат + ИНН + TG)

Прописать в `/opt/delno/.env` на VPS (не в git), затем:

```bash
cd /opt/delno && docker compose up -d --force-recreate api
```

| Переменная | Эффект |
|------------|--------|
| `OPENAI_API_KEY` + `MODEL_PROVIDER=openai` | живые ответы operator/widget/TTS |
| `TELEGRAM_BOT_TOKEN` | `POST /v1/tenant/channels/telegram/connect` + webhook |
| `DADATA_API_KEY` + `DADATA_SECRET_KEY` | party lookup / suggest / legal |

В Cursor cloud сейчас **нет** этих secrets (есть только `POLYHUB_SSH_KEY`, `BITRIX_WEBHOOK_URL`).

### Phase B2 — Telegram как первый канал

1. Flag `telegram` уже **enabled** у `quantum-labs`  
2. После токена: connect bot → webhook `/delno-api/v1/webhooks/telegram/{account_id}`  
3. Inbox в кабинете

### Phase B3 — почта / календарь / файлы

Перенос коннекторов из QO (`mailer`, `calendar`, `files`) как adapters за feature flags — после TG.

### Phase C — voice widget

Уже есть код + CDN; нужен OpenAI (STT/TTS) и проверка mic в браузере.

### Phase D — телефония

Только после стабильного A–B. Asterisk/AVA/`/opt/polyhub` **не трогать**.

## Ops cheat-sheet

```bash
ssh root@161.104.89.123
systemctl status delno-stack nginx
docker ps
curl -sf http://127.0.0.1:18020/v1/health
curl -sf http://127.0.0.1:18021/api/brain/health
curl -sf -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3020/
```

Compose **без** сломанного `site` (нет `package.json` у DELNO-site-v23); сервис `web` = образ `delno-web:latest` на `:3020`.

## Site restore

`DELNO-site-v23` в git был без `package.json` / `tsconfig` / `globals.css` / `ScenarioSwitcher` — из‑за этого на bootstrap поднялась заглушка.  
Сейчас v2 собран и отдан на `/`; scaffold закоммичен в ветку `cursor/delno-site-restore-9b51`.

## Runtime-патчи на VPS (зафиксировать в delno-ветку позже)

- `tenant_widget_config` отдаёт `PUBLIC_API_BASE` / `PUBLIC_CDN_BASE` вместо hardcode `api.dlno.ru`
- nginx: `/delno-api`, `/delno-brain`, `/widget/`, landing `/`
- `MODEL_PROVIDER=stub` до появления OpenAI
