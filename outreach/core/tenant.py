"""Active outreach tenant — one instance per deployment, any industry via config."""

from __future__ import annotations

import os

# Greenfield default: generic themes. Quantum Labs prod: OUTREACH_TENANT_ID=quantum-labs
DEFAULT_TENANT_ID = (os.getenv("OUTREACH_TENANT_ID") or "default").strip() or "default"
