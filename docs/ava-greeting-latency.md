# AVA outbound: тишина после ответа + обрыв «Алло»

## Симптом

После снятия трубки несколько секунд тишины, затем приветствие рвётся коротким «Алло»/«Приём».

Пример `call_id=1792675305.0` (2026-10-22): answer→greeting **14.25 s**, barge-in в ту же мс.

## Где теряется время

| # | Этап | Оценка |
|---|------|--------|
| 1 | Холодный OpenAI Live `connect` + `session.started` | ~1.9–6 s (на звонке event-loop часто раздувает до 6s+) |
| 2 | TTS greeting (`commentary.append` kick) | 0.3–1.5 s |
| 3 | Streaming jitter (было **950 ms**) | ~1 s |

## Неверный путь (откатили)

Локальный ARI Playback `ql_secretary_hello` — звук был **другим голосом**, не Cedar Live. Убрано.

## Правильный фикс

1. **Live warm pool** (`console/scripts/patch_live_warm_pool.py`): в простое держим один готовый Live WS (`LIVE_WARM_READY`). На answer — `LIVE_WARM_ADOPT` + greeting kick **тем же Cedar**. Цель answer→greeting ≤ **1.5 s**.
2. **Pre-warm fallback**: kickoff provider параллельно AudioSocket, если слот пуст.
3. YAML: `jitter_buffer_ms: 120`, `greeting_protection_ms: 8000`.
4. GA VAD mute на `openai_realtime` (если путь realtime).
5. Метрика: `GET /api/outbound/greeting-latency`.

Env: `AVA_LIVE_WARM=1` (по умолчанию). `0` — выключить пул.

Деплой: `bash console/scripts/install_prod.sh` (патч + recreate `ai_engine`).

Логи успеха: `LIVE_WARM_READY` → на звонке `LIVE_WARM_USED` / `LIVE_WARM_ADOPT` → `OpenAI Live greeting kick sent` за доли секунды.

## Baseline (до)

| call_id | answer→greeting |
|---------|----------------:|
| 1792675305.0 | 14.25 s |
| 1792675422.4 | 5.67 s |
| 1792682975.8 | 9.33 s (после pre-warm без warm-pool) |
