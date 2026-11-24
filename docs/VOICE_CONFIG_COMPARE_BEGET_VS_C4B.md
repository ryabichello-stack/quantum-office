# Сравнение голосового конфига: Beget backup vs C4B

**Источники**

| Срез | Файл | Когда |
|------|------|--------|
| **Beget (эталон «как работало»)** | `/srv/beget-full-20261112/.../root/ava/config/ai-agent.local.yaml` | бэкап ~2026-11-12 |
| **C4B thin (сломанный UX)** | `ai-agent.local.yaml.bak.pre-canon-*` | recovery 2026-11-11…15, до канона |
| **C4B сейчас (канон)** | `/root/ava/config/ai-agent.local.yaml` | 2026-11-24 ~23:59 MSK |

Секреты не сравниваем.

---

## 1. Размер и роль

| | Beget | C4B thin (до фикса) | C4B сейчас |
|--|------:|--------------------:|-----------:|
| Строк | ~1831 | 95 | ~222 |
| Байт | ~59 KB | ~4.4 KB | ~11 KB |
| Суть | Полный multi-context + pipelines + rich prompt | Урезанный recovery stub | Компактный канон: Beget-поведение + DELNO tools |

Beget — монолит «всё для QL». Сейчас — **универсальный секретарь** + discovery tools (для QL и следующих клиентов).

---

## 2. Модель / провайдер / ASR

| Параметр | Beget | C4B thin | C4B сейчас |
|----------|-------|----------|------------|
| Default provider | `openai_live_pilot` | `openai_realtime` | `openai_realtime` |
| Model | `gpt-realtime-2.1` (+ live pipelines) | **`gpt-realtime-2.1-mini`** | `gpt-realtime-2.1` |
| Voice | cedar | cedar | cedar |
| Speed | 1.0 (live pilot 1.1) | (default) | **1.05** |
| RU transcription | да (`gpt-live-transcribe`, lang=ru, keywords) | **нет** | да (lang=ru + email-домены в keywords) |
| Transcription prompt | QL/платежи/ломбарды | — | имя, email, дата/время + платежи |

**Почему имена/email ломались на thin:** mini без RU transcription hints → английская каша («неле», «data excess valley»).

---

## 3. VAD / barge-in / latency

| Параметр | Beget | C4B thin | C4B сейчас |
|----------|------:|---------:|-----------:|
| `silence_duration_ms` | **1700** | **1700** | **550** |
| VAD threshold | 0.62 | 0.62 | 0.55 |
| `prefix_padding_ms` | 450 | 200 | 200 |
| `interrupt_response` (в YAML) | false | — | — (поле не в схеме engine) |
| barge_in | полный блок | только `enabled: true` | полный блок + fallback |
| `greeting_protection_ms` | **8000** | нет | **2500** |
| `energy_threshold` | 1600 | — | 1200 |
| `min_ms` | 400 | — | 280 |
| streaming/jitter | да (120 ms и т.д.) | **нет** | да (как Beget, низкий jitter) |

**Интерпретация**

- Beget: хороший prompt, но **долгий silence 1700** и **8 s** защиты приветствия → ощущение «не перебивается» на длинных репликах бота.
- Thin: тот же долгий silence + почти нет barge_in → хуже.
- Сейчас: короче пауза до ответа бота + умеренная защита greeting → целевой barge-in; если слишком чувствительно — поднять `silence` до ~700–900.

---

## 4. Промпт: readback и сценарий

| Возможность | Beget | C4B thin | C4B сейчас |
|-------------|:-----:|:--------:|:----------:|
| Блок «ИМЯ, EMAIL» | да | нет | да (readback) |
| «Верно?» после имени | да | нет | да |
| Email «собака / точка» | да | нет | да |
| Readback даты/времени | да | нет | да |
| Исправление при «нет» | да | нет | да |
| «Перебивает — уступай» | да | нет | да |
| Жёсткий QL product pitch в prompt | да (длинный) | короткий QL | факты только из tools |
| `list_enabled_tools` / ready | нет (хардкод tools) | да (коротко) | **да, обязательно** |
| `book_meeting` и meeting-verbs | нет | нет | **да (prefer ready)** |

---

## 5. Tools

| | Beget | C4B thin | C4B сейчас |
|--|-------|----------|------------|
| Транспорт tools | прямые in_call tools mailer | `delno_office` → API | `delno_office` → API |
| Как выбирает tool | зашитый список в prompt | частично list_enabled | **только list_enabled + ready=true** |
| Типичные id | check_calendar, create_calendar_event, send_email, create_conference, get_company_knowledge, hangup | check_calendar, create_*, get_company_knowledge, hangup | discovery: book_meeting, suggest_other_time, confirm/reschedule/cancel, knowledge, hangup, … |
| Multi-tenant | по сути QL-only | DELNO bridge | DELNO bridge + универсальный prompt |

На живой QL-линии сейчас: `get_company_knowledge` ready; `book_meeting`/meeting-verbs ready; `check_calendar`/`create_calendar_event` часто **ready=false** — поэтому хардкод Beget-имён на C4B ломал бы запись.

---

## 6. Что взяли с Beget / что намеренно не копировали

**Взяли (поведение):**

- readback имени / email / даты;
- мужской род, ИИ-секретарь, короткий русский;
- cedar + полный `gpt-realtime-2.1` + RU transcription;
- нормальный barge_in + streaming.

**Не копировали целиком (59 KB монолит):**

- `openai_live_pilot` как default (на C4B стабильно крутится `openai_realtime`);
- десятки contexts/pipelines/cartesia_pilot;
- silence 1700 + greeting_protection 8000 (latency);
- зашитый QL tool-список без discovery.

**Добавили сверх Beget:**

- `delno_office` + `list_enabled_tools` / ready;
- универсальные meeting verbs;
- более короткий VAD для barge-in;
- канон-доки для Hermes.

---

## 7. Вердикт одной строкой

| Срез | Вердикт |
|------|---------|
| Beget | Хороший сценарий и ASR-hints; медленный turn-taking; tools QL-only |
| C4B thin | Потерял readback/ASR/barge → имена/email/перебивание развалились |
| C4B сейчас | Beget-дисциплина разговора + быстрее VAD + multi-tenant discovery tools |

Проверка: перезвонить → имя/email с «Верно?», попытка перебить бота mid-sentence, запись через `book_meeting` если ready.
