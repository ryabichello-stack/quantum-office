# Канон голосового секретаря (AVA → Hermes)

**Зачем:** единые правила для QL dogfood и всех следующих клиентов.  
**Конфиг-шаблон:** [`voice/ai-agent.secretary.canon.yaml`](voice/ai-agent.secretary.canon.yaml) → прод `/root/ava/config/ai-agent.local.yaml`.  
**Связанный RCA линии:** [`TELEPHONY_RCA_2026-11-24_MANGO_UNAVAILABLE.md`](TELEPHONY_RCA_2026-11-24_MANGO_UNAVAILABLE.md).

## Проблема 2026-11-24 (после подъёма SIP)

На C4B после recovery стоял **урезанный** `ai-agent.local.yaml` (~95 строк):

- модель `gpt-realtime-2.1-mini` без RU transcription hints;
- короткий prompt без обязательного readback имени/email/даты;
- `barge_in: {enabled: true}` без порогов; `silence_duration_ms: 1700` → ощущение «не слышит / не перебивается».

На Beget был полный промпт (readback email «собака/точка», «Верно?» для имени) + barge_in/streaming.

## Универсальные правила (для AVA и для Hermes telephony_script)

1. **Readback обязателен** для имени, email, даты/времени (и компании/интереса, если собираем).  
   Схема: услышал → повторил → «Верно?» → если нет — исправил → снова readback.
2. **Email вслух:** `@` → «собака», `.` → «точка». Без подтверждения — никаких write-tools.
3. **Странное ASR** (английская каша вместо русского имени) → не спорить, попросить повторить, снова readback.
4. **Факты о компании** только из tools / tenant KB — не хардкодить цифры в промпт как единственный источник.
5. **Tools — discovery, не хардкод:** сначала `list_enabled_tools`, дальше только id с `ready=true`.  
   Набор у tenant разный: сейчас часто универсальные meeting-verbs (`book_meeting`, `suggest_other_time`, `confirm_meeting`, `reschedule_meeting`, `cancel_meeting`) плюс `get_company_knowledge`; старые `check_calendar` / `create_calendar_event` могут быть `ready=false`. Не вызывать «привычные» имена вслепую.
6. **Write** только с `confirmed_by_caller true`. Не обещать успех при `ok=false` / отсутствии tool.
7. **Barge-in / latency:** короткий VAD silence (~500–600 ms), `barge_in.enabled`, умеренный `greeting_protection_ms` (~2–3 s, не 8 s).
8. **Модель:** полный realtime (`gpt-realtime-2.1`), не mini; `input_transcription_language: ru` + keywords доменов почты.

## Hermes

При генерации/сохранении `tenant.settings.telephony` / `telephony_script` Гермес должен **вшивать**:
- блоки readback (имя/email/дата);
- запрет write без подтверждения;
- правило «сначала list_enabled_tools / только ready» — **не** фиксированный список QL-инструментов.

Компания = tenant. Инструменты = то, что линия реально отдала.

## Деплой на C4B

```bash
cp -a /root/ava/config/ai-agent.local.yaml /root/ava/config/ai-agent.local.yaml.bak.$(date -u +%Y%m%dT%H%M%SZ)
# положить canon в ai-agent.local.yaml
cd /root/ava && docker compose restart ai_engine
curl -sS http://127.0.0.1:15000/health
```
