# DATA MAPPING — AS-IS → каноническая модель ТЗ

**Дата:** 2026-08-23  
**Назначение:** явный mapping сущностей/полей для Этапа 1 (Spec §25 п.5).

---

## 1. Identity & tenancy

| Канон | AS-IS источник | Поля / ключи | Миграция |
|-------|----------------|--------------|----------|
| `Tenant` | implicit | нет таблицы; brain: `tenant_id='quantum-labs'` | Добавить default tenant; enforced filter |
| `User` | Console login | `CONSOLE_USER` / session cookie | Позже RBAC (Этап 8) |
| `Role` / `Permission` | single token | `OUTREACH_UI_TOKEN`, `CONSOLE_TOKEN`, `WEBHOOK_TOKEN` | Не ломать; добавить roles поверх |
| `ProductProfile` | vault markdown | `knowledge/vault/.../products/*` | JSON package tenant |
| `ICPTemplate` | hardcode ломбарды в кампаниях | packs / settings | Config, не код |
| `DecisionRoleTemplate` | — | — | Greenfield JSON |
| `ChannelPolicy` | runtime_settings + deliverability | caps, windows, notify flags | Extract to policy package |

---

## 2. Accounts & people

| Канон | AS-IS | Ключевые поля | Действие |
|-------|-------|---------------|----------|
| `Account` | `modules/clients.companies` | `bitrix_id`, `title`, `inn`, `city`, `timezone`, `primary_email` | Facade + `lifecycle_status` |
| `Person` | `modules/clients.contacts` | `bitrix_id`, `display_name`, emails | Новая/нормализованная таблица |
| `Employment` | `director_*` на company + Bitrix contact company link | title, company | Явная связь person↔account |
| `ContactPoint` | `client_emails`, outbox.email, phones JSON | email/phone | verification_status + consent link |
| `DataSource` / `Evidence` | частично DaData raw, Bitrix raw_json | — | Provenance table Этап 1 |
| Bitrix company id | `companies.bitrix_id` | string | Сохранить как external ref |
| Outbox company link | `outbox.company_id` | Bitrix id | Map → Account.id |

### Lifecycle mapping

См. [GAP_ANALYSIS.md §3](./GAP_ANALYSIS.md) — `NEW`…`BLACKLISTED` ↔ outbox/sequence/consent.

---

## 3. Communications

| Канон | AS-IS | Notes |
|-------|-------|-------|
| `Conversation` | группировка по email/company в UI thread | Нужна явная таблица/id |
| `Message` inbound | `reply_inbox` | classification, preview, message_id |
| `Message` outbound campaign | `outbox` + `send_events` | Message-ID, status |
| `Message` operator reply | `operator_replies` | In-Reply-To |
| `Call` | `/root/ava/data/call_history.db` → `call_records` | Вне репо; facade |
| `Transcript` | `conversation_history` JSON в call_records | Console already parses |

---

## 4. Consent & suppression

| Канон | AS-IS |
|-------|-------|
| `ConsentRecord` | `consent_ledger` |
| `SuppressionEntry` | `deliverability.suppression` |
| Unsubscribe public | `/unsubscribe/{token}` |
| BLACKLISTED | `manual_dnc` + suppression reason |

---

## 5. Sales

| Канон | AS-IS | Gap |
|-------|-------|-----|
| `Lead` | Bitrix deal on reply; callback_requests | Local Lead table |
| `Opportunity` | Bitrix deal stage `NEW`… | Local Opportunity + sync |
| `Task` / `Meeting` | Bitrix tasks; calendar/conference | Unify Meeting entity |
| `Note` | timeline comments Bitrix | Local notes later |

---

## 6. Orchestration

| Канон | AS-IS |
|-------|-------|
| `JourneyDefinition` | pack steps + DEFAULT_STEPS |
| `JourneyEnrollment` | `sequence_leads` |
| `StepExecution` | implied by current_step / outbox sends |
| Runner state | `OUTREACH_RUN_STATE` playing/paused/stopped |

---

## 7. Knowledge

| Канон | AS-IS (`brain_platform`) |
|-------|--------------------------|
| `KnowledgeDocument` | `documents` |
| `KnowledgeClaim` | vault claims / chunks (частично) |
| Search | FTS + embeddings + RRF |
| Contacts/threads | `contacts`, `threads`, `emails` |

---

## 8. Social / greenfield (нет AS-IS таблиц)

`SocialSource`, `SocialIdentity`, `LPRSearchRun`, `CandidateProfile`, `IdentityCluster`, `VerificationDecision`, `PublicActivity`, `IntentSignal`, `CommitteeMember` — **создавать в Slice B**, не маппить из outreach.

---

## 9. Events (целевой envelope ← AS-IS triggers)

| Event type | AS-IS trigger today |
|------------|---------------------|
| `message.sent` | sender.py after SMTP |
| `message.received` | reply_watcher → reply_inbox |
| `message.classified` | classify_reply |
| `call.completed` | Console call watcher |
| `journey.stopped` | sequence stop on reply/unsub |
| `consent.changed` | consent_ledger.record |
| `suppression.created` | deliverability.add_suppression |

Остальные типы ТЗ §10 — после Orchestrator.
