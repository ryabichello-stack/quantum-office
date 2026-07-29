"""Behavior scenarios for ava-text-bot (personal secretary + office modes)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

SCENARIOS_PATH = Path(
    os.getenv("SECRETARY_SCENARIOS_PATH", str(Path(__file__).resolve().parent / "scenarios.yaml"))
)


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    prompt: str
    aliases: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    for_roles: list[str] = field(default_factory=lambda: ["owner", "guest"])


@dataclass
class ScenarioBundle:
    default_owner: str = "secretary"
    default_guest: str = "office"
    owners: set[str] = field(default_factory=set)
    scenarios: dict[str, Scenario] = field(default_factory=dict)


_bundle: ScenarioBundle | None = None


def _parse_owner_ids() -> set[str]:
    raw = os.getenv("SECRETARY_OWNER_IDS", os.getenv("OWNER_TELEGRAM_IDS", "")).strip()
    out: set[str] = set()
    for part in re.split(r"[\s,;]+", raw):
        if part:
            out.add(part.strip())
    return out


def load_scenarios(path: Optional[Path] = None) -> ScenarioBundle:
    global _bundle
    p = Path(path or SCENARIOS_PATH)
    data: dict[str, Any] = {}
    if p.is_file():
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.error("scenarios.yaml parse error: %s", exc)
            data = {}
    owners = {str(x).strip() for x in (data.get("owners") or []) if str(x).strip()}
    owners |= _parse_owner_ids()

    scenarios: dict[str, Scenario] = {}
    for sid, item in (data.get("scenarios") or {}).items():
        if not isinstance(item, dict):
            continue
        scenarios[str(sid)] = Scenario(
            id=str(sid),
            title=str(item.get("title") or sid),
            description=str(item.get("description") or ""),
            prompt=str(item.get("prompt") or "").strip(),
            aliases=[str(a).strip().lower() for a in (item.get("aliases") or []) if str(a).strip()],
            triggers=[str(t).strip().lower() for t in (item.get("triggers") or []) if str(t).strip()],
            for_roles=[str(r).strip().lower() for r in (item.get("for") or ["owner", "guest"])],
        )

    # Minimal fallback if yaml missing
    if not scenarios:
        scenarios["secretary"] = Scenario(
            id="secretary",
            title="Личный секретарь",
            description="Универсальный режим",
            prompt="Ты личный ИИ-секретарь владельца. Делай задачи через инструменты.",
            for_roles=["owner"],
        )
        scenarios["office"] = Scenario(
            id="office",
            title="Офисный секретарь",
            description="Для внешних",
            prompt="Ты офисный секретарь Quantum Labs. На «вы», по делу.",
            for_roles=["guest"],
        )

    bundle = ScenarioBundle(
        default_owner=str(data.get("default_owner") or "secretary"),
        default_guest=str(data.get("default_guest") or "office"),
        owners=owners,
        scenarios=scenarios,
    )
    _bundle = bundle
    logger.info(
        "scenarios loaded count=%s owners=%s path=%s",
        len(scenarios),
        len(owners),
        p,
    )
    return bundle


def get_bundle() -> ScenarioBundle:
    return _bundle or load_scenarios()


def is_owner(
    user_id: str,
    channel: str = "",
    *,
    chat_type: str | None = None,
) -> bool:
    """Full secretary privileges only for allowlisted owners.

    Telegram: private DM only (groups/supergroups/channels → guest).
    """
    uid = str(user_id or "").strip()
    if not uid:
        return False

    ch = (channel or "").strip().lower()
    ctype = (chat_type or "").strip().lower()

    # Groups / channels never get owner full-access, even if the speaker is the owner.
    if ch == "telegram" and ctype and ctype != "private":
        return False

    owners = get_bundle().owners
    if uid in owners:
        return True

    # Fail-open only when no owners configured yet (bootstrap). Prefer explicit IDs in prod.
    if not owners and ch == "telegram" and (not ctype or ctype == "private"):
        return os.getenv("SECRETARY_TELEGRAM_DEFAULT_OWNER", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    return False


def role_for(
    user_id: str,
    channel: str = "",
    *,
    chat_type: str | None = None,
) -> str:
    return "owner" if is_owner(user_id, channel, chat_type=chat_type) else "guest"


def list_scenarios(role: str) -> list[Scenario]:
    role = (role or "guest").lower()
    return [s for s in get_bundle().scenarios.values() if role in s.for_roles or not s.for_roles]


def get_scenario(scenario_id: str) -> Optional[Scenario]:
    return get_bundle().scenarios.get((scenario_id or "").strip().lower())


def resolve_by_alias(name: str, role: str) -> Optional[Scenario]:
    key = (name or "").strip().lower()
    if not key:
        return None
    for s in list_scenarios(role):
        if key == s.id or key in s.aliases:
            return s
    return None


def default_scenario(role: str) -> Scenario:
    b = get_bundle()
    sid = b.default_owner if role == "owner" else b.default_guest
    return get_scenario(sid) or next(iter(b.scenarios.values()))


_OUTBOUND_CALL_RE = re.compile(
    r"(?is)(?:позвони|позвонить|набери|набрать|обзвон|dial)\b"
    r".{0,120}?(?:\+?\d[\d\-\s()]{8,}|\b\d{10,11}\b)"
)
_OUTBOUND_CALL_SOFT_RE = re.compile(
    r"(?is)\b(?:позвони|позвонить|набери|набрать|перезвони|перезвонить|обзвон)\b"
)


def looks_like_outbound_request(text: str) -> bool:
    """True when the user is asking to place/manage an outbound call now."""
    raw = (text or "").strip()
    if not raw:
        return False
    if _OUTBOUND_CALL_RE.search(raw):
        return True
    low = raw.lower()
    # Soft: call verb + task words even without a clear phone yet
    if _OUTBOUND_CALL_SOFT_RE.search(low) and any(
        k in low
        for k in (
            "свидан",
            "приглас",
            "от имени",
            "скрипт",
            "greeting",
            "сценари",
            "обзвон",
            "исходящ",
        )
    ):
        return True
    return False


def detect_scenario(text: str, role: str) -> Scenario:
    """Pick best matching scenario by trigger keywords; else default."""
    # Hard priority: explicit call requests must not fall into memory/secretary meta.
    if role == "owner" and looks_like_outbound_request(text):
        outbound = get_scenario("outbound")
        if outbound and "owner" in (outbound.for_roles or ["owner"]):
            return outbound

    low = (text or "").lower()
    best: Optional[Scenario] = None
    best_score = 0
    for s in list_scenarios(role):
        score = 0
        for tr in s.triggers:
            if tr and tr in low:
                score += 2 + min(len(tr), 12) // 4
        if score > best_score:
            best_score = score
            best = s
    if best and best_score > 0:
        return best
    return default_scenario(role)


_CMD_RE = re.compile(
    r"^\s*/?(?:режим|scenario|mode|сценарий)\s+([a-zA-Zа-яА-ЯёЁ0-9_\- ]+)\s*$",
    re.I,
)
_LIST_RE = re.compile(
    r"^\s*/?(?:режимы|scenarios|modes|сценарии|help scenarios)\s*$",
    re.I,
)


def parse_scenario_command(text: str, role: str) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (action, payload).
    action: list | set | clear | None
    """
    raw = (text or "").strip()
    if _LIST_RE.match(raw) or raw.lower() in ("/режимы", "/scenarios", "/modes"):
        return "list", None
    if raw.lower() in ("/режим сброс", "/режим auto", "/режим авто", "/scenario clear", "/mode auto"):
        return "clear", None
    m = _CMD_RE.match(raw)
    if m:
        name = m.group(1).strip()
        if name.lower() in ("сброс", "auto", "авто", "clear", "default"):
            return "clear", None
        sc = resolve_by_alias(name, role)
        if sc:
            return "set", sc.id
        return "unknown", name
    return None, None


def format_scenarios_help(role: str, current_id: str, sticky: bool) -> str:
    lines = [
        "Режимы секретаря:",
        f"Сейчас: {current_id}" + (" (закреплён)" if sticky else " (авто)"),
        "",
    ]
    for s in list_scenarios(role):
        lines.append(f"• {s.id} — {s.title}: {s.description}")
    lines.append("")
    lines.append("Команды: /режимы | /режим calendar | /режим сброс")
    return "\n".join(lines)


def scenario_overlay(scenario: Scenario, *, role: str, sticky: bool) -> str:
    sticky_note = "Режим закреплён командой /режим." if sticky else "Режим выбран автоматически по запросу."
    return (
        f"----------------------------------------\n"
        f"СЦЕНАРИЙ: {scenario.id} — {scenario.title}\n"
        f"РОЛЬ СОБЕСЕДНИКА: {role}\n"
        f"{sticky_note}\n"
        f"----------------------------------------\n"
        f"{scenario.prompt.strip()}\n"
    )
