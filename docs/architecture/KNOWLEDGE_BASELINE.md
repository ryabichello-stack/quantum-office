# Current Knowledge — baseline snapshot (pre–Second Brain)

Date: 2026-07-23  
Purpose: зафиксировать состояние до миграции в Second Brain.  
See: [ADR-0001](./ADR-0001-second-brain.md), [Roadmap](./SECOND_BRAIN_ROADMAP.md).

## Runtime

| | |
|--|--|
| Service | `ava-knowledge` |
| Port | `8017` |
| Prod path | `/opt/ava-knowledge` |
| Live MD | `/root/ava/config/knowledge/quantum_labs.md` |
| Git copy | `knowledge/content/quantum_labs.md` (~54015 bytes, 117 headings) |
| Topics | `knowledge/content/index.yaml` (19 ids) |
| Search | alias + keyword section score |
| Voice | mailer `:8000` → proxy → `:8017` |
| Text | `AVA_KNOWLEDGE_BASE` → `:8017` |

## Strengths to keep

- Already shared by voice + text  
- Stable response contract `ok/topic/text/chars`  
- Topic ids used by LLM tools (`tariffs`, `sbp`, `npd`, …)  
- Mailer local fallback if knowledge down  

## Critical gaps vs Second Brain

- No `visibility` / ACL  
- No document types / frontmatter  
- No entity graph  
- No vector / hybrid search  
- No indexer pipeline  
- No MCP / principal-aware retrieve  
- Dual SoT drift risk (`/root/ava` vs git)  

## Non-negotiables for any change

1. Do not delete existing MD/docx-derived content  
2. Do not break `:8000/api/knowledge/query` or text-bot tools  
3. ACL filter before LLM context  
4. Markdown remains Source of Truth  
