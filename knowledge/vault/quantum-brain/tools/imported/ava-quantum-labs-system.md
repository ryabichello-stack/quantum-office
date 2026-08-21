---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: imported:/root/ava/docs/AVA_QUANTUM_LABS_SYSTEM.md
shard: ava-quantum-labs-system
---

# Quantum Labs AVA — паспорт системы

> Imported from `/root/ava/docs/AVA_QUANTUM_LABS_SYSTEM.md` for Second Brain. Secrets must not be added here.

# Quantum Labs AVA — система телефонии и секретаря (база для бэкапа и переноса)

**Снимок состояния:** 2026-07-22  
**Прод-хост:** `gakgoudtua` / `5.35.86.62` (SSH alias обычно `polyhub`)  
**Назначение документа:** единый «паспорт» стека — понять, как всё связано, что бэкапить, как поднять на другом сервере.  
**Секреты в этот файл не входят** — только имена переменных и пути к файлам с секретами.

Связанный код upstream: Asterisk AI Voice Agent (AVA) в `/root/ava` на сервере.  
Кастом Quantum Labs: dialplan/PJSIP, `ai-agent.local.yaml`, knowledge, `/opt/ava-mailer`, `/opt/ava-text-bot`, `/opt/ava-outreach`.

---

## 1. Что это за система (одним абзацем)

Входящий звонок с номера **8 (800) 555-94-18** приходит через **Mango Office SIP** на **Asterisk**, Asterisk отдаёт канал в **Stasis-приложение** AVA (`asterisk-ai-voice-agent`). Контейнер **`ai_engine`** держит Realtime-сессию с **OpenAI** (`gpt-realtime-2.1`, голос `cedar`), во время звонка вызывает HTTP-tools на **`ava-mailer`** (календарь Mail.ru, Телемост Яндекс, база знаний). После звонка webhook шлёт лид-письмо на office и опционально fan-out в CRM. Рядом: Telegram text-bot (тот же «мозг») и Bitrix outreach по SMTP — **не** в SIP-пути.

Публичные контакты компании (из knowledge): сайт `https://quantumlabs.ru`, email `office@quantumlabs.ru`, телефон `8 (800) 555-94-18`.

---

## 2. Архитектура (runtime)

```mermaid
flowchart TB
  Caller[Caller PSTN] --> Mango[Mango Office SIP trunk]
  Mango -->|UDP 5060| Asterisk[Asterisk 20 host]
  Asterisk -->|Stasis asterisk-ai-voice-agent| ARI[ARI HTTP :8088]
  ARI --> Engine[ai_engine Docker host net]
  Engine -->|OpenAI Realtime| OpenAI[gpt-realtime-2.1 / cedar]
  Engine -->|in-call HTTP tools| Mailer[ava-mailer :8000]
  Mailer --> CalDAV[Mail.ru CalDAV]
  Mailer --> Telemost[Yandex Telemost OAuth]
  Mailer --> SMTP[smtp.mail.ru office@]
  Mailer --> Knowledge[/root/ava/config/knowledge/quantum_labs.md]
  Engine -->|post-call webhook| Mailer
  Engine --> CallDB[(/root/ava/data/call_history.db)]
  TextBot[ava-text-bot :8011] --> Mailer
  TextBot --> OpenAI
  Outreach[ava-outreach :8012] --> SMTP
  Outreach --> Bitrix[Bitrix24 b24-m5614z]
  LocalAI[local_ai_server :8765] -.->|optional local STT/TTS| Engine
  AdminUI[admin_ui] -.-> Engine
```

### Компоненты на диске

| Компонент | Путь | Как запускается | Порт / сеть |
|-----------|------|-----------------|-------------|
| AVA monorepo + конфиги | `/root/ava` | Docker Compose | host network |
| `ai_engine` | образ `asterisk-ai-voice-agent-ai-engine:latest` | `quantum-ava-docker.service` | health `:15000` |
| `local_ai_server` | образ `…-local-ai-server:latest` | тот же compose | WS `127.0.0.1:8765` |
| `admin_ui` | образ `…-admin-ui:latest` | тот же compose | host |
| Asterisk PBX | пакет ОС + `/etc/asterisk` | `asterisk.service` | SIP `5060/udp`, ARI `8088`, AMI `5038` |
| Канон PJSIP/dialplan | `/root/ava/config/asterisk/*.quantum-labs.conf` | копируется в `/etc/asterisk` скриптом | — |
| ava-mailer | `/opt/ava-mailer` | `ava-mailer.service` | `0.0.0.0:8000` |
| ava-text-bot | `/opt/ava-text-bot` | `ava-text-bot.service` | `127.0.0.1:8011` |
| ava-outreach | `/opt/ava-outreach` | `ava-outreach.service` | `127.0.0.1:8012` |
| **quantum-console** | `/opt/quantum-console` | `quantum-console.service` | `127.0.0.1:8013` — **наш** ops UI |
| Бэкапы | `/root/backups/` | вручную `backup_quantum_labs.sh` | — |

**Важно:** polyhub trading Docker-стек (`polyhub-backend`, postgres, grafana…) живёт на том же хосте, но **не** часть голосового секретаря. При переносе AVA его можно не трогать.

---

## 3. Поток входящего звонка (детально)

1. Mango маршрутизирует вызов на зарегистрированный SIP endpoint `mango-endpoint` (registration `mango-registration` → `vpbx…mangosip.ru`).
2. Asterisk принимает в context **`from-mango`** (`extensions.conf`).
3. Dialplan:
   - `Answer()`
   - `Set(AI_CONTEXT=default)`
   - `Set(AI_PROVIDER=openai_realtime)`
   - `Stasis(asterisk-ai-voice-agent)`
4. `ai_engine` по ARI подключается к каналу, поднимает OpenAI Realtime session по `contexts.default` + `providers.openai_realtime`.
5. Greeting: «Добрый день! Вы позвонили в Quantum Labs. Чем могу помочь?»
6. In-call tools (HTTP → mailer):
   - `check_calendar` → `POST /api/calendar/check`
   - `create_calendar_event` → `POST /api/calendar/create` (CalDAV + Telemost + welcome email)
   - `get_company_knowledge` → `POST /api/knowledge/query`
   - `hangup_call` (встроенный)
7. Post-call: `mailru_post_call` → `POST /api/ava/post-call` с `X-Webhook-Token`, транскрипт/саммари → письмо менеджерам + опциональный CRM fan-out.
8. История: SQLite `/root/ava/data/call_history.db` таблица `call_records` (на снимке ~131 запись). Аудиозапись звонков в прод-конфиге **не** является основным артефактом — опирайтесь на транскрипт в БД.

Тестовый локальный endpoint: `ava-test` (identify `127.0.0.1`) — для SIP E2E с хоста без Mango.

---

## 4. Systemd: порядок автозапуска

| Unit | Role | Enabled (снимок) |
|------|------|------------------|
| `quantum-asterisk-config.service` | **Before** `asterisk`: восстановить `pjsip.conf` + `extensions.conf` из `/root/ava/config/asterisk/` | yes |
| `asterisk.service` | PBX | yes / active |
| `quantum-ava-docker.service` | `docker compose up -d --no-build` в `/root/ava` | yes / active |
| `ava-mailer.service` | uvicorn mailer `:8000` | yes / active |
| `quantum-ava-boot.service` | post-boot: health mailer/engine + mango registration watch | yes / inactive oneshot после boot |
| `ava-text-bot.service` | Telegram text secretary `:8011` | yes / active |
| `ava-outreach.service` | Bitrix email outreach `:8012` | yes / active |
| `quantum-mango-pjsip.service` | legacy/disabled на снимке | disabled |

Скрипты:

- `/root/ava/scripts/ensure_asterisk_config.sh`
- `/root/ava/scripts/quantum_ava_docker_up.sh` — **без rebuild на boot**
- `/root/ava/scripts/quantum_ava_boot.sh`
- `/root/ava/scripts/mango_registration_watch.sh`
- `/root/ava/scripts/backup_quantum_labs.sh`
- `/root/ava/scripts/post_deploy_check.sh` → `quantum_e2e_test.py --quick`
- `/root/ava/scripts/quantum_e2e_test.py`

Лог boot: `/var/log/quantum-ava-boot.log`.

Контейнеры AVA: `RestartPolicy=unless-stopped`.

---

## 5. Asterisk / Mango (без секретов)

### Канонические файлы (источник правды)

- `/root/ava/config/asterisk/pjsip.quantum-labs.conf` → runtime `/etc/asterisk/pjsip.conf`
- `/root/ava/config/asterisk/extensions.quantum-labs.conf` → runtime `/etc/asterisk/extensions.conf`

Маркер для ensure-скрипта: в PJSIP есть `mango-registration`, в dialplan — `from-mango`.

### Логика PJSIP (структура)

- Transport UDP `0.0.0.0:5060`
- Auth/AOR/Endpoint/Identify/Registration для Mango (`vpbx400348777.mangosip.ru`, username в конфиге)
- Identify match: подсети Mango `81.88.86.0/24`, `81.88.87.0/24`, `137.74.16.0/24`
- Codecs: `alaw,ulaw`
- Endpoint `ava-test` для localhost

**Секреты SIP** лежат в plaintext в `pjsip.quantum-labs.conf` и копии в `/etc/asterisk/pjsip.conf` — обязательны в бэкапе, не коммитить в публичный git.

### ARI / HTTP

- `/etc/asterisk/http.conf`: enabled, `bindport=8088`
- `/etc/asterisk/ari.conf`: user `asterisk-ai-voice-agent` (пароль в файле; должен совпадать с `/root/ava/.env` → `ASTERISK_ARI_*`)
- Версия Asterisk на снимке: **20.6.0** (Ubuntu package)

### Firewall (UFW, снимок)

Обязательно для телефонии:

- `5060/udp` (SIP)
- `10000:20000/udp` (RTP media)
- `8000/tcp` (mailer OAuth callback снаружи — Yandex)

Также открыты 22/80/443 и др. (polyhub/xray) — при переносе **не** копировать слепо весь UFW, минимум SIP+RTP+нужный OAuth.

---

## 6. AVA Docker + runtime YAML

### Compose

Файл: `/root/ava/docker-compose.yml`  
Режим: **`network_mode: host`** (критично: `127.0.0.1` из engine = host Asterisk/mailer).

Сервисы: `ai_engine`, `local_ai_server`, `admin_ui`.

Образы (снимки ID меняются после rebuild):

- `asterisk-ai-voice-agent-ai-engine:latest`
- `asterisk-ai-voice-agent-local-ai-server:latest`
- `asterisk-ai-voice-agent-admin-ui:latest`

### Env

`/root/ava/.env` — секреты и привязка к Asterisk (не поведение агента):

- `ASTERISK_HOST`, `ASTERISK_ARI_PORT`, `ASTERISK_ARI_USERNAME`, `ASTERISK_ARI_PASSWORD`
- `OPENAI_API_KEY`
- `ASTERISK_UID` / `ASTERISK_GID`, recording path и пр.

Шаблон: `/root/ava/.env.example`.

### Поведение агента

Активный конфиг: **`/root/ava/config/ai-agent.local.yaml`** (~588 строк).

Ключевые значения (снимок 2026-07-22):

| Параметр | Значение |
|----------|----------|
| Context | `default` |
| Profile | `openai_realtime_24k` |
| Provider | `openai_realtime` |
| Model | `gpt-realtime-2.1` |
| Voice | `cedar` |
| Temperature | `0.4` |
| Transcription | `gpt-realtime-whisper`, language `ru` |
| Sample rate | 24000 Hz in/out |
| VAD | `server_vad`, silence `1700ms`, threshold `0.62` |
| Tools in-call | calendar check/create, knowledge, hangup |
| Post-call | `mailru_post_call` → mailer `/api/ava/post-call` |
| Prompt | ИИ-секретарь Quantum Labs, только русский, без «сейчас проверю» и т.п. |

Бэкапы YAML лежат рядом (`*.bak.*`) — при откате модели/голоса смотреть timestamps.

Knowledge:

- `/root/ava/config/knowledge/quantum_labs.md` — основной текст для tool
- docx в той же папке (источники для сборки knowledge)

---

## 7. ava-mailer (`/opt/ava-mailer`)

**Роль:** FastAPI «руки» секретаря — календарь, Телемост, knowledge, post-call email, welcome PDF, CRM fan-out.

- Process: `/opt/ava-mailer/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000`
- Unit: `ava-mailer.service`
- Лог webhook: `/opt/ava-mailer/webhook.log`
- OAuth tokens Яндекс: `/opt/ava-mailer/yandex_oauth_tokens.json` (+ `yandex_oauth.py`)
- Assets (PDF презентации): `/opt/ava-mailer/assets/`
- `PROTECTED_README.txt` — пометки «не ломать» критичные куски

### Env keys (имена)

`WEBHOOK_TOKEN`, `MAIL_SMTP_*`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_TO_DEFAULT`,  
`OPENAI_API_KEY`, `OPENAI_MODEL`,  
`MAILRU_CALDAV_*`, `MAILRU_CALENDAR_URL`, `CALENDAR_TIMEZONE`, `CALENDAR_DEFAULT_DURATION_MIN`,  
`YANDEX_OAUTH_*`, `TELEMOST_*`,  
`WELCOME_*`,  
`OUTREACH_CRM_URL`, `OUTREACH_CRM_TOKEN`,  
опционально `KNOWLEDGE_QUANTUM_LABS_PATH` (default → `/root/ava/config/knowledge/quantum_labs.md`).

SMTP на снимке: **Mail.ru**, ящик office (тот же контур, что welcome/лиды).

### HTTP API (важное)

| Method | Path | Назначение |
|--------|------|------------|
| GET | `/health` | liveness |
| POST | `/api/knowledge/query` | фрагмент knowledge по topic |
| POST | `/api/calendar/check` | свободен ли слот |
| POST | `/api/calendar/suggest` | предложить слоты |
| POST | `/api/calendar/create` | событие + Telemost + welcome email |
| POST | `/api/ava/post-call` | post-call лид (header token) |
| GET | `/oauth/yandex/start?token=` | старт OAuth Телемост |
| GET | `/oauth/yandex/callback` | callback |
| GET | `/oauth/yandex/status` | статус токена |

После переноса на новый хост **обязательно** обновить `YANDEX_OAUTH_REDIRECT_URI` в Яндекс OAuth-приложении и в `.env`, затем один раз пройти `/oauth/yandex/start?token=<WEBHOOK_TOKEN>`.

---

## 8. ava-text-bot (`/opt/ava-text-bot`)

Telegram text secretary: тот же system prompt из AVA YAML + tools через mailer.

- `:8011` localhost only
- `.env`: `TELEGRAM_BOT_TOKEN`, `OPENAI_*`, `AVA_MAILER_BASE=http://127.0.0.1:8000`, `AVA_CONFIG_PATH=/root/ava/config/ai-agent.local.yaml`
- Данные: `/opt/ava-text-bot/data/sessions.db`
- Исходники также в репо polyhub: `extras/quantum-text-bot/`

Без валидного `TELEGRAM_BOT_TOKEN` сервис деградирует (не отвечает в TG).

---

## 8a. quantum-console (`/opt/quantum-console`) — наш UI

Не стоковый AVA Admin (`:3003`), а **Quantum Labs Control Console** на `127.0.0.1:8013`.

Код: `extras/quantum-console/` в polyhub → install `scripts/install_prod.sh`.

Вкладки: статус стека / сценарий (greeting+prompt+model+voice) / knowledge / история звонков / **исходящий one-shot dial** / пакет+бэкап+чеклист секретов.

Доступ:

```bash
ssh -L 8013:127.0.0.1:8013 polyhub
# http://127.0.0.1:8013/  + заголовок/поле CONSOLE_TOKEN из /opt/quantum-console/.env
```

---

## 8b. Исходящие звонки (outbound)

### Что было сломано (и починено на Asterisk)

Раньше INVITE уходил как `From: <sip:…@45.147.178.172>` **без** `from_user`/`from_domain` → Mango сразу `403 Denied` (даже без digest).

Рабочий trunk (`pjsip.quantum-labs.conf`):

- `from_user=garik`
- `from_domain=vpbx400348777.mangosip.ru`
- `contact_user=garik`
- `outbound_auth=mango-auth`
- `external_*_address` = публичный IP хоста

После фикса SIP-цепочка: `INVITE → 401 → auth INVITE → 183 Session Progress` (ранние медиа / softswitch принял).

### Dialplan + AVA dialer

- `[from-internal]` — `Dial(PJSIP/${EXTEN}@mango-endpoint,…)` (цифры без `+`, обычно `7XXXXXXXXXX`)
- `[aava-outbound-amd]` — AMD hop для AVA Campaign Dialer
- Console one-shot: `PJSIP/<phone>@mango-endpoint` напрямую в Stasis

Env: `AAVA_OUTBOUND_PBX_TYPE=generic`, `CHANNEL_TECH=local_only`, `DIAL_CONTEXT=from-internal`.

### Оставшийся блокер со стороны Mango (по их документации, не догадки)

Проверено **2026-07-22** tcpdump на polyhub (SIP `garik`, Registered, digest OK, IP Beget/RU):

`INVITE → 401 → auth INVITE → 183 Session Progress → (~9s) 403 Forbidden`

Одинаково для `7…` / `8…` / 10 цифр, с PAI=`79699665899`, и при наборе на свой DID.

#### Что говорит документация Mango про исходящие для «бота»-сотрудника

1. **Авторизация линии = SIP**, не «номер для авторизации».  
   Карточка сотрудника → SIP login/password; «номер для авторизации» — вход в ЛК/Talker (SMS/2FA).  
   Источники: [создание сотрудников](https://www.mango-office.ru/support/virtualnaya_ats/bystryy_start/sozdanie_sotrudnikov/), [карточка](https://www.mango-office.ru/support/virtualnaya_ats/nastroyka_uslug/nastroyka_kartochki_sotrudnika/), [SIP-оборудование](https://www.mango-office.ru/support/tekhnicheskaya_podderzhka/baza_znaniy/nastroyki_sip_oborudovaniya/).

2. **Исходящие с Asterisk — штатный сценарий** через SIP сотрудника:  
   `fromuser`/`fromdomain` = SIP ID, `type=peer` (у нас PJSIP `outbound_auth` + `from_user=garik`), register на `vpbx….mangosip.ru`.  
   Канон: [Настройка Asterisk*](https://www.mango-office.ru/support/tekhnicheskaya_podderzhka/nastroyki_softfonov/linux/asterisk/nastroyka_asterisk/).  
   В их примере dialplan: `_8XXXXXXXXXX`. В FAQ ВАТС набор: **`7` + код + номер**. Оба формата у нас дают один и тот же 183→403.

3. **«Исходящий номер» в Телефонии** = АОН (что видит абонент). 8-800 нельзя. У бота уже `79699665899`.  
   [Карточка сотрудника](https://www.mango-office.ru/support/virtualnaya_ats/nastroyka_uslug/nastroyka_kartochki_sotrudnika/), [создание сотрудников](https://www.mango-office.ru/support/virtualnaya_ats/bystryy_start/sozdanie_sotrudnikov/).

4. **«Направления»** = whitelist географии; «по умолчанию» = общие [Безопасность и ограничения](https://www.mango-office.ru/journal/newsletter/sip-telefoniya-kak-zashchititsya-ot-zloumyshlennikov/). Для РФ обычно достаточно.

5. **Альтернатива SIP-originate (официально):** API `POST /vpbx/commands/callback` от **внутреннего номера** (`extension`, у бота `12`) + `to_number` + опционально `line_number` (АОН).  
   [Общие вопросы API](https://www.mango-office.ru/support/integratsiya-api/restapivatshelp/obshchie_voprosy_po_api_vats_mango_office/), PDF API v1.9.  
   Коды: **3124** «линия не подходит как исходящий», **1150** «ограничения для вызывающего номера», **2240** «недостаточно средств», класс **2xxx** биллинг.

6. **Автоматический/роботный исходящий (с 01.09.2025):** вызовы через АТС/SIP-приложения/роботов попадают под **МАВ**. Без договора МАВ + маркировки («Этикетка») оператор **не доводит** вызов до абонента.  
   Источники Mango: [МАВ сервис](https://www.mango-office.ru/products/mav-servis-markirovki-massovykh-vyzovov/), [холодные звонки 2025](https://www.mango-office.ru/journal/for-marketing/telephony-for-marketers/telefoniya-dlya-kholodnykh-zvonkov/) («номер не зарегистрирован как МАВ — вызов блокируется»).

SIP у нас по канону Asterisk* уже корректный. Симптом 183→403 совпадает с **отказом на стороне сети/биллинга/МАВ после принятия сессии**, не с ошибкой `from_user`.  
Пример Call-ID: `cf4e45f8-f67c-4bdf-83f6-27c65a7cdfbe`. В ЛК проверить: баланс, МАВ/Этикетка на `79699665899`, история вызова (disconnect_reason), тикет в techsupport@mangotele.com.

---

## 9. ava-outreach (`/opt/ava-outreach`)

Отдельный контур Bitrix → SMTP (office@). **Не зависит** от Asterisk/Mango.

- Портал: `https://b24-m5614z.bitrix24.ru/`
- API `:8012`
- Env: `BITRIX_WEBHOOK_URL`, `MAIL_*`, `OUTREACH_ENABLED` (держать `false` до явного batch)
- Код также в polyhub `extras/` / задеплоен на сервер

При бэкапе телефонии — включать; при «только голос» — можно отдельно.

---

## 10. Данные, которые нельзя потерять

| Артефакт | Путь | Критичность |
|----------|------|-------------|
| AVA конфиг + knowledge + asterisk canon | `/root/ava/config/` | P0 |
| AVA `.env` | `/root/ava/.env` | P0 |
| Call history SQLite | `/root/ava/data/call_history.db` | P0 (история/транскрипты) |
| Mailer code + `.env` + tokens + assets | `/opt/ava-mailer/` | P0 |
| Yandex OAuth tokens | `yandex_oauth_tokens.json` | P0 |
| Runtime Asterisk (если diverged) | `/etc/asterisk/pjsip.conf`, `extensions.conf`, `ari.conf`, `http.conf` | P0 |
| Systemd units | `/etc/systemd/system/ava-*.service`, `quantum-*.service` | P1 |
| text-bot + outreach `.env` + data | `/opt/ava-text-bot`, `/opt/ava-outreach` | P1 |
| Docker images | `docker save` образов AVA | P1 (иначе долгий rebuild) |
| `/root/ava/models/` | большие веса local AI | P2 (исключены из штатного tar-бэкапа) |

На снимке уже есть архивы в `/root/backups/`:

- `quantum-labs-full-20260602T103858Z.tar.gz` (~70M)
- `quantum-labs-full-20260602-104057.tar.gz` (~31M)

---

## 11. Бэкап (как делать сейчас)

Штатный скрипт на сервере:

```bash
ssh polyhub
bash /root/ava/scripts/backup_quantum_labs.sh
# опционально с E2E: RUN_E2E_ON_BACKUP=1 bash /root/ava/scripts/backup_quantum_labs.sh
```

Что кладёт в `/root/backups/quantum-labs-full-<UTC>/` и `.tar.gz`:

- `/root/ava` **без** `models/`, `.git`, `__pycache__`, `node_modules`
- весь `/opt/ava-mailer`
- куски Asterisk (`extensions*.conf`, статусы pjsip/dialplan)
- `ava-mailer.service`, `docker_ps`, image id `ai_engine`
- `RESTORE.md` внутри архива

### Рекомендуемое расширение бэкапа (делать вручную или дописать скрипт)

Добавить в архив также:

```bash
# пример дополнения
rsync -a /opt/ava-text-bot/ /root/backups/.../ava-text-bot/ --exclude venv --exclude __pycache__
rsync -a /opt/ava-outreach/ /root/backups/.../ava-outreach/ --exclude venv --exclude __pycache__
cp -a /etc/asterisk/ari.conf /etc/asterisk/http.conf /etc/asterisk/pjsip.conf \
  /etc/systemd/system/ava-*.service /etc/systemd/system/quantum-*.service \
  /root/backups/.../asterisk-extra/   # в отдельные подпапки
docker save asterisk-ai-voice-agent-ai-engine:latest \
  asterisk-ai-voice-agent-local-ai-server:latest \
  asterisk-ai-voice-agent-admin-ui:latest \
  | gzip > /root/backups/ava-images-<UTC>.tar.gz
```

Скопировать архив **off-box** (другой диск / S3 / ноутбук). Архив содержит секреты — шифровать при передаче (`age`/`gpg`).

Периодичность: минимум после любого изменения dialplan/YAML/mailer/OAuth; желательно weekly.

---

## 12. Восстановление на том же сервере

1. Распаковать архив.
2. `rsync -a ava/ /root/ava/` (осторожно с `.env`).
3. `rsync -a ava-mailer/ /opt/ava-mailer/`.
4. `cp` asterisk configs → `/etc/asterisk/` → `chown asterisk:asterisk` →  
   `asterisk -rx "module reload res_pjsip.so"` + `dialplan reload`.
5. `systemctl restart ava-mailer`.
6. `cd /root/ava && docker compose up -d` (или `systemctl start quantum-ava-docker`).
7. `bash /root/ava/scripts/quantum_ava_boot.sh` или дождаться boot unit.
8. Smoke:
   - `curl -sf http://127.0.0.1:8000/health`
   - `curl -sf http://127.0.0.1:15000/health`
   - `asterisk -rx "pjsip show registrations"` → `Registered`
   - `python3 /root/ava/scripts/quantum_e2e_test.py --quick`
9. При необходимости: Yandex OAuth re-auth.

---

## 13. Перенос на **другой** сервер (чеклист)

### A. Новый хост — база

- Ubuntu 22.04/24.04 x86_64, публичный IP (для SIP/RTP).
- Пакеты: `asterisk` (или тот же major 20.x), `docker` + compose plugin, `python3`, `rsync`, `ufw`.
- Открыть UFW: `5060/udp`, RTP range `10000:20000/udp`, `22/tcp`, при OAuth снаружи — `8000/tcp` (или reverse-proxy на 443).
- Пользователь/группа `asterisk` с UID/GID, согласованными с `/root/ava/.env` (`ASTERISK_UID/GID`).

### B. Перенос файлов

1. Доставить tar бэкапа + желательно `docker load` образов AVA.
2. Разложить:
   - `/root/ava`
   - `/opt/ava-mailer` (+ venv пересоздать: `python3 -m venv venv && pip install -r …` если requirements есть; иначе зависимости как на старом — зафиксировать `pip freeze` заранее)
   - `/opt/ava-text-bot`, `/opt/ava-outreach` по необходимости
3. Поставить systemd units из бэкапа / example-файлов в `/root/ava/scripts/*.service.example`.
4. `systemctl enable quantum-asterisk-config asterisk quantum-ava-docker ava-mailer quantum-ava-boot …`

### C. Сеть и провайдеры

1. **Mango Office:** убедиться, что trunk/IP whitelist допускает **новый** IP сервера (или registration-based — проверить кабинет Mango). Username/password SIP — из перенесённого `pjsip.quantum-labs.conf`.
2. Прописать DNS/A записи, если mailer OAuth/URL завязаны на домен.
3. Обновить `YANDEX_OAUTH_REDIRECT_URI` → новый URL mailer.
4. Mail.ru SMTP: обычно без смены IP ок; при блоке — app-password / разрешить новый IP.
5. OpenAI key — тот же или новый; квоты Realtime.
6. Bitrix webhook URL — без изменений (облако), если IP сервера не важен.

### D. Поднять и проверить

```bash
systemctl start quantum-asterisk-config asterisk
systemctl start quantum-ava-docker ava-mailer
bash /root/ava/scripts/quantum_ava_boot.sh
asterisk -rx "pjsip show registrations"
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:15000/health
python3 /root/ava/scripts/quantum_e2e_test.py --quick
# контрольный звонок на 8-800 / тестольный SIP test
```

### E. Cutover

1. В Mango переключить маршрутизацию на новый сервер (или дождаться стабильной registration с нового IP).
2. Старый сервер: `docker compose stop` / stop mailer **после** успешного пробного звонка.
3. Сохранить старый диск read-only ещё N дней.

---

## 14. Операционные команды (шпаргалка)

```bash
# статус
systemctl status asterisk ava-mailer quantum-ava-docker --no-pager
docker ps --filter name=ai_engine --filter name=local_ai_server --filter name=admin_ui
asterisk -rx "pjsip show registrations"
asterisk -rx "pjsip show endpoints"
asterisk -rx "dialplan show from-mango"

# логи
journalctl -u ava-mailer -n 100 --no-pager
journalctl -u quantum-ava-boot -n 100 --no-pager
docker logs ai_engine --tail 100
tail -50 /opt/ava-mailer/webhook.log
tail -50 /var/log/quantum-ava-boot.log

# безопасный рестарт голоса (без docker build на нагруженном хосте)
cd /root/ava && docker compose up -d --no-build
systemctl restart ava-mailer
bash /root/ava/scripts/mango_registration_watch.sh

# восстановить dialplan/pjsip с канона
bash /root/ava/scripts/ensure_asterisk_config.sh
```

**Не делать на проде без нужды:** `docker compose build` / `up --build` под нагрузкой (в истории уже роняло хост).

Опасные эксперименты с моделью: раньше `gpt-live-1` давал invalid_model + reconnect storm. Рабочий прод-профиль: **`gpt-realtime-2.1` + `cedar`**.

---

## 15. Инвентарь секретов (чек-лист переноса)

Скопировать **файлами**, значения сюда не записывать:

- [ ] `/root/ava/.env`
- [ ] `/root/ava/config/asterisk/pjsip.quantum-labs.conf` (SIP password)
- [ ] `/etc/asterisk/ari.conf` (ARI password = env)
- [ ] `/opt/ava-mailer/.env`
- [ ] `/opt/ava-mailer/yandex_oauth_tokens.json`
- [ ] `/opt/ava-text-bot/.env`
- [ ] `/opt/ava-outreach/.env` (Bitrix webhook)
- [ ] OpenAI / Mail.ru / Yandex OAuth client secret / Mango SIP / Bitrix webhook — ротация при компрометации бэкапа

---

## 16. Связь с репозиторием polyhub

| В polyhub git | На сервере |
|---------------|------------|
| `extras/quantum-text-bot/` | `/opt/ava-text-bot` |
| `extras/quantum-outreach/` (если есть) | `/opt/ava-outreach` |
| этот документ `docs/AVA_QUANTUM_LABS_SYSTEM.md` | копия для людей; **runtime truth** — файлы на `gakgoudtua` |

Сам monorepo AVA (`/root/ava`) на проде **не** является submodule polyhub в текущей схеме — бэкапьте с сервера.

---

## 17. Definition of done для «подняли на новом сервере»

- [ ] Mango registration = `Registered`
- [ ] Входящий звонок на 8-800 → greeting Quantum Labs
- [ ] Tool knowledge отвечает по услугам/СБП
- [ ] Запись встречи создаёт событие в Mail.ru + (если OAuth жив) ссылку Телемост
- [ ] Post-call письмо уходит на `MAIL_TO_DEFAULT`
- [ ] `call_history.db` пишет новую `call_records`
- [ ] После reboot хоста стек сам поднимается (asterisk-config → asterisk → docker → mailer → boot/mango)

---

*Документ обновлять при смене модели/голоса, trunk Mango, путей mailer или состава systemd. Дата снимка указана в шапке.*
