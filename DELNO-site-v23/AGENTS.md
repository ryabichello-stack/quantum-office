# AGENTS.md — DELNO

Read `/docs/00_MASTER_SPEC.md` before making product or architecture decisions.

## Repository boundaries
- `delno-platform`: primary repository, read/write.
- `quantum-office`: reference only. Do not modify or commit changes there unless explicitly instructed.

## Core rules
1. DELNO is a multi-tenant SaaS.
2. Every tenant-owned entity must be tenant-scoped.
3. LLMs must never choose or supply arbitrary tenant IDs.
4. Tenant context is derived by backend authentication/session context.
5. Communication channels use adapters behind a unified communication model.
6. AI agents act only through backend tools/APIs.
7. Critical writes require confirmation and audit.
8. Prefer modular monolith over premature microservices.
9. Do not build future roadmap modules unless current milestone requires them.
10. Keep model/provider abstractions replaceable.
11. Update `/docs/12_DECISIONS.md` and `/docs/13_CHANGELOG.md` for material decisions.

## Current milestone
Phase 1: finish the DELNO selling website and ensure a new visitor understands the product within 5–10 seconds.

Do not start a large CRM, marketplace, ERP, or bank platform as part of Phase 1.
