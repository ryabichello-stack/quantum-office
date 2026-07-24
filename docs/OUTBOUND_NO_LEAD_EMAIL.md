# Outbound post-call: no lead email

## Policy

| Direction | After call |
|-----------|------------|
| **Inbound** (`default`) | Email «Новый лид» + CRM fan-out (mailer `mailru_post_call`) |
| **Outbound** | **No** lead email. Transcripts in Console → **Звонки** (filter outbound) and text-bot tools |

## Mechanisms

1. `/root/ava/config/ai-agent.local.yaml` → `contexts.outbound.post_call_tools: []`
2. Console must not re-seed `mailru_post_call` on outbound scenario save
3. Mailer `_should_send_lead_email` skips when `context_name` / `call_direction` is outbound
4. Payload template includes `{context_name}` / `{call_direction}` for defense in depth

## UI

https://a.47z.ru/_quantum_console/ → tab Звонки → filter «исходящие» → click row for message table.
