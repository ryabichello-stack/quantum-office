"""Worker-visible Hermes profile homes (real HERMES_HOME tree, not API-only skeleton).

Hermes v0.23+ multiplex layout (one gateway per worker hosts many companies):

  HERMES_PROFILES_ROOT/workers/<worker_id>/           ← worker HERMES_HOME
    config.yaml                                      ← multiplex root
    .env
    profiles/<profile_id>/                           ← per-company home
      config.yaml / SOUL.md / .env / memories / …

Legacy flat ``HERMES_PROFILES_ROOT/<profile_id>/`` is migrated into the worker
tree on ensure. API may also keep a backup under TENANT_FILES_ROOT/.../hermes.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.config import get_settings

_TEMPLATES = Path(__file__).resolve().parents[3] / "hermes_runtime" / "templates" / "home"
_ROOT_TEMPLATES = Path(__file__).resolve().parents[3] / "hermes_runtime" / "templates" / "worker_root"


def profiles_root() -> Path:
    override = (os.environ.get("HERMES_PROFILES_ROOT") or "").strip()
    if override:
        return Path(override)
    return Path(get_settings().hermes_profiles_root)


def _writable_profiles_root() -> Path:
    """Prefer HERMES_PROFILES_ROOT; if unwritable (CI/unit), fall back under tenant_files_root."""
    primary = profiles_root()
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except OSError:
        fallback = Path(get_settings().tenant_files_root) / "_hermes_profiles"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def safe_profile_id(profile_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in (profile_id or "unknown"))


def worker_multiplex_root(worker_id: str) -> Path:
    wid = safe_profile_id(worker_id or "pool")
    return _writable_profiles_root() / "workers" / wid


def live_profile_path(profile_id: str, *, worker_id: str | None = None) -> Path:
    """Path Hermes serves for this company profile.

    When worker_id is known → ``workers/<worker>/profiles/<id>``.
    Otherwise → staging under ``unassigned/profiles/<id>`` until placement.
    """
    safe = safe_profile_id(profile_id)
    if worker_id:
        return worker_multiplex_root(worker_id) / "profiles" / safe
    return _writable_profiles_root() / "unassigned" / "profiles" / safe


def legacy_flat_profile_path(profile_id: str) -> Path:
    """Pre-multiplex path: HERMES_PROFILES_ROOT/<profile_id>."""
    return profiles_root() / safe_profile_id(profile_id)


def ensure_worker_multiplex_root(worker_id: str, *, api_server_key: str | None = None) -> Path:
    """Create the Hermes multiplex root this worker process boots from."""
    root = worker_multiplex_root(worker_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "profiles").mkdir(exist_ok=True)
    for sub in ("memories", "skills", "cron", "sessions"):
        (root / sub).mkdir(exist_ok=True)

    cfg = root / "config.yaml"
    if cfg.exists():
        bumped = _bump_stock_model(cfg.read_text(encoding="utf-8"))
        if bumped != cfg.read_text(encoding="utf-8"):
            cfg.write_text(bumped, encoding="utf-8")
    if not cfg.exists():
        src = _ROOT_TEMPLATES / "config.yaml"
        if src.is_file():
            shutil.copy2(src, cfg)
        else:
            cfg.write_text(
                "gateway:\n  multiplex_profiles: true\n  auto_multiplex_migration: true\n",
                encoding="utf-8",
            )

    # Root .env: API key for default listener; named profiles get their own copy.
    env_path = root / ".env"
    key = (api_server_key or "").strip()
    if key and (not env_path.exists() or "API_SERVER_KEY=" not in env_path.read_text(encoding="utf-8")):
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        lines = [ln for ln in existing.splitlines() if not ln.startswith("API_SERVER_KEY=")]
        lines.append(f"API_SERVER_KEY={key}")
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return root


_LLM_MARKER = "# delno-llm-key"
_STOCK_MODEL = "default: gpt-4.1-mini"
_CURRENT_MODEL = "default: gpt-6-luna"


def _bump_stock_model(text: str) -> str:
    """Move untouched stock configs to the prod Hermes default. Leave custom models."""
    if _STOCK_MODEL in text and _CURRENT_MODEL not in text:
        return text.replace(_STOCK_MODEL, _CURRENT_MODEL)
    return text


def _apply_llm_env(lines: list[str], *, openai_api_key: str | None, llm_key_source: str) -> list[str]:
    """One managed key per profile: its BYOK, or the platform key for platform companies."""
    cleaned: list[str] = []
    skip_key = False
    for ln in lines:
        if ln.startswith("DELNO_LLM_KEY_SOURCE="):
            continue
        if ln.strip() == _LLM_MARKER:
            skip_key = True
            continue
        if skip_key and ln.startswith("OPENAI_API_KEY="):
            skip_key = False
            continue
        skip_key = False
        cleaned.append(ln)
    source = llm_key_source if llm_key_source in {"byok", "platform", "missing"} else "platform"
    cleaned.append(f"DELNO_LLM_KEY_SOURCE={source}")
    key = (openai_api_key or "").strip()
    if source in ("byok", "platform") and key:
        cleaned.append(_LLM_MARKER)
        cleaned.append(f"OPENAI_API_KEY={key}")
    return cleaned


def _seed_profile_files(
    home: Path,
    *,
    mcp_url: str | None,
    api_server_key: str | None,
    delno_mcp_key: str | None = None,
    openai_api_key: str | None = None,
    llm_key_source: str = "platform",
) -> None:
    for sub in ("memories", "skills", "cron", "sessions"):
        (home / sub).mkdir(exist_ok=True)

    if _TEMPLATES.is_dir():
        for name in ("config.yaml", "SOUL.md", "AGENTS.md"):
            src = _TEMPLATES / name
            dst = home / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)

    config_path = home / "config.yaml"
    if config_path.is_file():
        text = _bump_stock_model(config_path.read_text(encoding="utf-8"))
        # Named profiles are served by the worker multiplex root — not standalone daemons.
        if "multiplex_profiles: false" in text:
            text = text.replace("multiplex_profiles: false", "multiplex_profiles: true")
        if mcp_url and ("delno_office:" not in text or "mcp_servers: {}" in text):
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

    # Profile-scoped secrets (Hermes multiplex get_secret). Never share across companies.
    env_path = home / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = [
        ln
        for ln in existing.splitlines()
        if not ln.startswith("API_SERVER_KEY=") and not ln.startswith("DELNO_MCP_KEY=")
    ]
    key = (api_server_key or "").strip()
    if key:
        # /p/<profile>/ auth requires a profile-scoped API_SERVER_KEY (≥16 chars).
        lines.append(f"API_SERVER_KEY={key}")
    mcp_key = (delno_mcp_key or "").strip()
    if mcp_key:
        # Per-tenant legacy MCP key for Hermes MCP client connect at boot.
        # Run tokens / X-Delno-Run-Id still preferred for tool ACL.
        lines.append(f"DELNO_MCP_KEY={mcp_key}")
    lines = _apply_llm_env(lines, openai_api_key=openai_api_key, llm_key_source=llm_key_source)
    if lines:
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _migrate_legacy_flat(profile_id: str, dest: Path) -> None:
    legacy = legacy_flat_profile_path(profile_id)
    if not legacy.is_dir():
        return
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(legacy), str(dest))
    except OSError:
        # Cross-device or busy: copy then leave legacy (worker bind will prefer dest).
        shutil.copytree(legacy, dest, dirs_exist_ok=True)


def ensure_live_profile_home(
    profile_id: str,
    *,
    worker_id: str | None = None,
    mcp_url: str | None = None,
    api_server_key: str | None = None,
    delno_mcp_key: str | None = None,
    openai_api_key: str | None = None,
    llm_key_source: str = "platform",
) -> Path:
    """Create/seed the directory Hermes workers mount. Idempotent."""
    safe = safe_profile_id(profile_id)
    if worker_id:
        ensure_worker_multiplex_root(worker_id, api_server_key=api_server_key)
    home = live_profile_path(profile_id, worker_id=worker_id)
    if not home.exists():
        # Prefer migrating legacy flat home or unassigned staging.
        _migrate_legacy_flat(profile_id, home)
        staging = _writable_profiles_root() / "unassigned" / "profiles" / safe
        if not home.exists() and staging.is_dir() and staging.resolve() != home.resolve():
            home.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(staging), str(home))
            except OSError:
                shutil.copytree(staging, home, dirs_exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    _seed_profile_files(
        home,
        mcp_url=mcp_url,
        api_server_key=api_server_key,
        delno_mcp_key=delno_mcp_key,
        openai_api_key=openai_api_key,
        llm_key_source=llm_key_source,
    )
    marker = home / ".delno_profile_id"
    marker.write_text(profile_id + "\n", encoding="utf-8")
    return home


def worker_bind_hint(profile_id: str, *, worker_id: str | None = None) -> dict[str, str]:
    """Env the worker container should use (multiplex root, not a single company home)."""
    wid = worker_id or "pool"
    root = str(worker_multiplex_root(wid))
    path = str(live_profile_path(profile_id, worker_id=wid))
    return {
        "HERMES_WORKER_ID": wid,
        "HERMES_HOME": root,
        "HERMES_PROFILE_ID": profile_id,
        "state_location": path,
        "api_path_prefix": f"/p/{safe_profile_id(profile_id)}",
    }
