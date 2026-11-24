# Реестр изменений агентов (Cursor ↔ Codex)

**Полный боевой журнал** живёт на проде: `/opt/delno/docs/AGENT_CHANGE_REGISTER.md` (Cloud4Box).  
Перед правками телефонии/Asterisk/Mango — читать его там (или свежий sync). Сюда в git — краткие якоря + ссылки на RCA.

Секреты сюда не писать.

---

## 2026-11-24 ~23:40 Europe/Moscow — Cursor: RCA + фикс «номер недоступен» (QL Mango / C4B)

- **Симптом:** городской `+79699665899` → «номер недоступен» / «никого нет в сети»; внут. **12** (Бот Гарик) отвечал.
- **Хост:** Cloud4Box `161.104.89.123` (Москва). Beget `5.35.86.62` мёртв — не прод.
- **Причины:** (1) 23.11 намеренно гасили QL SIP; (2) legacy `[mango-registration]` с невалидным `enabled=no`; (3) узкий UFW SIP; (4) не было `identify` Mango→`delno-quantum-labs`; (5) схема DID / красный «!» в Mango UI.
- **Сделано на проде:** одна `delno-quantum-labs-reg`; UFW `81.88.80.0/20`; `[mango-identify]`; `local_net`; SSH через `POLYHUB_SSH_KEY`.
- **Полный RCA:** [`TELEPHONY_RCA_2026-11-24_MANGO_UNAVAILABLE.md`](TELEPHONY_RCA_2026-11-24_MANGO_UNAVAILABLE.md)
- **Не делать:** `enabled=no` на `type=registration`; второй REGISTER того же `garik`; Beget как прод.
