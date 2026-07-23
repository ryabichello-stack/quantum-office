# Second Brain — план до идеала (БД · граф · vault · агенты)

Связан с: [`ADR-0001-second-brain.md`](./ADR-0001-second-brain.md), [`OPERATIONAL_MEMORY.md`](./OPERATIONAL_MEMORY.md), [`SECOND_BRAIN_ROADMAP.md`](./SECOND_BRAIN_ROADMAP.md)

**Цель:** любой рабочий вопрос → один поиск → ответ с цитатой и правильным ACL; корпус растёт сам; дублей нет; MD/Vault = SoT, индексы производные.

**Не трогаем:** Polyhub / Asterisk / Mango / VPN.

---

## 0. Где мы сейчас (факт на проде)

| Слой | Сейчас | Идеал |
|------|--------|-------|
| SoT для агентов | Second Brain `/api/brain/*` | то же + Vault git как канон |
| FAQ | единый `quantum_labs.md` (продукт + ломбарды) | шарды в `quantum-brain` |
| Поиск | SQLite FTS + OpenAI embeddings + RRF hybrid | Postgres FTS + **pgvector HNSW** + RRF + rerank |
| Векторы | `chunks.embedding_json` | колонка `vector(1536)` + HNSW |
| Граф | таблицы-заготовки / контакты отдельно | полный `GraphStore` (people↔company↔thread↔doc) |
| Ingest | faq + files + IMAP; dedupe/hash/prune | + CRM/Bitrix, meetings, continuous |
| ACL | in-query на SQLite | in-query на Postgres FTS/vector/graph |
| Voice | legacy `/api/knowledge/*` | brain после security approval |
| Zones | logical `index_zone` | physical `knowledge_public` / `knowledge_private` |

Уже закрыто в office-репо: hybrid search, embed-backfill, idempotent ingest, text-bot SoT=brain, agentic loop.

---

## 1. Целевая картинка

```text
SOURCES                VAULT (SoT)              INDEXES (derived)
───────                ───────────              ─────────────────
FAQ MD          ┐
Mail IMAP       ├──►  quantum-brain repo  ├──►  Postgres FTS
Server files    │     + frontmatter ACL   ├──►  pgvector HNSW
Meetings/CRM    ┘     + publish pipeline  ├──►  Graph (entities/edges)
                                          └──►  zones: public | private

                              │
                              ▼
                    Search Gateway (hybrid+ACL)
                              │
              voice · text-bot · Cursor MCP · outreach
```

**Правило:** расхождение MD ↔ vector → правь MD, переиндексируй. Vector/graph никогда не SoT.

---

## 2. План по базам данных

### Этап B1 — Postgres на проде (фундамент)

**Сделать**
1. Поднять Postgres 16+ на `5.35.86.62` (или managed) — отдельный инстанс/DB `quantum_brain`.
2. Расширения: `vector` (pgvector), `pg_trgm` (опционально).
3. Роли: `brain_app` (CRUD), `brain_readonly` (для отчётов).
4. Бэкапы: daily dump + WAL/PITR; путь вне `/opt/ava-knowledge/data` только как hot replica позже.
5. Env: `BRAIN_DATABASE_URL=postgresql://…`, `BRAIN_VECTOR_BACKEND=pgvector`.

**Не делать:** сразу выключать SQLite; dual-write период.

**Exit:** `SELECT extname FROM pg_extension` показывает `vector`; app коннектится health-check’ом.

### Этап B2 — Схема Postgres (= ADR, без ломки API)

**Таблицы (транзакционно с ACL-полями как сейчас)**
- `documents`, `chunks` (+ `embedding vector(1536)`, `tsv tsvector`)
- `contacts`, `contact_emails`, `threads`, `emails`, `files`
- `entities`, `entity_aliases`, `edges`, `document_entities`, `entity_versions`
- `audit_log`, `ingest_state`, `meta`
- Zones: либо `index_zone` + partial indexes, либо две schema/DB: `knowledge_public` / `knowledge_private`

**Индексы**
- FTS: GIN на `chunks.tsv` / `documents.tsv`
- Vector: `CREATE INDEX … USING hnsw (embedding vector_cosine_ops)`
- ACL: `(tenant_id, index_zone, visibility)` + GIN на allow-list JSONB при необходимости

**Миграции:** `brain_platform/db/migrations/` (numbered SQL); CLI `brain migrate`.

**Exit:** пустая схема + миграции накатываются идемпотентно.

### Этап B3 — Миграция данных SQLite → Postgres (без потери)

**Порядок**
1. Freeze ingest (короткое окно) или dual-write.
2. Копировать documents/chunks/contacts/emails/threads/files **с теми же id**.
3. Перенести embeddings: JSON → `vector(1536)` (батчами).
4. Пересчитать `tsv` из text.
5. Проверка: counts + checksum body_hash + sample hybrid queries (diff top-k).
6. Feature flag `BRAIN_STORE=sqlite|postgres|dual`.
7. Cutover: `BRAIN_STORE=postgres`, SQLite оставить read-only snapshot 14 дней.

**Rollback:** `BRAIN_STORE=sqlite` + тот же API.

**Exit:** counts совпали; hybrid smoke на 20 эталонных запросах ≥ parity.

### Этап B4 — Physical zones

1. Разнести public/private (отдельные tablespaces/schemas или DB).
2. Principals `voice-public` → только public schema.
3. Negative tests: mail/PII никогда не в public zone.

---

## 3. План по графу знаний

### Этап G1 — GraphStore v1 (Postgres tables)

**Сущности (`entities.kind`)**
- `person`, `company`, `project`, `thread_topic`, `product`, `document`

**Рёбра (`edges.relation_type`)**
- `works_at`, `participant_of`, `mentions`, `about_company`, `decided_in`, `owns_doc`, `related_to`

**API**
- `POST /api/brain/graph/expand` `{entity_id|q, depth, limit}` + ACL in-query
- CLI: `brain graph expand "Парцуф"`

**Exit:** expand по контакту → компания + треды, без утечек чужих ACL.

### Этап G2 — Автоизвлечение из уже имеющегося корпуса

| Источник | Что пишем в граф |
|----------|------------------|
| `contacts` + emails | person ↔ company, person ↔ thread |
| FAQ / lombards | product ↔ scenario entities (ручной/полуавто) |
| Subject/body NER light | company aliases (ИНН, ООО «…») → entity_aliases |
| Files | document ↔ project (если path/tag) |

Правила:
- high-confidence рёбра → `review_status=accepted`
- low-confidence → `pending` (не в default retrieve)
- идемпотентные upsert по canonical key

### Этап G3 — Graph в hybrid retrieve

1. Query → keyword+vector hits.
2. Из hits достать entity ids → expand 1 hop.
3. Подмешать связанные chunks/threads с пониженным RRF-весом.
4. Ответ: факты + «связанные люди/компании/письма».

**Exit:** вопрос «кто с Альфой по НордСервису» даёт контакт + треды через граф, не только FTS.

### Этап G4 (позже) — Neo4j только если Postgres graph упрётся в perf

До этого не трогаем (ADR).

---

## 4. План по Vault (канон контента)

### Этап V1 — Repo `quantum-brain`

1. Private GitHub/GitLab repo.
2. Дерево: `vault/products/`, `vault/meetings/`, `vault/ops/`, `vault/_meta/`.
3. `_meta/`: taxonomy, acl-roles, service-principals.
4. CI: validate frontmatter (tenant, ACL, classification, ai_processing).

### Этап V2 — Нарезка монолита

Скопировать (не удаляя) `quantum_labs.md` в шарды:
- product FAQ / legal / AVA ops / lombards playbook / sales scripts  
Каждый файл — полный security frontmatter + `source: legacy#anchor`.

### Этап V3 — Publish pipeline

1. Merge в `main` vault → build release bundle (tar/OCI).
2. Prod: pull bundle → ingest → reindex.
3. `public` только manual approval в frontmatter publication.

### Этап V4 — Убрать dual SoT

1. `/root/ava/.../quantum_labs.md` становится export из vault (или symlink на bundle).
2. Office `content/quantum_labs.md` — generated artifact, не ручной SoT.

---

## 5. План по поиску и качеству ответа

### Этап S1 — Postgres hybrid (замена sqlite_json)

- `mode=keyword|semantic|hybrid` уже есть → backend pgvector.
- RRF сохранить; добавить optional cross-encoder/rerank later.

### Этап S2 — Citations + confidence

- В ответе API: `document_id`, `chunk_id`, `thread_id`, `score`, `citation`.
- Text-bot обязан ссылаться на источник (письмо/FAQ), не выдумывать.

### Этап S3 — Eval harness

Набор 50–100 реальных вопросов:
- контакты, комплаенс/Альфа, тарифы, ломбарды, «что обещали клиенту X»
- CI: recall@5 / citation presence / ACL leak tests

### Этап S4 — Rerank (если eval просел на long-tail)

Лёгкий reranker только на top-20; не в critical path для voice latency без замера.

---

## 6. План по агентам и switch

### Этап A1 — Text-bot (уже почти)

- SoT=brain, hybrid — done.
- Добавить tool `expand_office_graph` после G1.

### Этап A2 — MCP для Cursor

- `kb.search`, `kb.get`, `kb.related`, `kb.ingest_status`
- Тот же principal/ACL.

### Этап A3 — Voice switch (отдельный approval)

1. Negative-security pack зелёный на Postgres.
2. Dual-read voice: legacy + brain compare.
3. Cutover mailer proxy → brain faq-safe channel only.
4. Rollback flag на legacy.

---

## 7. План по ingest (рост корпуса)

| Источник | Статус | Дальше |
|----------|--------|--------|
| FAQ MD | ✅ | из vault bundle |
| Files + inbox | ✅ dedupe | watch/inotify optional |
| IMAP mail | ✅ | + attachments text extract |
| Contacts repair | ✅ | graph link G2 |
| Bitrix/CRM | ❌ | webhook → notes/deals entities |
| Meeting notes | ❌ | inbox md / calendar attach |
| Telegram export | ❌ | optional later |

Всегда: safety scan → ACL classify → idempotent upsert → embed → graph upsert.

---

## 8. Порядок работ (сводка)

| # | Этап | Зависимости | Результат |
|---|------|-------------|-----------|
| 1 | **B1** Postgres + pgvector | доступ к серверу/managed | живая БД |
| 2 | **B2** схема + миграции | B1 | пустой brain schema |
| 3 | **B3** migrate SQLite→PG | B2 | prod на Postgres, без потери |
| 4 | **S1** hybrid на pgvector | B3 | идеальный vector tier |
| 5 | **B4** physical zones | B3 | public/private split |
| 6 | **V1–V2** vault repo + нарезка | параллельно с B* | канон вне app image |
| 7 | **G1–G3** graph + retrieve | B3 | ответы «кто/с кем/о чём» |
| 8 | **S2–S3** citations + eval | S1 | качество измеримо |
| 9 | **V3–V4** publish + убрать dual SoT | V2, B3 | один канон |
| 10 | **A2–A3** MCP + voice switch | S3, B4, security approval | все агенты на brain |

Каждый этап: тесты → feature flag → cutover → rollback path.

---

## 9. Критерии «идеально» (чеклист)

- [ ] Postgres+pgvector — единственный write store
- [ ] Hybrid FTS+vector(+graph) с ACL in-query
- [ ] Vault `quantum-brain` = SoT; prod = release bundle
- [ ] Нет dual path `/root/ava` vs git vs индекс
- [ ] Граф: человек–компания–тред–документ
- [ ] Ingest: почта/файлы/vault/CRM; без дублей и без потери
- [ ] Voice+text+Cursor на `/api/brain` (после approval)
- [ ] Eval ≥ порога; цитаты в ответах
- [ ] Public только manual publish; default deny

---

## 10. Статус cutover (2026-07-23)

**Готово на `5.35.86.62`:**
- **B1–B3 / S1:** Postgres 16 + pgvector; `BRAIN_STORE=postgres`; hybrid FTS+vector; sync-pg.
- **B4 lite:** zone guards (mail/PII never public); PG schemas/views `brain_public` / `brain_private`.
- **G1–G2:** GraphStore + `brain graph rebuild|expand`; API `/api/brain/graph/*`; text-bot `expand_office_graph`.
- **S2:** `citation` / `citations[]` / `source` / `thread_id` в search matches.
- **V1 scaffold:** `knowledge/vault/quantum-brain/` (private repo wiring later).

**Дальше:** G3 graph-in-retrieve, S3 eval harness, V2 shard monolith, A2 MCP, A3 voice switch (approval).

Нужно от вас: private repo `quantum-brain` + OK на voice switch когда eval готов.
