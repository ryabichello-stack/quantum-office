# DELNO: общий реестр изменений агентов

Этот файл — журнал координации работы Cursor и Codex на сервере `/opt/delno` и в git (`docs/AGENT_CHANGE_REGISTER.md`). Перед правкой прочитайте последние записи и проверьте состояние указанных файлов. После правки добавьте запись. Не переписывайте чужие записи. Секреты и токены сюда не помещать.

Формат записи: дата (МСК), автор, цель, файлы, изменение, проверка, статус, следующий шаг/ограничение.

## 2026-11-17 — Codex: финальный isolated Hermes smoke для PR #121

- На C4B собраны отдельные образы из PR, production-контейнеры и флаги не менялись. Внутренняя сеть, одноразовая SQLite; два tenant × Owner/background. Установленный Hermes `_RunLaunch → MCP handler → HTTP` выполнил 24 параллельных вызова. Серверные события после отрицательных проверок: `26/26 auth_via=run_token`, четыре run, два tenant, unscoped=0.
- Legacy key → 403, истёкший token → 401, завершённый run → 401, чужой profile → 403. Фоновое задание без владельца получает `system_event`; роль обычного владельца перечитывается планировщиком.
- Дополнительная находка: `get_tenant_summary` в текущем production выдаёт полный `tenant.settings` (включая MCP key), `update_tenant_settings` возвращает и аудирует его, может заменить служебные поля. В PR оба инструмента ограничены публичными бизнес-полями; проверены отсутствие ключа/грантов в ответе и запрет изменения. Production пока не исправлен до отдельного rollout.
- API tests: 449 passed, 1 deselected (внешний DNS). Полный разговор с внешней LLM не тестировался: использован контролируемый Agent поверх реальных установленных Hermes run/handler и HTTP API. Последний коммит PR должен пройти CI. Merge/deploy/боевые флаги не разрешены; Gate 1 открыт до production proof.

## 2026-11-17 — Codex: security review PR #121, backup restore

- Ветка `codex/delno-mcp-gate1`, PR #121; production, Hermes Pool, каналы и телефония не изменялись.
- Review нашёл обход grants через JWT, diagnostic mint, replay завершённого run, неполную проверку legacy binding и owner-role у фонового задания без пользователя. Исправления внесены в `delno-api/app/api/v1/mcp.py`, `hermes_nous.py`, `services/hermes_nous/{bridge,run_bindings,run_tokens,tool_packs}.py`, `agent_schedule.py`; тесты дополнены.
- На C4B существующий и свежий DB dumps реально восстановлены в изолированном PostgreSQL; свежая копия совпала с источником по counts `6/6/6/15`. Шесть profile dirs и 18 файлов volume восстановлены и побайтно сравнены. Временный контейнер, сеть и копии удалены; production `/health=200`.
- API: 446 passed, 1 deselected (внешний DNS). Подробный протокол и rollout: `docs/DELNO_MCP_GATE1_2026-11-17.md`. Gate 1 открыт: повторить CI и проверку реального Hermes после review, затем отдельно согласовать production. Merge/deploy/боевые флаги запрещены до решения владельца.

## 2026-11-17 ~10:20 МСК — Cursor: #113 merged + prod e2e

- GitHub: PR #113 влит в `main` (`4fed2eb`).
- E2E `delno-public` marketing bot: ответ по фактам → подтверждение телефона → lead создан.
- Файлы: tenant A видит свой файл; B list пуст; download B → `file_not_found` (IDOR закрыт).
- Календарь: встреча создана у A, у B той же записи нет.
- Webhook TG smoke из контейнера API (секрет не логировался). Health 200.
- Телефонию/Mango/Asterisk/VPN не трогали.

## 2026-11-17 ~10:15 МСК — Cursor: боевой выпуск боты+календарь+файлы

- Ветка `cursor/delno-bots-calendar-files-9b51` / PR #113 выложена на C4B: api/web/calendar/files/conference/mail.
- Compose: `TENANT_FILES_ROOT=/data/tenants`, volume `delno-tenant-files` смонтирован в api. Backup: `/opt/delno/backups/prod-bots-cal-files-*`.
- Alembic: таблицы уже были → `stamp 009_tenant_folders`. Health api/calendar/files/conference/mail = 200. Каналы delno-public TG+MAX active.
- Образы rollback: `delno-*:before-bots-cal-files-*`. Телефонию/Mango/Asterisk/VPN не трогали.
- Осталось: живой e2e ботов→лид; UI smoke календарь/файлы; merge #113 после зелёного CI.

## 2026-11-17 — Cursor: боевой контур боты + календарь + файлы

- Ветка `cursor/delno-bots-calendar-files-9b51` (base `main`): слиты #112 (публичные боты) и #111 (календарь/файлы). Конфликт `channel_auto_reply`: сначала `delno-public` marketing bot, иначе identity для встреч.
- Цель: на боевом C4B DELNO сам ведёт клиентов (@Dlno_bot / MAX / сайт → лиды), а кабинет компании даёт календарь и файлы с изоляцией 152‑ФЗ.
- Боевой C4B / `main`: выкладка после CI и backup; телефонию/Mango/Asterisk/VPN не трогать.
- Следующий шаг: тесты → PR в `main` → compose `delno-tenant-files` + alembic 008/009 → smoke ботов/календаря/файлов.

## 2026-11-17 — Codex: аудит публичных ботов DELNO и ботов Знатно

- Файлы: `docs/DELNO_ZNTN_BOT_AUDIT_2026-11-17.md`, `DELNO-site-v23/app/v2/page.tsx`, `CHANGELOG.md`.
- Проверены исходники ботов в Beget backup, текущие API/БД DELNO и Знатно, действительность бот-токенов без вывода секретов, исходящий сетевой маршрут. В v2 ссылки Telegram/MAX исправлены на ботов DELNO; выкладка после подключения этих ботов к новому публичному tenant.
- Факты: старые публичные systemd-боты DELNO на C4B отсутствуют; Telegram и MAX токены из архива действительны, но `channel_accounts` пуст. У Знатно MAX-токен действителен, Telegram-токен даёт 401; прямой egress контейнера отсутствует, через локальный proxy доступ есть. Три MAX webhook-подписки требуют очистки дубликатов.
- Статус: аудит и правка ссылок в git-ветке, прод ботов не менялся. Знатно — отдельный репозиторий; не смешивать его токены, БД и сценарии с DELNO.
- Дополнительный блокер подключения: `ChannelAccount.credentials_encrypted` и `tenant_vault` сейчас содержат токены в обычном JSON; до записи архивных токенов в БД нужно настоящее шифрование. Копия продовой схемы отдельно обновлена 007→008→009; API на последнем состоянии ветки: 431 passed.

## 2026-11-17 — Codex: раздел «Файлы» и схема таблиц

- Файлы: `delno-web/components/AppShell.tsx`, `delno-web/app/dashboard/files/page.tsx`, `delno-web/app/dashboard/calendar/page.tsx`, `docs/DELNO_PRESENTATION_GENERATORS_2026-11-17.md`, `CHANGELOG.md`.
- Перенёс загрузку файлов из календаря в отдельный раздел кабинета; добавил папки, скачивание, перемещение и удаление в UI и tenant API. Миграция `009_tenant_folders`, сервис `tenant_attachments.py`, инструменты Hermes `files.*` с tenant context и подтверждением удаления. Зафиксировал локальный конвейер PPTX/PDF и разграничение: Hermes выбирает операции, профильный инструмент обрабатывает содержимое, LibreOffice конвертирует и рендерит.
- Проверено: сборка кабинета и tenant isolation на двух компаниях в серверном тестовом контейнере. Полный набор API тестов выполняется в текущей ветке.
- Ограничение: Hermes пока создаёт только TXT/Markdown/CSV/HTML; чтение текста ограничено. Генерация DOCX/PDF/PPTX/XLSX и извлечение вложений из входящей почты требуют отдельных серверных маршрутов. На прод не выкладывалось.

## 2026-11-17 — Codex: изоляция офисных отправок по компании

- Цель: исключить общие серверные учётные данные в видеовстречах, письмах и отправке файлов.
- Файлы: `delno-office/{conference,calendar,files,mail}/*`, `delno-api/app/{adapters/connectors,services,operator/tools}/*`, тесты и `docs/DELNO_OFFICE_TOOL_INVENTORY_2026-11-17.md`.
- Изменение: видеовстречи требуют токен провайдера из сейфа tenant; общие приглашения отключены. Почтовый шлюз и файловая отправка сверяют tenant в теле и заголовке; файловая отправка требует собственные доступы к источнику и доставке. Календарь не вызывает общий Телемост/старый mailer для обычной компании. Вызов почты из сценария встречи получает проверенные реквизиты компании. Внешние события обновляются/удаляются через доступ tenant; общий Quantum Outreach закрыт для других компаний.
- Проверка: API `427 passed`; calendar, conference, files, mail broker tests запускались в отдельных контейнерах на C4B, без изменения прод-сервисов. Живые внешние OAuth/SMTP аккаунты не использовались.
- Статус: ветка `codex/tenant-calendar-origin`, PR #111; **прод не обновлён** на момент этой записи. Следом нужны review, сквозная проверка A/B на проде, проверка внешнего update/delete на реальных провайдерах, письмо с выбранным файлом на реальном SMTP и привязка контакта между каналами.

**Где лежит:** git `docs/AGENT_CHANGE_REGISTER.md` ↔ прод `/opt/delno/docs/AGENT_CHANGE_REGISTER.md` (держать в синхроне).

## 2026-11-17 — Codex: Gate 1 MCP isolation candidate, без production

- Ветка `codex/delno-mcp-gate1`; файлы `delno-api/app/api/v1/mcp.py`, `hermes_nous.py`, `services/mcp_gateway.py`, `hermes_runtime/*`, compose, tests и `docs/DELNO_MCP_GATE1_2026-11-17.md`.
- Проверены два тенанта, параллельные HTTP/MCP-вызовы, подмены, отзыв binding, права actor и обратное переключение флагов. Локальный тест patch against upstream v0.23.2 прошёл. Production не трогали.
- Флаги по умолчанию выключены. Не менять prod, не включать `DELNO_MCP_DENY_LEGACY_KEY` до зелёного CI, живого Hermes E2E с двумя профилями и отдельного согласования владельца. Rollback и ограничения описаны в документе Gate 1.

## 2026-11-17 — Codex: публичные боты DELNO отдельно от кабинетов клиентов

- Ветка `codex/delno-public-bots`: отдельный ответчик для tenant `delno-public` без вызова бизнес-инструментов; явное подтверждение перед созданием лида. Сайт направляет лиды/виджет в этот tenant и ссылается на ботов DELNO.
- Бот-токены и webhook-секреты `ChannelAccount` шифруются с ключом, производным от продового `JWT_SECRET`. Форма подключения больше не записывает бот-токен в `tenants.settings`. Остальные секреты сейфа пока остаются в JSON — отдельная работа.
- Проверка в изолированном контейнере: API `429 passed`; прод пока не изменён. Для выпуска: резервная копия, выделить tenant, HTTPS `API_PUBLIC_BASE_URL`, подключить архивные токены без печати, проверить Telegram/MAX вход и ответ, затем сменить публичный tenant сайта. Знатно остаётся отдельным сервисом; Telegram-токен там даёт 401.
- В ходе включения на C4B создан tenant `delno-public`, API обновлён и отвечает `/health=200`, Telegram подключён. MAX выявил `CERTIFICATE_VERIFY_FAILED`: официальный MAX API использует Russian Trusted CA, отсутствующий в базовом контейнере. Добавлен публичный корневой сертификат с проверенным SHA-256 и отдельный TLS-контекст; MAX ещё не переподключён после сборки.

## 2026-11-15 — Codex для Cursor: отключение постоянного MCP-ключа отложено

- Исправление доступа по одному `X-Delno-Run-Id` уже в `main` (PR #102): идентификатор запуска больше не является секретом; требуется ключ той же компании. Это не требует изменения текущего подключения Hermes.
- **Не включать пока** `DELNO_MCP_DENY_LEGACY_KEY=1` или `DELNO_MCP_STRICT=1` на рабочем сервере. Конфигурация профиля Hermes по-прежнему задаёт статический `Authorization: Bearer ${DELNO_MCP_KEY}`; `X-Delno-Run-Id` в ней закомментирован. API передаёт per-run token в заголовках `create_run`, но нет подтверждения, что upstream Hermes переносит его в каждый MCP-вызов. Немедленный запрет ключа может отключить бизнес-инструменты у всех компаний.
- Техническая задача: обеспечить передачу scoped run token из контекста каждого запуска в каждый MCP-запрос Hermes, с изоляцией одновременных запусков разных компаний на общем воркере. Проверить по живому запросу `auth_via=run_token`, запретить подстановку чужого run/profile/tenant и проверить вызовы инструментов для двух тенантов параллельно.
- Только после успешного теста убрать статический `DELNO_MCP_KEY` из профилей и включить запрет legacy-ключа. Отдельным PR и с планом отката. Сейчас это улучшение защиты, а не причина ломать рабочий онбординг.

## 2026-11-15 — Codex: сведение онбординга и подключений по тенанту

- Ветка: `codex/onboarding-integration-20261115`; объединены подготовленные исправления онбординга с PR #99, без выкладки на сервер.
- Подключение почты, календаря и конференций получает статус `connected` только после проверки учётных данных конкретного тенанта. Включение сервиса или успешная проверка общего сервера не считаются подключением.
- Сохранены исправления этапов Hermes, SIP-формы Mango, честного прогресса и повторного открытия формы при ошибке. Форму календаря Mail.ru уточнили для неспециалиста.
- Проверка: API `418 passed`; брокеры calendar `4 passed`, files `5 passed`; `delno-web` production build успешен. Живые внешние аккаунты и полный пользовательский путь на сервере не проверены.
- Следующий шаг: review/merge, затем серверный smoke с двумя разными тенантами и проверкой отсутствия доступа к чужим данным. Отдельно закрыть аутентификацию `X-Delno-Run-Id` в MCP, прежде чем расширять пилот.

## 2026-11-15 ~17:45 МСК — Cursor: изоляция календаря и облаков по тенанту

- Автор: Cursor, ветка `cursor/tenant-calendar-files-isolation-a44a`. Не деплоить.
- Цель: delno-calendar и delno-files не читают общий env-токен для чужой компании. Креды — из сейфа тенанта (как `files_cloud.py`).
- Файлы: `delno-office/calendar/*`, `delno-office/files/sources.py`, `delno-office/files/main.py`, `delno-api/app/services/calendar_accounts.py`, `tenant_broker_access.py`, `tenant_vault.py`, коннекторы calendar/files, `office.py`, `appointments.py`.
- Изменение: запрос без tenant_id или с несовпадающим `X-Tenant-Id` → 403. Env только при `allow_env_fallback`, который API ставит служебному тенанту (`settings.service_tenant` или `DELNO_SERVICE_TENANT_SLUG`). Секреты в логи и в ответ не копируются.
- Проверка: pytest брокеров calendar/files isolation + `tests/test_tenant_calendar_files_isolation.py` + `tests/test_connector_connect.py` + vault/connectors/onboarding paths.
- Дополнение: флоу подключения календаря (Google OAuth / CalDAV Яндекс и Mail.ru / Outlook / внутренний DELNO), почты и видеовстреч. Статус connected только после пробы чтения, не по флагу enabled. Формы с примером ivan@example.ru. Секреты в ответ и в лог пробы не пишутся.
- Статус: в git, без выкладки на `/opt/delno`.
- Ограничение: GitHub-токен файлового брокера и локальный allowlist всё ещё серверные. Живой SMTP/Graph в этой среде не вызывался — проба покрыта подменой и memory-режимом брокера.


## 2026-11-13 ~04:05 МСК — Cursor: fix SIP probe host.docker.internal

- Что: на C4B в `/opt/delno/docker-compose.yml` у `api.extra_hosts` была склеена строка `host.docker.internal,delno-hermes-tenant-a,delno-hermes-tenant-b:host-gateway` → DNS внутри контейнера не резолвил `host.docker.internal`, `sip_probe` всегда `reachable=false`, hermes_ops phone не мог стать Registered.
- Файлы: прод `/opt/delno/docker-compose.yml` (backup `.bak.extra_hosts`); git SoT уже корректен — `delno-api/deploy/docker-compose.stack.yml` (`host.docker.internal:host-gateway` одной записью).
- Проверка: `docker exec delno-api` → resolve `172.17.0.1`; `probe_registration()` → `ok=true status=registered`; Ava toolkit: «регистрация OK».
- Статус: выкатано на C4B recreate `delno-api`. Не склеивать несколько hostname в одной `extra_hosts` строке.
- Следующий шаг: demo tenant всё ещё `need_sip` (нет vault SIP / DID) — это ожидаемо по PRODUCT_LOOP.

## 2026-11-13 ~02:00 МСК — Cursor: Hermes Nous lead.created + lab image + tests

- Что: `events_dispatch.on_lead_created` wired from `leads.create_lead_record`; sqlite integration suite expanded; hermes_runtime Dockerfile → Python 3.14 + `uv sync --frozen` (pip conflict Pillow/browser-harness); C4B lab under `/opt/delno/lab/hermes_runtime` (не prod API/telephony).
- Файлы: `delno-api/app/services/hermes_nous/events_dispatch.py`, `leads.py`, `events.py`, `tests/test_hermes_nous_integration.py`, `hermes_runtime/Dockerfile`, `scripts/lab_smoke.sh`, `CHANGELOG.md`, `docs/hermes-nous/MASTER_PLAN.md`.
- Проверка: `pytest tests/` → 241+ passed; C4B lab build/smoke (без Asterisk).
- Статус: в git ветке `cursor/hermes-nous-runtime-9b51`.

## 2026-11-12 22:42 МСК — изменения Cursor, наблюдение Codex

- Автор: Cursor по сообщению владельца; точный состав правок следует уточнять по текущему коду.
- Файл: `/opt/delno/api/app/operator/agent.py`.
- Наблюдение: обновлены инструкции агента для вызова инструментов перед ответом, добавлены ограничения на повторение шагов и расход токенов. Файл менялся во время диагностики; считать состояние на сервере текущим источником перед следующей правкой.
- Статус: запущен до следующей правки Codex; отдельная функциональная проверка этой записи не проводилась.

## 2026-11-12 22:48 МСК — Codex: обнаружение возможностей Гермеса

- Цель: дать Гермесу обзор разрешённых инструментов и различать доступность сервиса от доступа конкретного клиента.
- Файлы: `/opt/delno/api/app/operator/tools/hermes.py`, `/opt/delno/api/app/operator/tools/__init__.py`, `/opt/delno/api/app/operator/agent.py`.
- Изменение: добавлен `hermes.capabilities`; инструмент зарегистрирован и включён в кабинетный список. Он показывает разрешённые действия, проверяет сервисы, отдельно отмечает `service_reachable`, `service_ready`, `tenant_authorized`, `usable`, а также список поставщиков ВКС/календаря. Результат передаётся модели структурированно.
- Проверка: `py_compile`; Docker-образ API собран и запущен. Вызов инструмента выполнен для `delno-demo`, `tenant-beta`, `quantum-labs`; чужие учётные данные не смешиваются. Все внешние коннекторы пока помечены `usable=false`, поскольку их отдельная авторизация для клиента не подтверждена.
- Статус: развернуто. Это реестр возможностей, не завершённый онбординг и не подключение внешних аккаунтов.
- Следующий шаг: ввести единую модель учётных записей и прав коннекторов на `tenant_id`; связать её с формами авторизации и фактическим выполнением действий, затем использовать в пошаговом онбординге Гермеса.

## 2026-11-12 22:55 МСК — Codex: честная готовность онбординга для всех клиентов

- Цель: убрать ложный статус «готово», когда доступен только общий сервис без учётной записи конкретного клиента.
- Файлы: `/opt/delno/api/app/services/connectors.py`, `/opt/delno/api/app/services/hermes_ops.py`, `/opt/delno/api/app/operator/tools/hermes.py`, `/opt/delno/api/app/operator/agent.py`.
- Изменение: вынесена общая проверка `list_tenant_connector_readiness`: доступность сервиса, готовность поставщика и подтверждённый доступ tenant оцениваются отдельно. Гермес получает эту структуру; чеклист онбординга использует фактическую готовность. ВКС проверяется по выбранному поставщику, а не по любому доступному.
- Проверка: сборка образа API; отдельный вызов `office_setup_status` для `delno-demo`, `quantum-labs`, `tenant-beta` показал корректные отдельные статусы. API пересобран и запущен; импорт `app.main` успешен.
- Статус: развёрнуто. Для почты, календаря, ВКС и outreach пока нет подтверждения отдельной учётной записи tenant в адаптерах, поэтому они честно показываются как неготовые.
- Следующий шаг: реализовать отдельные подключения и проверку прав на tenant для каждого сервиса; после этого readiness сможет стать true без изменения чеклиста.

## 2026-11-12 23:00 МСК — Codex: защита SIP между клиентами

- Цель: не допустить, чтобы сохранение SIP другого клиента изменило одну общую конфигурацию Asterisk.
- Файлы: `/opt/delno/api/app/services/sip_probe.py`, `/opt/delno/api/app/services/tenant_vault.py`, `/opt/delno/.env` (только новый идентификатор разрешённого клиента, без секрета).
- Изменение: автоматическое применение SIP к устаревшему общему Asterisk разрешено только для явно указанного tenant. Для остальных данные сохраняются, но применение блокируется с объяснением причины. Это временная защита до tenant-aware маршрутизации телефонии.
- Проверка: `py_compile`; тестовый вызов для другого tenant вернул `tenant_route_not_configured` до передачи данных в Asterisk. API пересобран и запущен, импорт приложения успешен.
- Статус: развёрнуто. Нужен отдельный механизм маршрутизации SIP/DID для каждого клиента; текущая общая линия не является многопользовательским решением.

## 2026-11-12 23:54 МСК — Cursor: multi-step Hermes agent + OpenAI tool names (PR #79)

- Автор: Cursor (`cursor/hermes-web-agent-loop-9b51` → PR https://github.com/ryabichello-stack/quantum-office/pull/79, base `cursor/tenant-files-privacy-9b51` / #78).
- Цель: настоящий агент-цикл в кабинете (сам планирует шаги), а не одноразовый tool call / phrase router; починить падение каталога tools на OpenAI.
- Файлы (git `delno-api/`): `app/operator/agent.py`, `app/operator/tools/registry.py`, `app/operator/tools/web.py`, `app/operator/tools/builtin.py`, `app/services/web_browser.py`, `app/services/model_provider.py`, `app/core/config.py`, тесты `tests/test_hermes_web_agent.py`, `tests/test_tool_openai_names.py`.
- Изменение:
  - multi-round loop: soft-stop / no-progress (тот же tool+args ×N) / token budget / `HERMES_AGENT_MAX_ROUNDS` (default 25);
  - убраны keyword «web research» блокировки KB;
  - debug-блок `— отладка (сбои) —` (`HERMES_DEBUG_FAILURES`);
  - отказ от пустого soft-stop «сейчас схожу…» → один forced tool round;
  - **критично:** имена tools для OpenAI без точек (`web.search`→`web_search`) + resolve обратно — иначе весь catalog давал HTTP 400 и агент не вызывал tools;
  - DuckDuckGo search: retry proxy→direct.
- Проверка на Cloud4Box: health ok; live `_try_cabinet_llm_tools` на `tenant-beta` — цепочка `web.search`→`web.fetch`→ответ со ссылками ФНС/КонсультантПлюс. После правок Codex нужно заново сверить сосуществование с `hermes.capabilities` (не затирать чужой код вслепую).
- Статус: выкатано на `/opt/delno` в ходе сессии Cursor; git/PR #79. Прод после Codex мог пересобрать API поверх — перед следующей правкой `agent.py`/`hermes.py` сверить diff git↔`/opt/delno/api/app`.
- Следующий шаг: не дублировать phrase-routers; продолжать agent-loop + tenant-aware connectors из открытых задач ниже. При конфликте с Codex — merge по файлам, не overwrite.

## 2026-11-12 23:55 МСК — Cursor: реестр в git + подтяжка правок Codex с прода

- Цель: не потерять работу Codex при следующем deploy из git; общий реестр в репозитории.
- Файлы: `docs/AGENT_CHANGE_REGISTER.md`, `AGENTS.md`, `delno-api/AGENTS.md`; с прода в git: `hermes.py` (`hermes.capabilities`), `connectors.py` (`list_tenant_connector_readiness`), `hermes_ops.py`, `sip_probe.py` (SIP tenant guard), `__init__.py`, фрагменты `agent.py`/`tenant_vault.py`.
- Проверка: локально `register_builtin_tools` → 32 cabinet specs вкл. `hermes_capabilities` + `web_search`; unit-тесты Hermes web/names зелёные. На проде уже сосуществуют agent-loop Cursor и capabilities Codex.
- Статус: записано в git (PR #79) и `/opt/delno/docs/AGENT_CHANGE_REGISTER.md`.

## 2026-11-13 00:00 МСК — Cursor: восстановление secretary tools (календарь/Телемост/почта)

- Автор: Cursor, ветка `cursor/secretary-office-tools-9b51`.
- Цель: вернуть универсальные тулы секретаря Quantum Office для всех клиентов (не только QL): проверка слота, создание встречи + Telemost, уже существующие suggest/mail/conference.
- Источник правды старого поведения: `docs/AGENTS_AVA_VOICE.md`, `/opt/quantum-office` (qo-calendar/mailer/conference), `delno-office/calendar` API `check|suggest|create`.
- Файлы: `delno-api/app/adapters/connectors/calendar.py` (`check_slot`, `create_event`), `delno-api/app/operator/tools/office.py` (`check_calendar`, `create_calendar_event`), регистрация в `__init__.py`, кабинетный каталог `agent.py`.
- Изменение: Hermes/operator могут вызывать `check_calendar` → `create_calendar_event` (critical_write) как на старой линии AVA; stub без `CALENDAR_BASE_URL`, live через calendar broker. `send_mail_draft` / `create_conference` / `suggest_calendar_slots` уже были.
- Проверка: unit `test_connectors.py` (stub check/create + confirmation classes).
- Статус: в git; выкатка на `/opt/delno` в том же ходе. Cancel/reschedule ещё нет API у брокера — в открытых задачах.
- Следующий шаг: tenant CalDAV/OAuth credentials → `usable=true` в readiness; cancel/update event в calendar broker; прокинуть те же tool id в живой telephony handler.

## Открытые архитектурные задачи для Cursor и Codex

- Секреты в `tenant_vault.py` сейчас сохраняются как значения в `Tenant.settings` JSON. До массового онбординга нужны шифрование с управляемым ключом, миграция существующих данных и проверка, что секреты не попадают в ответы API и логи.
- `mail`, `calendar`, `conference`, `outreach` используют общие серверные сервисы. Их health не подтверждает права отдельного tenant. Нужны отдельные учётные записи/токены и проверка действия в контексте tenant.
- `telephony_script.py` сохраняет разрешённые инструменты в настройках tenant; необходимо доказать, что живой обработчик звонка читает и соблюдает их. Выбор голоса в `tenant_voice_profiles` пока не подтверждён на действующей линии.
- После подключения нового коннектора Гермес должен получать обновлённый каталог возможностей, продолжать сохранённую задачу после формы/подтверждения и проверять фактический результат.
- SIP: tenant-aware маршрутизация / отдельные линии (сейчас общая Asterisk + allowlist одного tenant).
- Calendar broker: API cancel/reschedule (перенос/отмена) — в старом AVA/mailer тоже не было; нужен новый CalDAV update/delete, затем тулы Hermes.
- Clarify email: в legacy только промпт секретаря, отдельного tool `ask_email` не было — оставляем агенту, не phrase-router.


## 2026-11-15 — Codex: авторизация MCP run binding

- Ветка: `codex/mcp-run-binding-auth-20261115`; прод не изменён.
- Исправлено: `X-Delno-Run-Id` только находит привязку запуска. Для доступа обязателен ключ того же тенанта; чужой профиль или несовпадающий run token отклоняется.
- Файлы: `delno-api/app/api/v1/mcp.py`, `delno-api/tests/test_run_bindings_mcp.py`, changelog и этот реестр.
- Проверка: 381 тест API прошёл. Нужен живой smoke MCP после выкладки.
- Ограничение: долгоживущий tenant MCP key всё ещё имеет широкий доступ при обычном legacy-вызове без run id. Это отдельное ужесточение после подтверждения динамической передачи run token клиентом Hermes.

## 2026-11-15 ~03:35 МСК — Cursor: Ava без скрипта/тулов (calls/tool 404)

- Симптом: линия отвечает, но секретарь «не знает кто она» и без инструментария.
- RCA: `telephony_script_ready=false` (скрипт не сохранён в tenant.settings); live Ava бьёт в `POST /v1/telephony/calls/tool` → **404** (voice_tools вырезан при деплое).
- Сделано: `voice_tools.py` + `/calls/tool`; inbound отдаёт `secretary`; Check/Create calendar tools; на проде сохранить скрипт QL из propose.
- Канон N клиентов: каждый tenant — свой script/tools в settings; tool gateway резолвит call_id → tenant.

## 2026-11-15 ~03:30 МСК — Cursor: dual SIP = shred voice; multi-tenant invariant

- Владелец: всё должно работать на **многих** клиентах; с одним уже ломалось.
- RCA: `mango-registration` + `delno-quantum-labs-reg` на один Mango → два Stasis на звонок → Low audio energy, drift −80%, `no_input_timeout`. Сервер (CPU/RAM) был здоров.
- Сделано: legacy `mango-registration` `enabled=no` на C4B; `apply_mango_sip_server.disable_legacy_shared_registration()` на каждый apply + старт сервиса; правило в `AGENTS.md`.
- Канон: N клиентов = N `delno-<slug>-reg`, **никогда** shared Registered рядом.

## 2026-11-15 ~03:20 МСК — Cursor: восстановлен voice_agent_slug (Busy «линия не настроена»)

- Симптом: SIP Registered + DID active, но входящий Busy. AGI `/usr/local/bin/delno_route_call.py` требует `voice_agent_slug` в ответе bridge; git/prod `inbound/start` его не отдавал → `DELNO_ROUTE_OK=0`.
- Не Гермес: путь Asterisk AGI → bridge → `/v1/telephony/inbound/start` → Stasis.
- Файлы: `delno-api/app/services/telephony.py`, `api/v1/telephony.py`, `phone_provision.py`, `deploy/asterisk_delno_bridge.sh`, `deploy/delno_route_call.py`, тесты.
- Восстановлено из Codex backup (trunk_id + voice_agent_slug); QL `default` + `trunk_aliases: [mango-trunk]`; новые tenant → `delno_<uuid>`.
- Статус: см. проверку после деплоя на C4B.

## 2026-11-12 23:04 МСК — Codex: входящая маршрутизация DID → tenant → голосовой агент

- Цель: убрать фиксированный номер и общий голосовой профиль из пути входящего звонка; не направлять звонок чужому клиенту.
- Файлы: `/opt/delno/api/app/services/telephony.py`, `/opt/delno/api/app/api/v1/telephony.py`, `/opt/delno/api/app/services/phone_provision.py`, `/opt/delno/api/app/operator/tools/calls.py`, `/opt/delno/api/app/services/hermes_ops.py`, `/opt/delno/api/deploy/asterisk_delno_bridge.sh`, `/opt/delno/api/deploy/delno_route_call.py`, `/etc/asterisk/extensions.conf`, `/root/ava/config/asterisk/extensions.quantum-labs.conf`. Копия AGI установлена в `/usr/local/bin/delno_route_call.py`.
- Изменение: API выбирает tenant по фактическому DID и возвращает `voice_agent_slug`. При неизвестном DID, неоднозначности или отсутствии голосового профиля звонок не передаётся в Stasis. Для старых транков без DNID разрешён fallback только если во всей системе ровно один активный DID. AGI передаёт выбранный профиль через `AI_AGENT`, а также `DELNO_TENANT_ID`; dialplan вызывает AGI до голосового движка. Для текущего DID задан существующий профиль `default`. Hermes может указать `voice_agent_slug` при привязке нового номера. Чеклист телефонии требует маршрут голоса и готовность транка.
- Проверка: тест в транзакции с двумя tenant подтвердил разные DID/голосовые профили и `ambiguous_did` при неизвестном номере; транзакция откатена. AGI проверен с имитацией ответа API; скрипты прошли синтаксическую проверку, Asterisk успешно перезагрузил dialplan, API собран и запущен без ошибок старта. Права запуска AGI для пользователя `asterisk` проверены.
- Ограничение: реальный входящий звонок после изменения ещё не выполнен. Для нового клиента требуется подготовить отдельный голосовой профиль и транк/DID, который передаёт набранный номер. Если провайдер не передаст DID при нескольких клиентах, вызов завершится без подключения к секретарю. Автоматическое создание голосовых профилей в Hermes остаётся отдельной задачей.

## 2026-11-12 23:06 МСК — Codex: закрытие маршрутизированной сессии

- Файлы: `/etc/asterisk/extensions.conf`, `/root/ava/config/asterisk/extensions.quantum-labs.conf`.
- Изменение: `h` extension вызывает мост `calls/end` после завершения входящего звонка по сохранённому session ID, чтобы сессии не оставались активными. Записи нет, если маршрутизация не создала сессию.
- Проверка: `dialplan reload` успешен. Реальный входящий и завершение после изменения ещё требуют звонка на линию.

## 2026-11-12 23:06 МСК — Codex: изоляция голосового профиля

- Файлы: `/opt/delno/api/app/services/telephony.py`, `/opt/delno/api/app/services/phone_provision.py`.
- Изменение: для новых клиентов голосовой агент должен иметь имя `delno_<tenant_uuid_hex>`; чужой или общий профиль отклоняется. Старый `default` разрешён только tenant, указанному как владелец существующей линии в конфигурации сервера.
- Проверка: тест с двумя tenant подтвердил отказ `voice_agent_not_owned` при попытке выбрать чужой `default` и успешную маршрутизацию на собственный профиль. Все записи теста откатены. API пересобран и запущен.
- Ограничение: профиль для нового клиента пока нужно создать в голосовом движке; автоматическое создание из кабинета Гермеса ещё не реализовано.

## 2026-11-12 23:07 МСК — Codex: исходящее задание привязано к номеру клиента

- Файл: `/opt/delno/api/app/services/telephony.py`.
- Изменение: создание исходящего задания теперь требует активный DID этой компании с готовым маршрутом и принадлежащим ей голосовым профилем. Чужой DID и неподготовленная линия возвращают явную ошибку вместо постановки невыполнимого звонка в очередь.
- Проверка: тестовые задания в откатываемой транзакции подтвердили успешный маршрут текущей компании и отказ другому tenant при попытке взять её DID. API пересобран и запущен.
- Ограничение: отдельный исполнитель исходящих заданий ещё не подтверждён работающим; этот шаг защищает постановку в очередь, а не доказывает совершение звонка.

## 2026-11-12 23:10 МСК — Codex: исправлен сброс входящего звонка

- Причина: Asterisk искал `delno_route_call.py` в стандартном каталоге AGI; скрипт был установлен в `/usr/local/bin`, поэтому проверка маршрута завершалась ошибкой и вызов сбрасывался.
- Файлы: `/etc/asterisk/extensions.conf`, `/root/ava/config/asterisk/extensions.quantum-labs.conf`.
- Исправление: в обеих версиях плана указан абсолютный путь `/usr/local/bin/delno_route_call.py`; Asterisk перезагрузил dialplan.
- Проверка: API `/health` вернул 200; тестовый входящий звонок в 23:09 МСК создал и завершил сессию в DELNO, голосовой движок выбрал профиль `default` и отправил приветствие. Владелец подтвердил, что услышал приветствие.
- Статус: действующая входящая линия восстановлена. Длительный диалог и инструменты звонка этим тестом не проверялись.

## 2026-11-12 23:19 МСК — Codex: изоляция нескольких SIP-аккаунтов Mango

- Причина: Mango не передал публичный DID в DNID/To на действующей линии; старое резервное правило по единственному номеру и распознавание endpoint по IP провайдера не давали гарантии при втором аккаунте Mango.
- Файлы: `/opt/delno/api/app/services/telephony.py`, `/opt/delno/api/app/api/v1/telephony.py`, `/opt/delno/api/app/services/phone_provision.py`, `/opt/delno/api/app/operator/tools/calls.py`, `/opt/delno/api/deploy/asterisk_delno_bridge.sh`, `/opt/delno/api/deploy/delno_route_call.py`, `/etc/asterisk/pjsip.conf`, `/root/ava/config/asterisk/pjsip.quantum-labs.conf`. Копия AGI в `/usr/local/bin/delno_route_call.py`.
- Изменение: Asterisk связывает входящий Mango-вызов с конкретной регистрацией через `line=yes` и `endpoint=mango-trunk`; одинаковые IP-идентификаторы Mango удалены. AGI передаёт endpoint как `trunk_id` в DELNO. API выбирает только DID, привязанные к этому транку, и отклоняет транк без привязки или разделяемый между tenant. Регистрация чужого номера на уже занятом транке блокируется. Резервное правило «единственный номер во всей системе» удалено; при отсутствии DID допустим только один активный номер в идентифицированном транке.
- Проверка: официальный механизм `line`/`endpoint` сверён с документацией Asterisk; тест API с двумя tenant и разными транками подтвердил изоляцию и отказ при попытке разделить транк. После `pjsip reload` регистрация Mango стала `Registered`; новый реальный входящий звонок создал/завершил сессию DELNO, а владелец услышал приветствие. IP identify Mango отсутствует в работающей конфигурации.
- Статус: действующая линия работает. Для каждого нового Mango-аккаунта нужен отдельный SIP registration с `line=yes`, собственный endpoint и привязанный к нему номер tenant. Если провайдер не вернёт `line` для нового аккаунта, входящий вызов будет отклонён, а не направлен в чужой tenant.

### Cursor — archive MCP inventory + restore
- Extracted office-mcp catalog (90 tools) → `docs/QUANTUM_OFFICE_MCP_CATALOG.md` from commit `9f715c4`.
- AVA `/root/ava/src/mcp` is framework only (weather/aviation sample servers), not Quantum Office MCP.
- Restored package under `office-mcp/` + vendored `delno-api/third_party/quantum_office_mcp`.
- Hermes: `qo_mcp_bridge` registers ~83 tools into registry/CABINET (skips calls.*/line.* aliases).
- Deploy needs: `CONSOLE_TOKEN`, `WEBHOOK_TOKEN`/`OFFICE_WEBHOOK_TOKEN`, `OUTREACH_UI_TOKEN` in `/opt/delno/.env`;
  api on `quantum-office_default`; NO_PROXY must list qo-* (HTTP_PROXY otherwise 503s).

## 2026-11-13 00:33 МСК — Cursor: STOP — не ломать multi-tenant AVA / маршрутизацию Codex

- Автор: Cursor (после замечания владельца).
- Контекст: владелец + Codex специально настроили DID/trunk → tenant → голосовой профиль, чтобы **разные компании** могли пользоваться AVA. Cursor ранее перезаписал `/opt/delno/api` и снёс эту маршрутизацию; Codex восстановил (запись ~00:26–00:35 МСК).
- Жёсткие правила для Cursor и Codex (навсегда):
  1. **Не деплоить** ветки Cursor поверх `/opt/delno/api`, если diff затирает `telephony.py`, `api/v1/telephony.py`, `phone_provision.py`, `asterisk_delno_bridge.sh`, `delno_route_call.py`, dialplan/pjsip, `hermes_progress.py`, или снова включает общий `register_qo_mcp_tools` без tenant-aware адаптеров.
  2. Перед любой выкаткой API: `diff` прод↔git по этим файлам; при конфликте — **merge/подтянуть Codex**, не overwrite.
  3. Старый Quantum Office MCP (`third_party/quantum_office_mcp` / `qo_mcp_bridge`) с общими токенами и фиксированным quantum-labs — **не активировать** для мульти-клиента, пока нет изоляции по `TenantContext`. Код можно держать в архиве; регистрация в `__init__.py` на проде отключена Codex — так и оставить.
  4. Каждая задача Cursor обязана пройти фильтр: «это не вредит мультиарендной задумке?» Иначе — только verify/docs, без правок runtime.
  5. Hermes UI progress (`hermes_progress` + `HermesStage`) уже делает Codex — **не дублировать** и не переписывать вслепую.
- Проверка Cursor сейчас (только read-only на Cloud4Box):
  - `telephony.resolve`/`inbound` учитывает `trunk_id`; ошибки `ambiguous_did` / shared trunk на месте.
  - AGI `/usr/local/bin/delno_route_call.py` → `AI_AGENT` + `DELNO_TENANT_ID` + `trunk_id`.
  - dialplan: `AGI(/usr/local/bin/delno_route_call.py)` до Stasis; pjsip `line=yes` + `endpoint=mango-trunk`; registration **Registered**.
  - MCP register в prod `__init__.py` закомментирован/отключён (есть комментарий про shared credentials).
  - `hermes_progress.py` на проде есть; чат показывает «Ход работы».
  - Архив ломбардов лежит **только** в tenant `3b9326a4-…` exports; `OUTREACH_ENABLED=false`.
- Локальная ветка Cursor `cursor/hermes-trace-tenant-archive-9b51` **опасна для деплоя as-is**: в git нет `trunk_id` telephony и нет `hermes_progress`, зато MCP снова регистрируется. **Не выкатывать** на `/opt/delno` без выравнивания с продом/Codex.
- Статус: зафиксировано. Cursor дальше — verify/docs/tenant-safe archive; runtime телефонии и Hermes progress — зона Codex, пока владелец не скажет иначе.

## 2026-11-13 00:42 МСК — Cursor: глубокий анализ «почему Hermes тупой» (без runtime overwrite)

- Автор: Cursor по запросу владельца (комплексный разбор, не быстрый фикс).
- Файл: `docs/HERMES_AGENT_ARCHITECTURE_ANALYSIS.md` (+ эта запись).
- Вывод: корневая причина не «короткий промпт», а архитектура secretary-loop: cabinet allowlist **34** tools; `crm.*` зарегистрированы, но **не в CABINET**; QO MCP на проде отключён Codex (правильно для multi-tenant); web.search ≤10 / fetch ≤12k; **нет субагентов/jobs/artifacts**. Progress UI (`hermes_progress`) уже от Codex. Целевой путь: supervisor + tenant-safe workers (research/mail/phone/social) + batch research jobs; MCP только после TenantContext/vault.
- Проверка: read-only Cloud4Box (cabinet list, MCP off, web caps, model `gpt-5.4-mini`, progress poll). **API/telephony не менялись.**
- Следующий шаг (только после согласования с Codex/владельцем): Фаза A из анализа — cabinet+crm readonly, research CSV artifact; не деплоить опасные MCP-ветки поверх `/opt/delno`.

## 2026-11-13 00:47 МСК — Cursor: КОРРЕКЦИЯ — база = Nous Hermes Agent, не DIY loop

- Автор: Cursor (после жёсткого замечания владельца + уточнения Codex).
- Ошибка: Cursor называл «Гермесом» самописный `_try_cabinet_llm_tools` / `HermesStage` и проектировал субагентов/jobs с нуля. Настоящий продукт — **Nous Research Hermes Agent** (delegate_task, cron, memory, skills, MCP, profiles). На Cloud4Box **не установлен** (проверено read-only).
- Файлы: `docs/HERMES_NOUS_INTEGRATION.md` (source of truth направления); баннер deprecation на `docs/HERMES_AGENT_ARCHITECTURE_ANALYSIS.md`.
- Порядок дальше: изучить/посадить Nous Hermes per-tenant profile (`HERMES_HOME` под tenant), bridge из кабинета; **не** выдавать самописные subagents за решение; telephony Codex не трогать; один общий Hermes на всех клиентов — запрещён.
- Статус: зафиксировано. Установка на staging — только после явного ОК владельца.

## 2026-11-13 00:56 МСК — Cursor: рецензия плана интеграции оригинального Hermes (multi-tenant)

- Автор: Cursor. Полный `HERMES_ORIGINAL_INTEGRATION_PLAN.md` Codex на сервере не найден (только запись в реестре: Nous=engine, DELNO=control plane, runtime per tenant из‑за process-global MCP discovery).
- Файлы: `docs/HERMES_ORIGINAL_INTEGRATION_REVIEW.md` (глубокая оценка + схема home/MCP/self-setup); `docs/HERMES_ORIGINAL_INTEGRATION_PLAN.md` (реконструкция тезисов Codex + расширения до появления канона Codex).
- Вердикт: решение Codex **верно**; подтверждено upstream docs (multiplex MCP discovery process-global, `#67605`). Усилить: provision path, approvals bridge, billing, Frontline vs Owner, pin version, dogfood QL.
- `HERMES_AGENT_ARCHITECTURE.md` = control plane, не замена Nous. Prod/telephony не трогались.

## 2026-11-13 01:00 МСК — Cursor: сверка полного плана Codex `HERMES_ORIGINAL_INTEGRATION_PLAN.md`

- На сервере появился канон Codex (~00:58 МСК, 117 строк). Скопирован в git `docs/HERMES_ORIGINAL_INTEGRATION_PLAN.md`.
- Рецензия обновлена: `docs/HERMES_ORIGINAL_INTEGRATION_REVIEW.md` — вердикт **план верен**; tenant/user/agent/task/subagent модель, scoped run token, separate runtime first, voice last — принять как SoT.
- Усиления без смены оси: pin image, policy self-setup (что агент может/не может), Frontline≠Hermes, billing meters, feature-flag cabinet.
- Prod/telephony не трогались.

## 2026-11-13 01:17 МСК — Cursor: СТАРТ реализации Nous Hermes по плану Codex (Stage 0)

- Ветка: `cursor/hermes-nous-runtime-9b51` (от `cursor/control-panel-9b51`).
- DIY-архив: `docs/archive/diy-hermes/`. Канон: `HERMES_ORIGINAL_INTEGRATION_PLAN.md`.
- Код: `delno-api/hermes_runtime/` (pin v0.23.1 + 2-tenant compose), `app/services/hermes_nous/*`, API `/v1/hermes-nous/*`, MCP scoped run tokens, flag `hermes_nous_runtime` (off).
- Кабинет: soft-route на Nous при флаге; иначе прежний DIY loop.
- Telephony / prod Asterisk не трогались. Живой image на C4B не деплоился.

## 2026-11-13 01:21 МСК — Cursor: north star = онбординг+KB+дирижирование (не только plumbing Codex)

- Контекст: владелец уточнил — Codex-план про runtime/изоляцию полезен, но **изначальная задача** другая: Гермес сам проводит любого клиента по настройке всех нужных тулзов, сам собирает/обогащает базу знаний (сайт, каталог, текст) и потом ими дирижирует. Это преимущество DELNO.
- На `/opt/delno/docs/HERMES_ORIGINAL_INTEGRATION_PLAN.md` нового текста Codex (после 00:58) не обнаружено — тот же 22KB план; продуктовый цикл там почти не раскрыт.
- Файлы: `docs/hermes-nous/PRODUCT_LOOP.md` (канон продукта); обновлены review + STAGE0 приоритеты.
- Реализация дальше: после pin/isolation — onboarding skill → KB → один коннектор → поручения; cron/voice не первыми. Telephony не трогать.

## 2026-11-13 01:25 МСК — Cursor: единый MASTER_PLAN (продукт + изоляция + UI + P0–P5)

- Владелец подтвердил: multi-tenant изоляция сред/тулзов/KB + умный Nous (субагенты, сам выбирает как решать) + современный UI онбординга/прогресса. То же преимущество, что задумывали изначально, на нормальном Гермесе.
- Файл: `docs/hermes-nous/MASTER_PLAN.md` — канон порядка работ. P0 plumbing → P1 онбординг+KB+UI → P2 коннекторы+delegate → P3 cron/tasks → P4 каналы/голос last → P5 scale.
- Codex platform plan остаётся для runtime/tokens; PRODUCT_LOOP — зачем; MASTER — как идём.

## 2026-11-13 01:31 МСК — Cursor: реализация MASTER P0–P5 (код + UI + миграции)

- P0: isolation_smoke.sh; pin/runtime уже были.
- P1: office-loop API, kb-draft/confirm, SOUL+onboarding skill, UI «Путь офиса».
- P2: tool packs onboarding/conduct/tasks; cabinet soft-route → conduct pack.
- P3: alembic 007 agent_tasks/runs/steps + API + UI поручения; bridge пишет AgentRun.
- P4/P5: channels-map, scale-notes, docs P4/P5; meter event hermes_nous.run_started.
- Live docker image / telephony / lead.created worker — staging later; prod phone не трогали.
- Тесты: test_hermes_nous_* + mcp_gateway — 11 passed.

## 2026-11-13 ~20:15 МСК — Cursor: Stage 1 multi-tenant placement (Codex assignment)

- Ветка: `cursor/hermes-multitenant-runtime-9b51` (от `cursor/hermes-live-dictate-thinking-9b51`).
- Цель: карта `tenant → profile → worker` без silent fallback на worker A; закрыть клиентский `runtime_base_url` / escalate `tool_ids`; честный `hermes_unavailable` вместо DIY-как-Гермес; MCP run-binding proxy (`X-Delno-Run-Id`).
- Файлы: `delno-api/app/models/hermes_runtime.py`, `services/hermes_nous/placement.py`, `run_bindings.py`, rewrite `runtime_pool.py`/`bridge.resolve_runtime`, `api/v1/hermes_nous.py`, `api/v1/mcp.py`, `api/v1/operator.py`, `provision.py`, `onboarding.py`, `scripts/migrate_prod.py`, tests `test_placement.py` / `test_runtime_pool.py` / `test_run_bindings_mcp.py`, `docs/HERMES_ORIGINAL_INTEGRATION_PLAN.md` status, CHANGELOG.
- Правила: capacity=1 на dogfood worker до доказанного multiplex на pin v0.23.1; pool exhausted → `provisioning`, не `slots[0]`; MCP internal URL; `api.dlno.ru` = SNI (не полагаться как на «отдельный API host» в DNS).
- Telephony/Asterisk не трогались. Живой C4B deploy ещё не в этом коммите — сначала git/PR.
- Следующий шаг: выкат migrate + явная assign demo→A / QL→B через admin; worker-visible HERMES_HOME volume; выключить legacy MCP key для Hermes (`DELNO_MCP_DENY_LEGACY_KEY` / meta-only); tasks reconciler.

## 2026-11-13 ~20:25 МСК — Cursor: live profile homes + reconciler

- Ветка: `cursor/hermes-multitenant-runtime-9b51` (PR #88).
- `HERMES_PROFILES_ROOT` / `profile_homes.py`: state_location = worker-visible path; shared volume `hermes-profiles` in stack + hermes compose; entrypoint `HERMES_PROFILE_ID`; **убран** fallback `DELNO_MCP_KEY_B←DELNO_MCP_KEY`.
- `reconcile_stale_runs` + `/v1/hermes-nous/admin/reconcile-runs` + background ticker; `scripts/bootstrap_hermes_placement.py`.
- Тесты: test_profile_homes, test_reconcile_runs + placement suite.
- Следующий: C4B migrate/bootstrap; DELNO_MCP_DENY_LEGACY_KEY на Hermes workers; e2e A/B isolation with real containers; DIY ticker → Hermes for scheduled tasks.

## 2026-11-13 ~20:30 МСК — Cursor: schedule→Nous + MCP strict + isolation smoke

- Schedule: при флаге Nous — `create_run`; при unavailable — fail без DIY.
- MCP: `X-Delno-Profile-Id` vs mcp key tenant check; `DELNO_MCP_STRICT` → legacy meta-only.
- `scripts/isolation_placement_smoke.py`; hermes compose mem/pids limits.
- Цель ещё не закрыта без C4B e2e на живых контейнерах.

## 2026-11-13 20:30 МСК — Cursor: C4B deploy multi-tenant placement (PR #88)

- Выкатан код на `/opt/delno/api` (backup `hermes-mt-*`); volume `hermes-profiles`; recreate `delno-api`.
- Bootstrap: `delno-demo→tenant-a`, `quantum-labs→tenant-b`; **tenant-beta = provisioning** (resolve blocked, no fallback to A).
- Live smoke: QL with FACTS → «кабинет пустой, 0/6, начать с знаний»; demo create_run ok на A.
- Telephony не трогали. Полный e2e двух новых регистраций / multiplex — ещё впереди.

## 2026-11-13 20:35 МСК — Cursor: shared profile homes live on A/B + isolation proof

- Workers recreated: `HERMES_HOME=/data/hermes-profiles/<profile_id>` (shared volume with API); state migrated from old volumes.
- Proof: demo progress 6/6 vs QL 0/6; MCP keys 1:1; beta `resolve` + `/v1/operator/chat` → `hermes_unavailable` (not DIY).
- Goal criteria (map, no fallback, provision/MCP lock, honest unavailable, worker-visible profiles) verified on C4B. Multiplex >1 profile/worker still unproven (capacity=1).

## 2026-11-15 23:03 МСК — Codex: MCP run-binding auth на C4B

- Файл: `/opt/delno/api/app/api/v1/mcp.py` из merged PR #102. Заголовок `X-Delno-Run-Id` без учётных данных того же тенанта больше не открывает инструменты.
- Резервная копия: `/opt/delno/backups/mcp-auth-20261115/mcp.py`.
- Проверено: SHA256 установленного файла `73c3ba42b547de12dba3731e44fb6e2ce94fce47cfb1120f33ce7e49a7981633`, API `/health` = 200 после перезапуска, `app.dlno.ru` = 200, журнал запуска без ошибок. Тесты PR #102 и CI были зелёными.
- Осталось: сквозная проверка онбординга и отдельный пакет PR #101 с per-tenant календарём/файлами.

## 2026-11-15 23:08 МСК — Codex: проверка подключения почты в DELNO gateway

- Файлы: `delno-office/mail/office_gateway.py`, `delno-office/mail/tests/test_probe.py`, `delno-api/app/services/connector_connect.py`, `delno-api/app/operator/tools/office.py`, `delno-api/app/adapters/connectors/mail.py`, тесты API.
- PR #101 вызывал `/api/mail/probe`, но текущий `delno-mail` его не предоставлял: реализация была добавлена в другой сервис `mailer/main.py`. В рабочий gateway добавлена проверка SMTP-входа по данным одного тенанта без отправки письма и без вывода пароля.
- Отправка теперь берёт только проверенную почту текущей компании; шлюз отклоняет запрос без данных компании и не использует общий SMTP. Тесты: 4 gateway-теста прошли; API 419 passed, 1 unrelated network-dependent `test_suggest_reachable_host_fixes_quantum_typo` failed. На прод пока не выложено.
- Осталось: проверить живую отправку после выкладки с учётной записью тестовой компании; до этого не считать почту готовым модулем онбординга.

## 2026-11-15 23:40 МСК — Codex: онбординг и изоляция офисных сервисов на C4B

- PR #101 и #104 merged. На `/opt/delno` обновлены API, кабинет, calendar, files, conference и mail; исходники до выкладки: `/opt/delno/backups/onboard-20261115/sources.tar.gz`, прежние образы: `delno-<service>:before-onboard-20261115`.
- Dockerfile calendar/files дополнены `tenant_scope.py` после проверки собранных образов: прежние образы модуль не импортировали. Исправленные образы импортируют `main` и `tenant_scope`.
- Проверено на сервере: `/health` API и всех четырёх office brokers, `app.dlno.ru` и `dlno.ru/blog` = 200; два существующих audit-тенанта видят свои `/auth/me`, каталоги подключений, status/placement = 200; calendar/files отклоняют несовпадающий tenant заголовка и тела = 403; mail отклоняет отправку без учётных данных компании = 403. Журналы контейнеров без traceback.
- Блокер полного живого диалога: Hermes pool получает от OpenAI `HTTP 403 unsupported_country_region_territory` для `gpt-6-luna` с egress IP сервера `161.104.89.123`. В контейнере настроен только `OPENAI_API_KEY`; альтернативного провайдера нет. Поэтому настоящий ответ Hermes и завершение онбординга пока не подтверждены. Нужен поддерживаемый провайдер/доступный сетевой маршрут; не считать онбординг завершённым.
- Живая отправка письма из подключённого тестового ящика не проверена: проверочных SMTP-данных тенанта нет. Телефония, Asterisk, Mango, VPN и 3x-ui не менялись.

## 2026-11-15 23:48 МСК — Codex: честное сообщение о недоступности модели

- PR #106 deployed на `/opt/delno/api`: при `unsupported_country_region_territory` Hermes run помечается failed, клиент получает короткое русское сообщение `hermes_unavailable` вместо сырого текста API. Backup файлов: `/opt/delno/backups/hermes-provider-error-20261115/`, образ `delno-api:before-provider-error-20261115`.
- Проверено: API `/health` = 200; живой запрос существующего audit-тенанта вернул `engine=hermes_unavailable` без текста про API-ключ. Блокировка модели самим провайдером остаётся.
- Дополнительно обнаружено: общий pool имеет пустой `DELNO_MCP_KEY`, а конфигурации профилей содержат `${DELNO_MCP_KEY}`. Перед объявлением онбординга готовым надо доказать передачу per-run token в MCP и реальный вызов инструмента для двух тенантов; не включать legacy static key как обход.

## 2026-11-16 00:04 МСК — Codex: восстановлен прежний OpenAI egress для Hermes

- Причина `unsupported_country_region_territory`: в текущем `/opt/3x-ui/xray-bin/up-vpn1-rules.json` отсутствовало прежнее правило `inbound-grok-minsk → up-vpn1`; настроенный DELNO прокси `172.18.0.1:10808` поэтому выходил напрямую с C4B. Правило найдено в `config.json.bak.20261114T152505` и `up-vpn1-rules.json.bak.20261114T152505`.
- Восстановлено **только** это правило в persistent rules. До правки сохранены `/root/backups/delno-egress-20261115/config.json`, `up-vpn1-rules.json`, `x-ui.db`. Кандидат после `inject-uplink.sh` отличался от активной конфигурации ровно одним правилом и прошёл `xray -test` внутри контейнера. После перезапуска 3x-ui правило присутствует; `10808` выходит с внешнего IP, OpenAI `/v1/models` из Hermes = 200. Остальные маршруты не менялись; порты 8443/8444/10808 слушают, DELNO API `/health` = 200.
- Живые запросы двух audit-тенантов к Hermes вернули `nous_hermes_agent` и правильный статус 0/6. SSE обоих запусков подтвердил `mcp__delno_office__hermes_setup_status` → `tool.completed`, `error=false`.
- Уточнение к записи 23:48: пустой `DELNO_MCP_KEY` **общего процесса** не означает отсутствия MCP. У каждого профиля есть отдельный `.env` с `DELNO_MCP_KEY`; проверено без раскрытия значений, что ключи audit A, audit B, QL и demo принадлежат только соответствующим тенантам. Per-run token в MCP всё ещё не доказан и остаётся отдельной задачей по ужесточению прав, но текущая проверка не выявила смешения этих профилей.


## 2026-11-16 — Codex: онбординг от задачи, без обязательных инструментов

- Ветка `codex/goal-led-onboarding`: `delno-api/app/services/hermes_ops.py`, `instrument_catalog.py`, `hermes_nous/{onboarding,bridge,tool_packs}.py`, `operator/{agent,tools}.py`, API `/operator`, шаблоны SOUL/skill и `delno-web/components/HermesStage.tsx`.
- Добавлены `hermes.goal_set` и `hermes.catalog_ack`, выбранные инструменты и уведомление о новых возможностях; телефон больше не обязателен и не вызывает health warning, когда не выбран. Доступ к рабочим инструментам не зависит от статуса онбординга.
- Rollout-скрипт расширен на multiplex worker profiles; изменённые владельцем файлы сохраняются и получают `.update-candidate`. Тесты и сборка: см. PR.
- Прод и существующие профили на момент записи не менялись. При выкладке проверить подмену шаблонов в `/opt/delno/lab/hermes_runtime/templates/home` и отдельно согласовать применённые кандидаты профилей. Секреты и телефония не затронуты.

## 2026-11-16 20:37 МСК — Codex: выложен онбординг от задачи

- PR #109 принят; API и кабинет пересобраны на C4B. Обновлены шаблоны в `/opt/delno/lab/hermes_runtime/templates/home` и 9 файлов SOUL/skill действующих профилей. Предыдущие файлы сохранены в `/opt/delno/backups/goal-led-20261116/`, включая настройки Quantum Labs.
- API `/health`, локальный кабинет и `https://app.dlno.ru/` отвечают 200. На audit-тенанте задача «Отвечать на сообщения клиентов» с выбранными Telegram и MAX дала только эти два следующих шага; телефон отмечен необязательным. Исходные настройки audit-тенанта восстановлены после проверки.
- CI и полный серверный набор тестов прошли (424 теста); сборка кабинета прошла. Живой диалог с моделью после выкладки отдельно не проверен.

## 2026-11-17 — Codex: внутренний календарь и инвентаризация офисных инструментов

- Ветка `codex/tenant-calendar-origin`: отдельные tenant-scoped встречи, экран и API календаря, общие действия для голоса и мессенджеров. Голосовой номер берётся из `CallSession`, ID отправителя Telegram/MAX — из webhook; чужая запись и неоднозначный номер не выбираются автоматически.
- Сверены старые `ava-calendar`, `ava-conference`, `ava-files`, `ava-mailer` и `quantum-console` с текущими DELNO; результат в `docs/DELNO_OFFICE_TOOL_INVENTORY_2026-11-17.md`. Бэкап содержал PDF-письмо, но не содержал перенос/отмену CalDAV-событий.
- Ветка ещё не выложена на прод. Внешняя двусторонняя синхронизация, привязка контактов между каналами и реальное вложение презентации — отдельные недоделанные части, их нельзя заявлять готовыми.

## 2026-11-17 — Codex: Gate 1, реальный путь Session Authority

- В Hermes v0.23.2 реальный `/v1/runs` исполняется через `Session Authority`; прежняя привязка scoped-токена только в `_run_agent_sync` не охватывала этот путь. Это было причиной `delno_run_scope_missing` при первом rollout.
- Патч регистрирует токен по upstream admission/request ID в памяти процесса, привязывает его к ContextVar только на время допущенного хода с совпадающим профилем и удаляет после завершения запуска. Токен не пишется в session SQLite и не становится общим для воркера. Регрессионный smoke проверяет параллельные ходы двух профилей, чужой профиль и удаление привязки.
- Production: API `delno-api:gate1-5053e3ef`; Hermes Pool `delno-hermes-runtime:gate1-hotfix-20261117`. Перед переключением сделан `/opt/delno/backups/gate1-fix-20261117/`; прежние образы сохранены. Флаги включены последовательно: `DELNO_MCP_RUN_SCOPE_ENABLED=1`, `DELNO_MCP_REQUIRE_RUN_BINDING=1`, `DELNO_MCP_LEGACY_CATALOG_ONLY=1`, `DELNO_MCP_DENY_LEGACY_KEY=1`. Живой Owner и фоновая задача проходят; Telegram/MAX health OK; legacy business call получает 403. Параллельные реальные диалоги двух audit-компаний вызвали `get_tenant_summary` с `auth_via=run_token` и своими `run_id`.
- Итог Gate 1: после ограничений 13 production бизнес-вызовов MCP, все `auth_via=run_token` с `run_id`, две audit-компании; legacy бизнес-вызов получает 403. Фоновая задача сопоставлена по `HermesRunBinding.session_id` со своим scoped событием. На API прошли 14 тестов изоляции; на каналах — 15 тестов; регрессия установленного Hermes прошла; CI PR #121 зелёный. Gate 1 закрыт по проверенному контуру. Один из первых параллельных прогонов вернул пустой текст для одного диалога, повторный прогон обеих компаний прошёл; это отдельный риск качества ответа, не обход авторизации. Ротация шести постоянных ключей не производилась по указанию Дениса; они больше не дают бизнес-доступ через MCP.

## 2026-11-17 — Codex: Gate 2, память диалогов владельца

- Ветка `codex/delno-gate2-memory`: tenant/user-scoped таблица `hermes_owner_turns`, миграция 010, короткий recall прежних разговоров в Owner Hermes, API просмотра и удаления, флаг `DELNO_OWNER_MEMORY_ENABLED` выключен по умолчанию.
- Изолированные тесты и миграция на восстановленной копии базы описаны в `docs/DELNO_GATE2_OWNER_MEMORY_2026-11-17.md`. На production Gate 2 не выкладывался.

## 2026-11-18 — Codex: Gate 2, завершение реализации перед E2E

- Найден основной путь кабинета `/v1/operator/chat`; он не использовал первую версию памяти из PR #122. Добавлено извлечение фактов и восстановление контекста на этом пути и в прямом `/v1/hermes-nous/runs`.
- Память переведена на короткие факты и решения по `(tenant_id, user_id)`, с исправлением, удалением, запретом темы, очисткой, ревизией сессии и минимальным UI. Извлечение использует только слова владельца; ответы инструментов не сохраняются.
- История диалогов Hermes ограничена владельцем внутри компании. Общие каналы не менялись. Старые диалоги получают владельца миграцией только для компаний с одним пользователем.
- Локально прошли 24 целевых теста; общий прогон 453/454, единственный отказ — старый сетевой тест доступности внешнего сайта. Production Gate 2 ещё не изменён; изолированный E2E A–H, свежий backup и выкладка ещё обязательны.

## 2026-11-18 — Codex: Gate 2, production audit

- Production API `delno-api:gate2-f86e9d2`, веб `delno-web:gate2-b4956cb`; пул Hermes остался на образе Gate 1. Схема БД 010. Память включена только для audit A, рабочие профили пока выключены.
- Backup `/opt/delno/backups/gate2-20261118/` прошёл контрольные суммы, восстановление в отдельный PostgreSQL и повторное применение миграции 009→010. Профильные `MEMORY.md` и `USER.md` отключены на всех девяти профилях Hermes.
- Реальные Owner E2E A–H прошли после ожидания запуска пула: новые диалоги, коррекция, семь промежуточных разговоров, перезапуск, две компании и второй пользователь, удаление, защита от внедрённой инструкции и приоритет MCP. Gate 1 smoke сохранил Owner, фоновые задания, Telegram/MAX, scoped business MCP и отказ legacy 403.
- Первый запрос немедленно после restart пришёл до готовности Hermes; повтор после готовности прошёл. Финальное включение рабочего профиля, проверка и merge PR #122 ещё не выполнены.
- Tenant-флаг включён для Quantum Labs; реальный диалог сохранил тестовый факт, новый диалог восстановил его, затем запись удалена. Audit A после проверки выключен, B оставался выключен. CI PR #122 на `94f5886` зелёный.
- PR #122 слит в `main` коммитом `f1f95ae` после зелёного CI на финальном `e94f70f`. Production оставлен на проверенных образах API `gate2-f86e9d2`, web `gate2-b4956cb`, Hermes Gate 1 hotfix. Quantum Labs включён; остальные tenant-флаги памяти выключены. Gate 2 закрыт для этого рабочего профиля.

## 2026-11-18 — Codex: правило выкладки DELNO

- Ветка `codex/delno-release-gate`: удалено устаревшее требование обновлять PROD сразу после изменения Git.
- Новый порядок: DEV → постоянный UAT с автоматическими и сквозными тестами → отдельное разрешение Дениса на конкретную версию PROD, предварительно проверенный откат и production smoke.
- Аудит GitHub: `delno-tests` запускает только тесты API и knowledge; workflow автоматического deploy PROD не найден. `main` пока без branch protection. Правило в `AGENTS.md` устраняет неправильную инструкцию агентам, но технический UAT gate и защита `main` ещё должны быть внедрены и проверены отдельно.
