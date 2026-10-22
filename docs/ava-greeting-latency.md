# AVA outbound: тишина после ответа + обрыв «Алло»

## Симптом

После снятия трубки несколько секунд тишины (раньше 6–14s).

## Фикс (прод, проверено)

**Live warm pool** — idle Cedar-сессия готова до ответа; на answer только adopt + greeting kick.

Чужой WAV (`ql_secretary_hello`) **откатили**.

| Проверка | call_id | answer→first audio | warm |
|----------|---------|-------------------:|------|
| baseline | 1792682975.8 | ~9.3 s | cold |
| warm #1 | 1792684347.24 | **~1.77 s** | `LIVE_WARM_USED` |
| warm #2 | 1792684466.28 | **~0.90 s** | `LIVE_WARM_USED` |

Цель ≤1.5s: warm #2 в норме; #1 чуть выше из‑за TTS Live. Пользователь на #1: «задержка хорошая».

Скрипты: `patch_live_warm_pool.py`, `harden_live_warm_pool.py`. Env `AVA_LIVE_WARM=1`.

Логи успеха: `LIVE_WARM_READY` → `GREETING_PREWARM_SKIP_WARM` → `LIVE_WARM_USED` → first audio <1.5s.
