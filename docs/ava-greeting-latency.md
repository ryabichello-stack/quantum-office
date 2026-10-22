# AVA outbound: тишина после ответа + обрыв «Алло»

## Симптом

После снятия трубки несколько секунд тишины (раньше 6–14s). Цель: **≤1.5s** answer→голос Cedar.

## Фикс (прод)

1. **VPN proxy для Live WSS** — `AVA_OPENAI_PROXY` (Minsk HTTP inbound). Direct к `api.openai.com` ~9s; через proxy ~0.5–1s. **Не** ставить глобальный `HTTPS_PROXY` (ломает ARI / local WS).
2. **Live warm keepalive** — idle: `session.start` + paced mic silence (20ms). На answer: только greeting kick (тот же Cedar). Без mic keepalive kick давал цифровую тишину (~20s rms=0).
3. Emit refresh на adopt (AudioSocket `slin`) + drop digital silence на ulaw/pcm.

Чужой WAV (`ql_secretary_hello`) **откатили**. Silent-fallback «wait + cold reconnect» **запрещён** (раздувал задержку до ~15s).

## Офлайн-пробы (без звонка на телефон)

```bash
docker cp console/scripts/probe_live_greeting_latency.py ai_engine:/tmp/
docker exec ai_engine python3 /tmp/probe_live_greeting_latency.py
```

Проверено 2026-10-22: kick→audio **1.18 / 0.85 / 1.42 s** (3/3 ≤1.5s) при warm+keepalive+proxy.

## Скрипты

| Script | Role |
|--------|------|
| `patch_live_warm_pool.py` | base warm pool |
| `harden_live_warm_pool.py` | health / tools / skip prewarm |
| `patch_live_openai_proxy.py` | `_live_ws_proxy()` |
| `patch_live_warm_keepalive.py` | session+mic keepalive, kick-only adopt |
| `probe_live_greeting_latency.py` | offline TTFA (no phone) |

Env: `AVA_LIVE_WARM=1`, `AVA_OPENAI_PROXY=http://user:pass@127.0.0.1:17892` (только в `/root/ava/.env`).

Логи успеха: `LIVE_WARM_READY` (mode=keepalive) → `GREETING_PREWARM_SKIP_WARM` → `LIVE_WARM_USED` / `LIVE_WARM_ADOPT` → first audio &lt;1.5s, `provider_out` rms ≫ 0.
