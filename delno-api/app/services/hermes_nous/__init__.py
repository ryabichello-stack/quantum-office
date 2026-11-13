"""Nous Hermes Agent integration (Stage 0+).

See docs/HERMES_ORIGINAL_INTEGRATION_PLAN.md and docs/hermes-nous/.
"""

from app.services.hermes_nous.flags import FLAG_HERMES_NOUS_RUNTIME, is_hermes_nous_enabled
from app.services.hermes_nous.provision import ensure_tenant_hermes_home, tenant_runtime_record
from app.services.hermes_nous.run_tokens import (
    IssueRunTokenResult,
    issue_run_token,
    revoke_run_token,
    verify_run_token,
)

__all__ = [
    "FLAG_HERMES_NOUS_RUNTIME",
    "IssueRunTokenResult",
    "ensure_tenant_hermes_home",
    "is_hermes_nous_enabled",
    "issue_run_token",
    "revoke_run_token",
    "tenant_runtime_record",
    "verify_run_token",
]
