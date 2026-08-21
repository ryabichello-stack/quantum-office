# Knowledge Vault — transitional freeze (office repo)

**ADR-0001:** Accepted with required security amendments.

- `legacy/` — frozen snapshot of current corpus (do not delete)
- `_meta/` — Phase 0 taxonomy / principals / ACL stubs

**Canonical Vault** after Phase 1 lives in the private repository **`quantum-brain`**.  
This tree must not become the long-term home for contracts/client materials.

Runtime agents still read `knowledge/content/` (+ prod `/root/ava/...`) via `ava-knowledge :8017`.  
Voice/text switch to Second Brain requires a **separate approval**.
