# P4 — Каналы (owner vs frontline)

- Owner Hermes: кабинет + `/v1/hermes-nous` (этот PR).  
- Frontline: Telegram / MAX / widget / phone — трубы в tenant; читают KB **этого** tenant.  
- API stub: `GET /v1/hermes-nous/channels-map`.  
- Telephony: только Codex `trunk_id` routing — **не** переписывать из Hermes-веток.
