# DELNO: общий реестр изменений агентов

Этот файл — журнал координации работы Cursor и Codex на сервере `/opt/delno` и в git (`docs/AGENT_CHANGE_REGISTER.md`). Перед правкой прочитайте последние записи и проверьте состояние указанных файлов. После правки добавьте запись. Не переписывайте чужие записи. Секреты и токены сюда не помещать.

Формат записи: дата (МСК), автор, цель, файлы, изменение, проверка, статус, следующий шаг/ограничение.

**Где лежит:** git `docs/AGENT_CHANGE_REGISTER.md` ↔ прод `/opt/delno/docs/AGENT_CHANGE_REGISTER.md` (держать в синхроне).

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

