# AVA outbound: тишина после ответа + обрыв «Алло»

## Симптом

После снятия трубки несколько секунд тишины, затем приветствие рвётся коротким «Алло»/«Приём».

Пример `call_id=1792675305.0` (2026-10-22): answer→greeting **14.25 s**, barge-in в ту же мс.

## Где теряется время (после Answer / Stasis)

| # | Этап | Оценка |
|---|------|--------|
| 1 | AudioSocket bridge → только потом старт realtime | 0.3–1 s |
| 2 | OpenAI WS + `session.created` + `session.update` ACK | 1–5 s (+ reconnect на `gpt-live-1`) |
| 3 | TTS greeting (`response.create`) | 1–5 s |
| 4 | Streaming jitter buffer (было **950 ms**) | ~1 s |

Per-call script load (ARI vars + JSON) — десятки–сотни ms, не главный вклад.

## Почему рвётся приветствие

Провайдер `openai_live_pilot` в **GA**: `server_vad` с `create_response=true` / `interrupt_response=true`.  
`_send_explicit_greeting` отключал VAD только в Beta; в GA «Алло» сразу резало первую фразу.  
Локальный `barge_in.initial_protection_ms=200` почти не защищал, если `conversation_state != greeting`.

## Фикс (`console/scripts/patch_greeting_latency.py`)

1. **Локальный ARI Playback** `sound:custom/ql_secretary_hello` сразу после добавления caller в bridge (до Live WS ~6s). Env: `AVA_LOCAL_GREETING_URI`.
2. **`openai_live`**: при `local_greeting_played` — не кикает greeting (`LOCAL_GREETING_SKIP_LIVE_KICK`).
3. **GA VAD mute** на время greeting (openai_realtime), restore после `response.done`.
4. **Pre-warm**: kickoff Live/realtime WS параллельно с originate AudioSocket.
5. YAML: `jitter_buffer_ms: 120`, `greeting_protection_ms: 8000`, `initial_protection_ms: 2000`.
6. `conversation_state=greeting` при per-call greeting.
7. Метрика: `GET /api/outbound/greeting-latency`.

Деплой: `bash console/scripts/install_prod.sh` (патч + recreate `ai_engine`).

После патча в логах: `LOCAL_GREETING_PLAY` → сразу звук; `Connecting OpenAI Live` параллельно; `LOCAL_GREETING_SKIP_LIVE_KICK`.

## Baseline (до патча)

| call_id | answer→greeting | greet→«алло» |
|---------|----------------:|-------------:|
| 1792675305.0 | 14.25 s | 0.002 s |
| 1792675422.4 | 5.67 s | 0.807 s |
| 1792592489.16 | 8.85 s | 0.040 s |

**Цель после:** answer→greeting ≤ **1.2 s**, short barge-in не режет первую фразу.

Проверка после 3 тестовых звонков:

```bash
curl -sH "X-Console-Token: $CONSOLE_TOKEN" \
  'http://127.0.0.1:8013/api/outbound/greeting-latency?limit=3'
```
