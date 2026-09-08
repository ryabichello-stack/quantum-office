"""Read/write platform secrets in the server .env file (platform admin only)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class SecretFieldDef:
    key: str
    label: str
    group: str
    group_title: str
    sensitive: bool = True
    hint: str = ""
    control: str = "text"  # text | password | select
    options_key: str | None = None  # chat_models | realtime_models | realtime_voices


SECRET_FIELDS: tuple[SecretFieldDef, ...] = (
    SecretFieldDef(
        "OPENAI_API_KEY",
        "OpenAI API Key",
        "openai",
        "OpenAI / голос",
        True,
        "Realtime WebRTC, TTS и оператор. Тот же ключ, что в телефонии AVA.",
        "password",
        None,
    ),
    SecretFieldDef(
        "OPENAI_MODEL",
        "OpenAI Chat Model",
        "openai",
        "OpenAI / голос",
        False,
        "Модель для текстового оператора и виджета",
        "select",
        "chat_models",
    ),
    SecretFieldDef(
        "OPENAI_REALTIME_MODEL",
        "Realtime Model",
        "openai",
        "OpenAI / голос",
        False,
        "Модель для голосового орба (WebRTC)",
        "select",
        "realtime_models",
    ),
    SecretFieldDef(
        "OPENAI_REALTIME_VOICE",
        "Realtime Voice",
        "openai",
        "OpenAI / голос",
        False,
        "Голос Realtime — cedar как в телефонии AVA",
        "select",
        "realtime_voices",
    ),
    SecretFieldDef(
        "JWT_SECRET",
        "JWT Secret",
        "security",
        "Безопасность",
        True,
        "Подпись токенов входа. После смены все сессии сбросятся.",
    ),
    SecretFieldDef(
        "TELEGRAM_BOT_TOKEN",
        "Telegram Bot Token",
        "integrations",
        "Интеграции",
        True,
        "Уведомления о лидах",
    ),
    SecretFieldDef(
        "TELEGRAM_CHAT_ID",
        "Telegram Chat ID",
        "integrations",
        "Интеграции",
        False,
    ),
    SecretFieldDef(
        "DADATA_API_KEY",
        "DaData API Key",
        "integrations",
        "Интеграции",
        True,
    ),
    SecretFieldDef(
        "DADATA_SECRET_KEY",
        "DaData Secret",
        "integrations",
        "Интеграции",
        True,
    ),
)

ALLOWED_KEYS = frozenset(field.key for field in SECRET_FIELDS)


def platform_env_path() -> Path:
    settings = get_settings()
    raw = (settings.platform_env_file or "").strip()
    if raw:
        return Path(raw)
    # Dev fallback next to repo api folder
    return Path(__file__).resolve().parents[2] / ".env"


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value[0] in "\"'":
        quote = value[0]
        if len(value) >= 2 and value.endswith(quote):
            inner = value[1:-1]
            return inner.replace(f"\\{quote}", quote).replace("\\\\", "\\")
    return value


def _format_value(value: str) -> str:
    if value == "":
        return ""
    if re.search(r'[\s#"$\\]', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def read_env_values() -> dict[str, str]:
    path = platform_env_path()
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_LINE.match(stripped)
        if match:
            values[match.group(1)] = _parse_value(match.group(2))
    return values


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def env_file_status() -> dict[str, object]:
    path = platform_env_path()
    exists = path.is_file()
    writable = os.access(path, os.W_OK) if exists else os.access(path.parent, os.W_OK)
    return {
        "path": str(path),
        "exists": exists,
        "writable": writable,
    }


def list_secret_fields() -> list[dict[str, object]]:
    values = read_env_values()
    groups: dict[str, dict[str, object]] = {}
    for field in SECRET_FIELDS:
        current = values.get(field.key, "")
        group = groups.setdefault(
            field.group,
            {"id": field.group, "title": field.group_title, "items": []},
        )
        item: dict[str, object] = {
            "key": field.key,
            "label": field.label,
            "hint": field.hint,
            "sensitive": field.sensitive,
            "control": field.control,
            "options_key": field.options_key,
            "configured": bool(current.strip()),
        }
        if field.sensitive and current.strip():
            item["preview"] = mask_secret(current)
        elif current.strip():
            item["preview"] = current
            item["value"] = current
        elif field.control == "select":
            item["value"] = ""
        group["items"].append(item)
    order = ["openai", "security", "integrations"]
    return [groups[g] for g in order if g in groups]


def update_env_values(updates: dict[str, str]) -> tuple[list[str], str | None]:
    """Apply updates to .env. Empty string clears a key. Returns (changed_keys, error)."""
    if not updates:
        return [], None

    unknown = [key for key in updates if key not in ALLOWED_KEYS]
    if unknown:
        return [], f"unknown_keys:{','.join(unknown)}"

    path = platform_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# DELNO platform secrets — managed via admin panel", ""]

    changed: list[str] = []
    for key, value in updates.items():
        formatted = _format_value(value)
        new_line = f"{key}={formatted}" if value != "" else f"{key}="
        replaced = False
        for index, line in enumerate(lines):
            if _ENV_LINE.match(line.strip()) and line.strip().split("=", 1)[0] == key:
                if line.strip() != new_line.strip():
                    changed.append(key)
                lines[index] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)
            changed.append(key)

    try:
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError:
        return [], "env_write_failed"

    for key in changed:
        if updates.get(key, "") != "":
            os.environ[key] = updates[key]
        elif key in os.environ:
            del os.environ[key]

    get_settings.cache_clear()
    return changed, None


def apply_runtime_env() -> None:
    """Load current .env values into process environment (after external edit)."""
    for key, value in read_env_values().items():
        if value:
            os.environ[key] = value
    get_settings.cache_clear()
