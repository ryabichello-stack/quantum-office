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

## Открытые архитектурные задачи для Cursor и Codex

- Секреты в `tenant_vault.py` сейчас сохраняются как значения в `Tenant.settings` JSON. До массового онбординга нужны шифрование с управляемым ключом, миграция существующих данных и проверка, что секреты не попадают в ответы API и логи.
- `mail`, `calendar`, `conference`, `outreach` используют общие серверные сервисы. Их health не подтверждает права отдельного tenant. Нужны отдельные учётные записи/токены и проверка действия в контексте tenant.
- `telephony_script.py` сохраняет разрешённые инструменты в настройках tenant; необходимо доказать, что живой обработчик звонка читает и соблюдает их. Выбор голоса в `tenant_voice_profiles` пока не подтверждён на действующей линии.
- После подключения нового коннектора Гермес должен получать обновлённый каталог возможностей, продолжать сохранённую задачу после формы/подтверждения и проверять фактический результат.
- SIP: tenant-aware маршрутизация / отдельные линии (сейчас общая Asterisk + allowlist одного tenant).
