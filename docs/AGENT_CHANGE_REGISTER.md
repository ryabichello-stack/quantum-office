# Реестр изменений агентов (Cursor ↔ Codex)

Читать **до** правок на прод-телефонии / Asterisk / Mango. Писать **после** значимых действий.

Прод-копия (если есть): `/opt/delno/docs/AGENT_CHANGE_REGISTER.md` на Cloud4Box.

Секреты сюда не писать.

---

## 2026-11-24 ~23:40 Europe/Moscow — Cursor: RCA + фикс «номер недоступен» (QL Mango / C4B)

- **Симптом:** городской `+79699665899` → «номер недоступен» / «никого нет в сети»; внут. **12** (Бот Гарик) отвечал.
- **Хост:** Cloud4Box `161.104.89.123` (Москва). Beget `5.35.86.62` мёртв — не прод.
- **Причины:** (1) 23.11 намеренно гасили QL SIP (`/root/backup-telephony-ql-disable-20261123T173739Z`); (2) legacy `[mango-registration]` с невалидным `enabled=no` (Asterisk 20 не знает опцию); (3) UFW SIP только `81.88.86/88` — узко для IP Mango; (4) не было `identify` Mango→`delno-quantum-labs`; (5) схема DID в Mango / красный «!» у бота — внешний звонок без INVITE при живом SIP.
- **Сделано на проде:** закомментирован legacy reg; UFW ALLOW `81.88.80.0/20` на 5060/5061 перед DENY; `[mango-identify]`; `local_net` на transport; `delno-quantum-labs-reg` стабильно Registered. SSH: env `POLYHUB_SSH_KEY`.
- **Док для агентов:** [`docs/TELEPHONY_RCA_2026-11-24_MANGO_UNAVAILABLE.md`](TELEPHONY_RCA_2026-11-24_MANGO_UNAVAILABLE.md)
- **Не делать:** снова `enabled=no` на `type=registration`; второй REGISTER того же `garik`; считать Beget продом.
