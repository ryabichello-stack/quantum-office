#!/usr/bin/env bash
# One-shot dedupe for Second Brain: remove vault twins + deprecate FAQ monolith copies.
set -euo pipefail
ROOT="${1:-/opt/ava-knowledge}"
cd "$ROOT"

echo "==> remove duplicate vault files"
rm -f vault/quantum-brain/lombards/part-b-playbook.md
rm -f vault/quantum-brain/products/quantum-payouts-profile.md
rm -f vault/quantum-brain/tools/imported/*-readme.md

echo "==> refresh tool imports (deep docs only)"
bash scripts/import_office_tool_docs.sh

echo "==> ingest vault (deprecates removed vault:* docs)"
./venv/bin/python -m brain_platform ingest --sources vault

echo "==> deprecate faq docs from quantum_labs.md (covered by vault SoT)"
./venv/bin/python - <<'PY'
from brain_platform.db.factory import get_brain_repo, reset_repo_singleton
reset_repo_singleton()
repo = get_brain_repo()
cur = repo.conn.execute(
    """UPDATE documents SET status='deprecated'
       WHERE tenant_id=? AND status='active' AND type='faq'
         AND (source LIKE '%quantum_labs.md%' OR source LIKE '%legacy_faq%' OR source LIKE '%faq:%')
    """,
    ("quantum-labs",),
)
repo.conn.commit()
print({"deprecated_faq": cur.rowcount})
# dual-write / sync counts
try:
    from brain_platform.db.migrate_sqlite_to_pg import sync_sqlite_to_postgres
    # prefer CLI sync-pg path if available via subprocess later
except Exception:
    pass
stats = repo.conn.execute(
    """SELECT status, type, COUNT(*) c FROM documents
       WHERE tenant_id=? GROUP BY status, type ORDER BY status, type""",
    ("quantum-labs",),
).fetchall()
for r in stats:
    print(dict(r))
PY

echo "==> sync-pg"
./venv/bin/python -m brain_platform sync-pg || true
echo "done"
