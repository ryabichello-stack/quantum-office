# Operational memory — product mission for Second Brain

See ADR-0001 §2.1 and §4.16–4.18.

## Goal

Answer **any work or technical question** from one searchable corpus that grows over time.

## Must cover

1. **Contacts** — emails, phones, titles, companies, project roles  
2. **Correspondence** — inbound + outbound mail threads and topics  
3. **Projects / discussions** — decisions, open questions, participants  
4. **Server files** — office documents and attachments on allowed roots  
5. **FAQ / product ops** — existing `quantum_labs.md` layer  

## Growth

Every new email, project discussion, and allowlisted server file → safety scan → ACL classify → index (FTS + vector + graph). Idempotent ingest; no silent drop.

## Agents

Cursor and office agents query the same indexes via MCP/REST **within ACL**.  
`voice-public` never receives mail/PII. Full mailbox access requires an authorized principal.

## Security

Operational data defaults to `company` / `restricted`, never auto-`public`.  
PII flagged; credentials → quarantine. In-query ACL on every backend.
