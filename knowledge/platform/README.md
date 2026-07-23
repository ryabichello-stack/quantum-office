# knowledge/platform — Second Brain platform code

Lives in **quantum-office** (application repo).  
Canonical Markdown Vault lives in separate private repo **quantum-brain**.

## Phase 0 (current)

- Pydantic security schemas (`schemas/`)
- ACL / principals / cache / audit helpers (`security/`)
- Secret/PII scan stubs (`security/safety.py`)
- Contract + negative-security tests (`tests/`)

**Does not** change production `ava-knowledge` (:8017) keyword runtime.  
Voice/text must **not** be switched to this platform without separate approval.

## Run tests

```bash
cd /path/to/quantum-office
PYTHONPATH=. pytest knowledge/platform/tests -q
```

## ADR

See `docs/architecture/ADR-0001-second-brain.md` (Accepted with required security amendments).
