# DELNO — файлы тенанта и ПДн (152‑ФЗ)

**Статус:** целевая архитектура (dogfood Cloud4Box / dlno.ru)  
**Редакция:** 12 ноября 2026  
**Связано:** `DELNO_OFFICE_OS_ARCHITECTURE.md`, `DEPLOY_ISOLATION.md`, сайт `/privacy` `/terms`

---

## 1. Цель

Каждый тенант работает в **изолированном контуре файлов и знаний**:

- чужие объекты недоступны даже при утечке UUID соседнего тенанта;
- потеря/утечка одного тенанта не открывает остальных;
- персональные данные (ПДн) **хранятся и обрабатываются в РФ**;
- во внешние LLM / зарубежные API уходит только **обезличенный** минимум (или обработка остаётся на RU-модели).

---

## 2. Модель хранения (per tenant)

### 2.1 Логическое дерево

```
tenants/{tenant_id}/
  uploads/          # кабинет / онбординг / вложения Hermes
  knowledge/        # исходники KB + extracted text
  telephony/        # сценарии, записи звонков (если включены)
  mail/             # вложения исходящих/входящих (кэш)
  exports/          # выгрузки по запросу владельца
  tmp/              # TTL ≤ 24h, автоочистка
```

`tenant_id` — UUID из БД (не slug в пути на диске: slug может меняться).  
Slug допустим только как **метаданные** в индексе, не как единственный ключ ACL.

### 2.2 Физика (прод РФ)

| Слой | Выбор | Зачем |
|------|--------|--------|
| Object store | Yandex Object Storage / Selectel S3 **регион РФ** | резидентность, durability |
| Prefix | `t/{tenant_id}/…` | жёсткая изоляция ключей |
| БД метаданных | Postgres DELNO (`tenant_files`) | ACL, hash, retention, audit |
| Локальный диск | только `tmp/` и кэш извлечения | не primary source of truth |

До перехода на object store допустим том `/data/tenants/{tenant_id}/` **внутри** compose DELNO
(`TENANT_FILES_ROOT`, volume `delno-tenant-files` в `deploy/docker-compose.stack.yml`), с теми же
правилами путей. Онбординг-загрузки пишут в `uploads/`. Legacy `/data/onboarding` volume
сохраняется для уже лежащих файлов, новые — только под `tenants/`.

### 2.3 Шифрование

1. **At rest:** SSE на стороне бакета (провайдер РФ) + **envelope encryption**:
   - master key в HSM/секрет-хранилище хоста (не в git);
   - per-tenant DEK в Postgres (зашифрован master key);
   - объект на диске/S3 = ciphertext.
2. **In transit:** TLS только; внутренние вызовы по docker-сети без публикации портов наружу.
3. **Секреты** (SIP, SMTP, OAuth дисков) — только `tenant.settings.secrets` / vault, **не** в файловом дереве plaintext.

### 2.4 API-контракт

Все операции только через `delno-api` с `TenantContext`:

- `POST /v1/tenant/files` — upload (multipart) → `file_id`
- `GET  /v1/tenant/files` — list своего prefix
- `GET  /v1/tenant/files/{id}` — metadata (+ short-lived signed URL)
- `DELETE /v1/tenant/files/{id}` — soft-delete → purge по retention

Запрещено:

- принимать «сырой» путь от клиента (`../`, абсолютные пути);
- отдавать файлы по slug другого тенанта;
- шарить один allowlist/`FILES_LOCAL_*` на всех (legacy `ava-files` — только QL, не multi-tenant SaaS).

Hermes / Frontline читают файлы **только** через tool с `tenant_id` из сессии.

---

## 3. Изоляция и угрозы

| Угроза | Контроль |
|--------|----------|
| Path traversal | canonical path must start with `tenants/{tenant_id}/`; иначе 403 |
| IDOR | `file_id` lookup **всегда** `WHERE tenant_id = ctx.tenant_id` |
| Украденный JWT | короткий TTL + refresh; revoke; audit |
| Утечка бэкапа | бэкапы шифруются; restore только в тот же tenant map |
| Insider / ops | least privilege; секреты mode 600; без общего mount всех тенантов в один контейнер «на чтение» |
| Malware upload | allowlist расширений + размер + (этап 2) AV scan; исполняемые — блок |
| Cross-tenant LLM leak | в промпт не класть чужие документы; RAG только `X-Tenant-Id` |
| Data loss | object store versioning + ежедневный encrypted backup off-box в РФ |

**Тест изоляции (обязательный перед вторым платящим клиентом):**  
tenant A загружает файл → JWT tenant B → list/get/delete → всё 404/403; brain search B не возвращает A.

---

## 4. Внешние диски (Я.Диск, Mail.ru, GDrive, OneDrive)

Коннекторы **per tenant** в vault:

- токены только этого тенанта;
- list/fetch идут от имени тенанта; кэш копии — в его prefix;
- **GDrive / OneDrive** = обработка/хранение у иностранного оператора по выбору клиента.  
  По умолчанию в онбординге предлагаем **Яндекс.Диск / Mail.ru / локальный кабинет DELNO (РФ)**.  
  Подключение зарубежных дисков — отдельное явное согласие («данные могут обрабатываться вне РФ провайдером диска»).

Legacy `delno-office/files` с env-токенами — **не** путь для SaaS; заменить на tenant connectors.

---

## 5. ПДн, 152‑ФЗ, резидентность

### 5.1 Роли

| Роль | Кто |
|------|-----|
| Оператор ПДн (сайт dlno.ru, аккаунты) | ИП Рябов Д.В. |
| Оператор / обработчик контента клиентов тенанта | DELNO как SaaS; тенант — оператор своих клиентов (B2B) |
| Поручение на обработку | в договоре / оферте + Политика |

### 5.2 Категории данных

- **Аккаунт:** email, ФИО/название, ИНН юрлица, телефоны владельца.
- **Контент тенанта:** KB, сценарии, записи, переписка, вложения — **данные клиента тенанта**, изоляция по `tenant_id`.
- **Технические:** IP, user-agent, логи доступа (срок хранения ограничен).

### 5.3 Принцип «безлично наружу»

1. **Хранение и первичный поиск** — только РФ (Postgres + object store + knowledge в контуре DELNO).
2. **LLM / Realtime:**  
   - целевой режим: RU-модель (YandexGPT / GigaChat / self-host) **или**  
   - перед любым зарубежным API — **минификация + обезличивание** (без ФИО, телефонов, email, адресов, вложений as-is);  
   - сырые файлы и записи звонков **не** загружаются в OpenAI Files API.
3. Текущий dogfood-egress OpenAI через мост — **технический долг**: либо перевести голос/текст на RU-провайдера, либо оставить только для обезличенных демо с явным согласием. Не позиционировать как «ПДн не покидают РФ», пока сырой диалог уходит в OpenAI.

### 5.4 Права субъекта

Запрос на доступ / уточнение / удаление / отзыв согласия → `office@dlno.ru` (и кабинет: удаление файлов тенанта + soft-delete аккаунта).  
Срок ответа — по 152‑ФЗ (ориентир ≤ 10 рабочих дней на типовой запрос).

### 5.5 Сайт

Публичные документы:

- `/privacy` — Политика конфиденциальности (152‑ФЗ)
- `/terms` — Пользовательское соглашение
- согласие в формах лидов (уже есть ссылка на privacy)

---

## 6. Retention и удаление

| Тип | Срок | Удаление |
|-----|------|----------|
| `tmp/` | ≤ 24h | cron |
| uploads без привязки к KB | по политике тарифа (по умолчанию 180 дней неактивности → warn) | soft → hard 30 дней |
| knowledge originals | пока тенант активен | cascade при закрытии договора |
| call recordings (если вкл.) | default 90 дней, настраиваемо | purge job |
| audit log | ≥ 1 год | append-only |

Удаление тенанта: tombstone → блокировка API → purge объектов prefix → wipe DEK.

---

## 7. Этапы внедрения

| Этап | Что |
|------|-----|
| **F0** | Правила путей + запрет traversal + tenant-scoped onboarding (уже частично) |
| **F1** | Таблица `tenant_files`, API list/get/delete, audit |
| **F2** | S3 РФ + envelope encryption + signed URLs |
| **F3** | Tenant vault `files_*` + Hermes «подключи Яндекс/Mail/Google» + per-request creds в files broker (**done**) |
| **F4** | RU LLM path / anonymizer перед foreign LLM; health «residency mode» |
| **F5** | Isolation e2e test в CI + DR restore drill |

---

## 8. Что не делать

- Не класть файлы всех тенантов в один плоский каталог без prefix.
- Не использовать Beget/QL paths; прод файлов — контур DELNO / Cloud4Box + РФ object store.
- Не обещать «данные не уходят за рубеж», пока голос/чат шлёт сырой текст в OpenAI.
- Не отдавать ops «общий» SSH mount `/data/tenants` в CI-агенты без необходимости.
