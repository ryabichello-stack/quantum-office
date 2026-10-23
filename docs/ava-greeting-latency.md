# AVA outbound: тишина после ответа + обрыв «Алло»

## Симптом

После снятия трубки несколько секунд тишины (раньше 6–14s). Цель: **≤1.5s** answer→голос Cedar.

## Фикс (прод)

1. **VPN proxy для Live WSS** — `AVA_OPENAI_PROXY` (Minsk HTTP inbound). Direct к `api.openai.com` ~9s; через proxy ~0.5–1s. **Не** ставить глобальный `HTTPS_PROXY` (ломает ARI / local WS).
2. **Cold Live + proxy** — основной безопасный путь. Сессия открывается только на реальный звонок и закрывается по его концу.
3. Emit refresh на adopt (AudioSocket `slin`) + drop digital silence на ulaw/pcm.

Чужой WAV (`ql_secretary_hello`) **откатили**. Silent-fallback «wait + cold reconnect» **запрещён**.

## Стоп-кран по деньгам (обязательно)

Idle OpenAI Live (warm pool + mic keepalive) **жжёт кредиты даже без звонков**. После инцидента (~$60 / 2 дня) действует жёсткий cost guard:

| Env | Default | Смысл |
|-----|---------|--------|
| `AVA_LIVE_WARM` | **`0`** | warm pool выключен |
| `AVA_LIVE_WARM_COST_OK` | **`0`** | второй ключ; без него warm **не стартует** |
| `AVA_LIVE_WARM_MAX_IDLE_S` | `45` | даже при явном включении idle-сессия убивается через N секунд |

Правила:

- Warm **запрещён** без **обоих** флагов `=1`.
- `install_prod.sh` всегда принудительно пишет `AVA_LIVE_WARM=0` и `AVA_LIVE_WARM_COST_OK=0`.
- `warm_start` / keepalive / supervisor отказывают без dual opt-in; при снятии флагов открытая сессия закрывается (`LIVE_WARM_KILLED_COST_GUARD`).
- Офлайн Live-пробы и тестовые звонки — только по явному OK владельца после пополнения баланса.

**Не включать warm «чтобы было быстрее» без лимита стоимости.**

## Офлайн-пробы (без звонка на телефон)

Только вручную, при `AVA_LIVE_WARM_COST_OK=1` и живом балансе:

```bash
docker cp console/scripts/probe_live_greeting_latency.py ai_engine:/tmp/
docker exec ai_engine python3 /tmp/probe_live_greeting_latency.py
```

Проверено 2026-10-22: kick→audio **1.18 / 0.85 / 1.42 s** (3/3 ≤1.5s) при warm+keepalive+proxy — затем warm **выключен**.

## Скрипты

| Script | Role |
|--------|------|
| `patch_live_warm_pool.py` | base warm pool (**default OFF**) |
| `harden_live_warm_pool.py` | health / tools / skip prewarm |
| `patch_live_openai_proxy.py` | `_live_ws_proxy()` |
| `patch_live_warm_keepalive.py` | session+mic keepalive, kick-only adopt |
| `harden_live_cost_guard.py` | **dual opt-in + idle expire + kill switch** |
| `probe_live_greeting_latency.py` | offline TTFA (no phone) |

Логи при нормальной работе: `LIVE_WARM_DISABLED_COST_GUARD` при старте engine.  
Запрещённые: долгие `LIVE_WARM_READY` без звонка, циклы `LIVE_WARM_CONNECT` / `LIVE_WARM_REFILL_FAILED`.
