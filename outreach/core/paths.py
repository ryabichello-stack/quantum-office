"""Shared paths and constants for outreach modules."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-outreach/data"))
OUTBOX_DB = DATA_DIR / "outbox.db"
SETTINGS_DB = DATA_DIR / "settings.db"
# Shared module DB (tracking, suppression, send events) — separate file so
# modules can evolve without fighting outbox schema migrations.
MODULES_DB = DATA_DIR / "modules.db"
