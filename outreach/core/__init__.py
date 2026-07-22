"""Core package."""

from .paths import DATA_DIR, MODULES_DB, OUTBOX_DB, SETTINGS_DB
from .registry import AppContext, ModuleRegistry

__all__ = [
    "AppContext",
    "DATA_DIR",
    "MODULES_DB",
    "ModuleRegistry",
    "OUTBOX_DB",
    "SETTINGS_DB",
]
