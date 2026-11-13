"""Worker-visible Hermes profile homes (real HERMES_HOME, not API-only skeleton).

API may also write under TENANT_FILES_ROOT/.../hermes for backups, but the
path Hermes must read is HERMES_PROFILES_ROOT/<profile_id> — the same volume
mounted into worker containers.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.config import get_settings

_TEMPLATES = Path(__file__).resolve().parents[3] / "hermes_runtime" / "templates" / "home"


def profiles_root() -> Path:
    override = (os.environ.get("HERMES_PROFILES_ROOT") or "").strip()
    if override:
        return Path(override)
    return Path(get_settings().hermes_profiles_root)


def live_profile_path(profile_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in (profile_id or "unknown"))
    return profiles_root() / safe


def ensure_live_profile_home(profile_id: str, *, mcp_url: str | None = None) -> Path:
    """Create/seed the directory Hermes workers mount. Idempotent."""
    home = live_profile_path(profile_id)
    home.mkdir(parents=True, exist_ok=True)
    for sub in ("memories", "skills", "cron", "sessions"):
        (home / sub).mkdir(exist_ok=True)

    if _TEMPLATES.is_dir():
        for name in ("config.yaml", "SOUL.md", "AGENTS.md"):
            src = _TEMPLATES / name
            dst = home / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)

    # Stamp MCP URL if provided (internal docker DNS — never public api.dlno.ru).
    config_path = home / "config.yaml"
    if mcp_url and config_path.is_file():
        text = config_path.read_text(encoding="utf-8")
        if "delno_office:" not in text or "mcp_servers: {}" in text:
            block = (
                "mcp_servers:\n"
                "  delno_office:\n"
                f'    url: "{mcp_url}"\n'
                "    headers:\n"
                '      Authorization: "Bearer ${DELNO_MCP_KEY}"\n'
                '      # Prefer run binding when runtime injects it:\n'
                '      # X-Delno-Run-Id: "${DELNO_RUN_ID}"\n'
            )
            if "mcp_servers: {}" in text:
                text = text.replace("mcp_servers: {}", block.rstrip())
            elif "delno_office:" not in text:
                text = text.rstrip() + "\n\n" + block
            config_path.write_text(text, encoding="utf-8")

    marker = home / ".delno_profile_id"
    marker.write_text(profile_id + "\n", encoding="utf-8")
    return home


def worker_bind_hint(profile_id: str) -> dict[str, str]:
    """Env the worker should use so HERMES_HOME points at this profile."""
    path = str(live_profile_path(profile_id))
    return {
        "HERMES_PROFILE_ID": profile_id,
        "HERMES_HOME": path,
        "state_location": path,
    }
