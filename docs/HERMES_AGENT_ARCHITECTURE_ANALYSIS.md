# Почему Hermes «тупой»: аудит залипухи DELNO (НЕ стратегия продукта)

Дата: 2026-11-13 (МСК). Автор: Cursor.  
Статус: **устарел как roadmap**. Оставлен как forensic-аудит самописного цикла DELNO.

**Коррекция:** продукт должен опираться на **[Nous Research Hermes Agent](https://hermes-agent.nousresearch.com/docs)** (субагенты, cron, memory, MCP уже есть). Стратегия интеграции: [`docs/HERMES_NOUS_INTEGRATION.md`](HERMES_NOUS_INTEGRATION.md). Ниже — почему *текущий* DELNO-омоним «Гермес» инвалидный; **не** план писать субагентов с нуля.

Runtime телефонии / multi-tenant AVA — зона Codex; overwrite `/opt/delno/api` не предлагается.

---

## 1. Вердикт в одном абзаце

Hermes сейчас — это **один синхронный LLM-цикл с узким allowlist ~34 tools**, слабым web-research (DuckDuckGo ≤10 ссылок, fetch ≤12k символов), **без субагентов**, без параллельного fan-out и без tenant-safe полного office-инструментария. Модель на проде (`gpt-5.4-mini`) способна планировать, но **ей физически нечем выполнять** «Grok-уровень»: собрать таблицу на 200 клиентов, глубоко пропарсить сайты/TG, вести почту/соцсети как отдельные рабочие линии. UI progress (Codex `hermes_progress`) уже показывает *ход работы*, но это не компенсирует дыры в tools и оркестрации. Поэтому ответы короткие и «инвалидные» — не потому что «забыли промпт», а потому что **архитектура всё ещё secretary-setup loop, а не research/ops agent platform**.

---

## 2. Что владелец ожидает vs что есть

| Ожидание | Факт на Cloud4Box (проверено read-only) |
|----------|----------------------------------------|
| Видно размышление / план / следующий шаг | Есть `hermes_progress` + poll `/v1/operator/progress/{turn_id}` + блок «Ход работы» в `HermesStage`. Это **операционные события**, не chain-of-thought модели (намеренно: секреты/args не светятся). |
| Полноценный агент, не фразовый бот | Есть multi-round loop (soft-stop / no-progress×3 / max_rounds=25 / token budget 100k). Это уже «агент», но **одноуровневый**. |
| Доступ ко всему инструментарию office | **Нет.** MCP QO (~90 tools) на проде **отключён** Codex (shared credentials + fixed quantum-labs). В `CABINET_LLM_TOOLS` **34 имени**; `crm.*`/`outreach.*` **зарегистрированы, но не в allowlist** → модель их не видит. |
| Глубокий research, таблицы клиентов | `web.search` default **5**, cap **10**; нет crawl pipeline, нет extract-to-sheet, нет bulk CRM ingest tool в cabinet. |
| Субагенты (почта / телефония / соцсети / research) внутри одного tenant | **Отсутствуют.** Один `HERMES_AGENT_SYSTEM` + один список tools на весь turn. |
| Умно и оптимально по токенам | Mini-модель + один толстый system+tools каждый round; нет router/skills; нет дешёвого worker / дорогого synthesizer. |
| Multi-tenant безопасность | Codex восстановил DID/`trunk_id`→tenant. Cursor **не должен** снова выкатывать общий MCP/overwrite telephony. |

---

## 3. Слои проблемы (почему кажется «ограниченной инструкцией»)

### 3.1. Промпт — не главная причина, но усугубляет

На проде system prompt уже требует для сложной задачи: цель / что проверил / факты / что сделал / что осталось. Параллельно жёстко запрещает «сейчас схожу…» и **форсирует tool** при narration. Это правильно для исполнения, но:

- модель **не может** долго «рассказывать план пользователю» в финальном тексте до tools — UI должен брать план из `hermes_progress.publish("plan"|"next"|"working")`;
- если tools слабые или connectors `usable=false`, агент быстро soft-stop’ится с коротким «не могу / вот что есть».

В git system всё ещё упоминает «Quantum Office MCP полный каталог», а на проде Codex это вырезал. Расхождение git↔prod само по себе путает агентов разработки.

### 3.2. Allowlist режет мозг сильнее промпта

`registry.list_openai_specs(names=_cabinet_llm_tools())` отдаёт модели **только** cabinet-список.

Факт прод:

- cabinet = **34** tools (setup, phones, calendar/mail draft, web×3, billing…);
- `Crm*Tool` / outreach connectors **есть в registry**, но **`crm.*` / `outreach.*` не входят в CABINET** → для LLM их как будто нет;
- `register_qo_mcp_tools(...)` на проде **не вызывается** (правильно для multi-tenant, пока нет tenant-aware адаптеров).

Итог: даже «умный» `gpt-5.4-mini` играет в шахматы без фигур.

### 3.3. Web-stack — игрушечный research

Реализация:

- поиск = HTML DuckDuckGo, `limit ∈ [1,10]`;
- fetch/browse = до ~12 000 символов текста;
- Playwright optional fallback;
- HTTP timeout LLM completion **30s** (vision 60s) — длинные цепочки хрупкие;
- нет: site maps, pagination crawl, structured extraction, SERP API, TG/public channel scrapers, spreadsheet writer, dedupe/enrich (ИНН/DaData bulk), export в files/Sheets.

Поэтому «найди клиентов» → 5 ссылок и абзац, а не таблица на 200 строк. Это **потолок инструмента**, не «лень модели».

### 3.4. Коннекторы честно «не usable»

`hermes.capabilities` / readiness разделяют `service_reachable` vs `tenant_authorized` / `usable`. Почта, календарь, ВКС, outreach для большинства tenant — поверхности без подтверждённого аккаунта. Агент правильно отказывается делать вид, что отправил 200 писем. Но UX выглядит как «тупой», если не объясняет дорожную карту подключения.

### 3.5. Нет оркестрации уровня платформы

Сейчас:

```
User → run_operator_turn → _try_cabinet_llm_tools
        → for round in 1..25:
             LLM(tools=cabinet34)
             → sequential tool runs
        → one reply + progress events
```

Нет:

- planner vs workers;
- parallel subagent fan-out;
- specialist prompts (research / mail / telephony ops / social);
- persistent task graph на tenant;
- budget router (дешёвая модель на routing, сильная на synthesis);
- artifact store (таблицы, черновики, отчёты) как first-class result.

Крупные системы (OpenAI Agents handoffs / agents-as-tools, LangGraph subagents, CrewAI manager, AWS supervisor-workers) сходятся: **один менеджер + узкие специалисты с изоляцией контекста**, а не 90 tools в одном prompt.

### 3.6. Почему «Codex определяет», а Cursor «ломает»

Не политика «Codex главный», а физика прода:

1. Codex чинит **live** `/opt/delno` (телефония multi-tenant, progress UI, отключение опасного MCP).
2. Cursor пушит в git ветки, которые при «выкатить api» **затирают** эти файлы (уже было: потеря `trunk_id` routing).
3. Владелец справедливо требует: любая задача Cursor проходит фильтр «не вредит мультиаренде».

Значит путь к «умному Гермесу» — **аддитивный дизайн tenant-safe tools + оркестратор в git**, merge с Codex, потом аккуратный deploy — не «залить свою ветку».

---

## 4. Как делают «Grok-уровень» у зрелых продуктов (сжатая карта)

Паттерны, релевантные DELNO:

1. **Supervisor + subagents-as-tools** (LangChain/LangGraph, OpenAI Agents): менеджер держит диалог; research/mail/telephony — вызываются как tools с своим system+toolset; контекст не раздувается.
2. **Handoffs** — когда специалист должен сам говорить с пользователем (онбординг SIP) vs **agents-as-tools** — когда менеджер синтезирует (research table).
3. **Skills / on-demand prompts** — не тащить весь office catalog каждый turn; подгружать пакет tools по классу задачи.
4. **Graph / task queue** — для 200 клиентов: job `research.leads.batch` с прогрессом, артефактом CSV, а не 25 chat-rounds в одном HTTP request.
5. **Least privilege per worker** — research-worker read-only web; mail-worker только mail send с confirm; telephony-worker только своего tenant DID (уже направление Codex).
6. **Model routing** — mini классифицирует и делегирует; stronger model пишет отчёт/таблицу; детерминированный код делает parse/dedupe (дешевле токенов).
7. **Human approval gates** — critical_write уже есть; для bulk outreach обязателен.

Для DELNO оптимально: **паттерн 1+3+4+5**, не «включить 90 MCP в один system prompt».

---

## 5. Целевая архитектура Hermes vNext (внутри одного tenant)

```
                    ┌──────────────────────────┐
   Owner UI         │  Hermes Supervisor       │  gpt-mini / mid
   progress SSE     │  plan · budget · policy  │
                    └───────────┬──────────────┘
           ┌────────────┬───────┼────────┬────────────┐
           ▼            ▼       ▼        ▼            ▼
      ResearchWorker  MailWorker  PhoneWorker  SocialWorker  OfficeWorker
      (web/crawl/      (draft/     (DID/calls/  (TG/MAX/      (calendar/
       extract/table)  send*)      scripts*)    channel*)     files/kb)
           │            │           │            │            │
           └────────────┴───────────┴────────────┴────────────┘
                              │
                    Tenant-scoped adapters
                    (vault creds, NO shared QO tokens)
                              │
                    Artifacts: CSV / Sheet / KB docs / confirm cards
```

\* write-пути — confirmation + tenant readiness.

### 5.1. ResearchWorker (то, за что платят)

Минимальный набор tools:

- `research.search` (SERP или усиленный DDG, limit до 50–100 *per query*, с пагинацией);
- `research.fetch` / `research.crawl` (глубина, sitemap, JS render);
- `research.extract_entities` (компании, телефоны, email, ИНН — schema JSON);
- `research.to_table` → artifact CSV + optional `files.upload` / Sheets;
- `research.enrich` (DaData/company registry) — отдельный платный шаг.

Оркестрация batch: создать `Task` на 200 строк → progress events → итоговый файл. **Не** пытаться уложить в один sync chat turn.

### 5.2. Domain workers

| Worker | Tools (tenant-scoped) | Когда создавать |
|--------|----------------------|-----------------|
| Mail | drafts, send, imap threads | задача про переписку / outreach email |
| Phone | calls.*, script_*, health линии | задача про AVA/звонки |
| Social | messenger/telegram/max publish+inbox | задача про каналы |
| Office | calendar/conference/files/kb | секретарь |
| CRM | funnel/leads/companies local + later Bitrix | лиды/воронка |

Supervisor вызывает worker **только если** `hermes.capabilities` говорит `usable` или есть явный план «сначала подключить credential form».

### 5.3. Экономика токенов (оптимально, не «дёшево любой ценой»)

- Не отдавать 90 tools в каждый round → **skills**: 8–15 tools supervisor + 1 tool `delegate(worker, goal)`.
- Worker стартует с **чистым** контекстом (goal + constraints + schema), без всей истории чата.
- Парсинг/дедуп/CSV — **код**, не LLM.
- Сильная модель — только на synthesis отчёта и спорные извлечения.
- Кэш SERP/fetch по URL+etag в tenant storage.
- Soft budgets: research job max $ / max pages; UI показывает смету до confirm.

---

## 6. Почему прошлые попытки «подключить MCP» не дали умного агента

1. **office-mcp / qo_mcp_bridge** — мощный каталог, но с **общими** broker tokens и часто implicit `quantum-labs` → убивает multi-tenant (Codex правильно снял с регистрации).
2. Даже при включении: без research-pipeline и без subagents MCP даёт «много кнопок», не «команду».
3. Allowlist cabinet не расширяли под crm/outreach stubs → часть уже безопасных local tools **молчит**.
4. Выкатка Cursor API затирала telephony Codex → владелец воспринимает Cursor как угрозу архитектуре, а не как ускоритель ума агента.

Правильный путь MCP/tools: **переписать handlers на TenantContext + vault**, регистрировать по readiness, не «QO_MCP_OVERWRITE=1 на весь мир».

---

## 7. Матрица корневых причин «коротких тупых ответов»

| Симптом у пользователя | Корневая причина | Лечится промптом? |
|------------------------|------------------|-------------------|
| Не видно шагов | Раньше не было progress; сейчас есть, но план скудный если мало tool events | Частично UI; нужен richer publish |
| Короткие ответы | mini + мало фактов из tools + soft-stop | Слабо; нужны артефакты |
| Нет серьёзного research | web≤10, нет crawl/table/batch | Нет |
| «Нет нормальных тулов» | cabinet 34; MCP off; crm не в allowlist; connectors not usable | Нет |
| Не как Grok | нет subagents/jobs/artifacts | Нет |
| Боится сложных задач | confirmation + readiness честно режут | UX + onboarding |
| Разные компании / AVA | требует tenant routing (Codex) | Не трогать вслепую |

---

## 8. Рекомендуемый план работ (без вреда multi-tenant)

### Фаза A — быстро и безопасно (не трогая telephony)

1. Расширить **CABINET** локальными безопасными tools: `crm.*` (уже tenant DB), read-only outreach status/dashboard **без send**, если stub/ready.
2. Поднять research MVP: search limit↑, multi-query loop tool, `research.export_csv` artifact + download card в UI.
3. Supervisor prompt: явно «для lead-gen всегда строй таблицу-артефакт; не останавливайся на 5 ссылках».
4. Выровнять git↔prod system prompt (убрать ложное «MCP полный каталог» или заменить на «только usable tools»).
5. Документировать в register; merge с Codex, не overwrite.

### Фаза B — оркестратор

1. `delegate_research` / `delegate_mail` / `delegate_phone` как tools supervisor.
2. Background `HermesJob` + progress (уже есть event bus) для задач >N минут.
3. Model routing + token accounting per worker.

### Фаза C — tenant-safe office power

1. Адаптеры QO MCP → каждый call с `TenantContext` + vault creds.
2. Включать packs tools только при `usable=true`.
3. Bulk outreach только после SMTP+policy+confirm (архив ломбардов QL уже изолирован).

### Явно не делать сейчас

- Деплой веток Cursor поверх `/opt/delno/api` с MCP overwrite.
- Правки `telephony.py` / AGI / pjsip без Codex.
- Обещать «200 клиентов в одном sync chat» без job+artifact.

---

## 9. Ответ на вопрос «почему до сих пор как инвалид»

Не потому что «забыли одну настройку в UI». Потому что продукт на развилке:

- **снизу** уже есть зачатки агента (loop, progress, capabilities, multi-tenant phone);
- **сверху** всё ещё cabinet-секретарь с тремя web-tools;
- **мост** к полному office (MCP) временно снят по безопасности;
- **организационно** Cursor и Codex дерутся за одни файлы, и выкатки без merge откатывают умные куски.

Grok-уровень = supervisor + tenant-safe workers + research jobs + artifacts + model routing.  
Это проектируется и внедряется поэтапно; «вкрутить промпт» или «вернуть MCP as-is» проблему не решит и снова ударит по мультиаренде.

---

## 10. Архитектурный check vs исходный замысел DELNO/QL

Исходный замысел: офисный ИИ-сотрудник для **каждого** клиента, с телефонией AVA, почтой, знаниями, outreach — максимально умный, но изолированный.

Сейчас ближе к: сильный **онбординг/секретарь scaffold** + честный readiness + правильная изоляция звонков; слабый **research/ops autonomy**.

Соответствие замыслу: **инфра изоляции — да (после Codex); интеллект агента — нет**. Следующий приоритет продукта — Фазы A→B, не новый rewrite телефонии.
