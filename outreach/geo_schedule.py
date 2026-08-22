"""Recipient geo / timezone + B2B send-window helpers.

DaData party.address.data.timezone is like ``UTC+3``. We map those offsets
to IANA zones used across Russia, then schedule cold email only in local
business slots (default Tue–Thu preferred, Mon–Fri allowed;
10:00–11:30 and 14:30–16:30).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

# DaData / Russian civil-time offsets → IANA (best-effort, single zone per offset).
UTC_OFFSET_TO_IANA: dict[int, str] = {
    2: "Europe/Kaliningrad",
    3: "Europe/Moscow",
    4: "Europe/Samara",
    5: "Asia/Yekaterinburg",
    6: "Asia/Omsk",
    7: "Asia/Krasnoyarsk",
    8: "Asia/Irkutsk",
    9: "Asia/Yakutsk",
    10: "Asia/Vladivostok",
    11: "Asia/Magadan",
    12: "Asia/Kamchatka",
}

DEFAULT_IANA = "Europe/Moscow"
DEFAULT_SLOTS = ((time(10, 0), time(11, 30)), (time(14, 30), time(16, 30)))
# Python weekday: Mon=0 … Sun=6
DEFAULT_PREFERRED_WEEKDAYS = (1, 2, 3)  # Tue–Thu
DEFAULT_ALLOWED_WEEKDAYS = (0, 1, 2, 3, 4)  # Mon–Fri

_UTC_OFFSET_RE = re.compile(
    r"^\s*(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FioParts:
    surname: str = ""
    first: str = ""
    patronymic: str = ""

    @property
    def full(self) -> str:
        return " ".join(p for p in (self.surname, self.first, self.patronymic) if p)

    @property
    def greeting(self) -> str:
        """Имя + отчество for letter greeting; fallback to first or surname."""
        if self.first and self.patronymic:
            return f"{self.first} {self.patronymic}"
        return self.first or self.surname or ""


@dataclass(frozen=True)
class SlotWindow:
    start: time
    end: time


def parse_utc_offset_hours(raw: str | None) -> int | None:
    """Parse ``UTC+3`` / ``+05:00`` / ``GMT+7`` → integer hour offset."""
    s = (raw or "").strip()
    if not s:
        return None
    m = _UTC_OFFSET_RE.match(s)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    hours = int(m.group(2))
    minutes = int(m.group(3) or 0)
    if minutes:
        # Rare; round toward nearest hour for zone pick.
        if minutes >= 30:
            hours += 1
    return sign * hours


def iana_from_utc_offset(raw: str | None, *, default: str = DEFAULT_IANA) -> str:
    hours = parse_utc_offset_hours(raw)
    if hours is None:
        # Already an IANA name?
        cand = (raw or "").strip()
        if "/" in cand:
            try:
                ZoneInfo(cand)
                return cand
            except Exception:  # noqa: BLE001
                return default
        return default
    return UTC_OFFSET_TO_IANA.get(hours, default)


def zoneinfo_for(raw: str | None, *, default: str = DEFAULT_IANA) -> ZoneInfo:
    name = iana_from_utc_offset(raw, default=default)
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo(default)


def split_russian_fio(value: str | None) -> FioParts:
    """Split ``Фамилия Имя Отчество`` (also tolerates ``Имя Отчество``)."""
    raw = re.sub(r"\s+", " ", (value or "").replace(",", " ").strip())
    if not raw:
        return FioParts()
    parts = [p for p in raw.split(" ") if p]
    if len(parts) >= 3:
        return FioParts(surname=parts[0], first=parts[1], patronymic=parts[2])
    if len(parts) == 2:
        # Ambiguous: treat as Имя Отчество when no obvious surname marker,
        # else Фамилия Имя.
        a, b = parts
        if _looks_like_patronymic(b):
            return FioParts(first=a, patronymic=b)
        return FioParts(surname=a, first=b)
    return FioParts(first=parts[0])


def _looks_like_patronymic(token: str) -> bool:
    low = token.lower()
    return low.endswith(
        ("ич", "вна", "чна", "оглы", "кызы", "улы", "уулу")
    )


def extract_geo_from_dadata_raw(raw: dict[str, Any] | None) -> dict[str, str]:
    """Pull city / region / timezone from a DaData party suggestion or ``data`` blob."""
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(data, dict):
        return {}
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    addr_data = address.get("data") if isinstance(address.get("data"), dict) else {}
    city = str(
        addr_data.get("city")
        or addr_data.get("settlement")
        or addr_data.get("city_with_type")
        or ""
    ).strip()
    region = str(
        addr_data.get("region_with_type")
        or addr_data.get("region")
        or ""
    ).strip()
    tz_raw = str(addr_data.get("timezone") or "").strip()
    line = str(
        address.get("unrestricted_value") or address.get("value") or ""
    ).strip()
    out: dict[str, str] = {}
    if city:
        out["city"] = city
    if region:
        out["region"] = region
    if line:
        out["address_line"] = line
    if tz_raw:
        out["timezone_raw"] = tz_raw
        out["timezone"] = iana_from_utc_offset(tz_raw)
    return out


def extract_geo_from_bitrix_company(raw: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    city = str(
        raw.get("ADDRESS_CITY")
        or raw.get("REG_ADDRESS_CITY")
        or ""
    ).strip()
    region = str(
        raw.get("ADDRESS_PROVINCE")
        or raw.get("REG_ADDRESS_PROVINCE")
        or raw.get("ADDRESS_REGION")
        or ""
    ).strip()
    line = str(
        raw.get("ADDRESS_LEGAL")
        or raw.get("REG_ADDRESS")
        or raw.get("ADDRESS")
        or ""
    ).strip()
    out: dict[str, str] = {}
    if city:
        out["city"] = city
    if region:
        out["region"] = region
    if line:
        out["address_line"] = line
    return out


def parse_slots(spec: str | None) -> tuple[SlotWindow, ...]:
    """Parse ``10:00-11:30,14:30-16:30`` into slot windows."""
    raw = (spec or "").strip()
    if not raw:
        return tuple(SlotWindow(a, b) for a, b in DEFAULT_SLOTS)
    out: list[SlotWindow] = []
    for part in raw.split(","):
        part = part.strip()
        if not part or "-" not in part:
            continue
        a, b = part.split("-", 1)
        try:
            sh, sm = [int(x) for x in a.strip().split(":")[:2]]
            eh, em = [int(x) for x in b.strip().split(":")[:2]]
            start, end = time(sh, sm), time(eh, em)
            if start < end:
                out.append(SlotWindow(start, end))
        except Exception:  # noqa: BLE001
            continue
    return tuple(out) if out else tuple(SlotWindow(a, b) for a, b in DEFAULT_SLOTS)


def parse_weekdays(spec: str | None, *, default: Iterable[int]) -> tuple[int, ...]:
    raw = (spec or "").strip()
    if not raw:
        return tuple(default)
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            d = int(part)
        except ValueError:
            continue
        if 0 <= d <= 6:
            out.append(d)
    return tuple(out) if out else tuple(default)


def _cfg(settings: Any, key: str, default: str = "") -> str:
    if settings is None:
        return default
    try:
        if callable(settings) and not isinstance(settings, type):
            # settings_get(key, default) style
            try:
                return str(settings(key, default) or default)
            except TypeError:
                return str(settings(key) or default)
        if hasattr(settings, "get"):
            return str(settings.get(key, default) or default)
    except Exception:  # noqa: BLE001
        pass
    if isinstance(settings, dict):
        return str(settings.get(key, default) or default)
    return default


def _cfg_bool(settings: Any, key: str, default: bool = True) -> bool:
    raw = _cfg(settings, key, "true" if default else "false").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def schedule_config(settings: Any = None) -> dict[str, Any]:
    return {
        "enabled": _cfg_bool(settings, "SCHEDULE_LOCAL_WINDOWS", True),
        "slots": parse_slots(_cfg(settings, "SCHEDULE_SLOTS", "")),
        "preferred_weekdays": parse_weekdays(
            _cfg(settings, "SCHEDULE_PREFERRED_WEEKDAYS", "1,2,3"),
            default=DEFAULT_PREFERRED_WEEKDAYS,
        ),
        "allowed_weekdays": parse_weekdays(
            _cfg(settings, "SCHEDULE_ALLOWED_WEEKDAYS", "0,1,2,3,4"),
            default=DEFAULT_ALLOWED_WEEKDAYS,
        ),
        "default_timezone": iana_from_utc_offset(
            _cfg(settings, "SCHEDULE_DEFAULT_TIMEZONE", DEFAULT_IANA)
            or DEFAULT_IANA
        ),
        "prefer_tue_thu": _cfg_bool(settings, "SCHEDULE_PREFER_TUE_THU", True),
    }


def local_now(tz_name: str | None, *, default: str = DEFAULT_IANA) -> datetime:
    return datetime.now(zoneinfo_for(tz_name, default=default))


def in_send_window(
    local_dt: datetime,
    *,
    settings: Any = None,
    require_preferred_day: bool = False,
) -> bool:
    """True if ``local_dt`` falls into an allowed B2B slot."""
    cfg = schedule_config(settings)
    if not cfg["enabled"]:
        return True
    wd = local_dt.weekday()
    allowed = cfg["allowed_weekdays"]
    preferred = cfg["preferred_weekdays"]
    if wd not in allowed:
        return False
    if require_preferred_day and cfg["prefer_tue_thu"] and wd not in preferred:
        return False
    t = local_dt.time().replace(second=0, microsecond=0)
    for slot in cfg["slots"]:
        if slot.start <= t < slot.end:
            return True
    return False


def window_rank(
    local_dt: datetime,
    *,
    settings: Any = None,
) -> float:
    """Higher = better candidate right now (preferred day, earlier in slot, east TZ)."""
    if not in_send_window(local_dt, settings=settings):
        return -1.0
    cfg = schedule_config(settings)
    score = 0.0
    if local_dt.weekday() in cfg["preferred_weekdays"]:
        score += 100.0
    else:
        score += 40.0  # Mon/Fri still ok
    t = local_dt.time().replace(second=0, microsecond=0)
    # Prefer earlier minutes inside the active slot
    for slot in cfg["slots"]:
        if slot.start <= t < slot.end:
            elapsed = (t.hour * 60 + t.minute) - (slot.start.hour * 60 + slot.start.minute)
            score += max(0.0, 30.0 - elapsed / 2.0)
            break
    # East-first: larger UTC offset → slightly higher (their morning comes first)
    utcoff = local_dt.utcoffset() or timedelta(0)
    score += utcoff.total_seconds() / 3600.0
    return score


def next_send_datetime(
    after_utc: datetime,
    tz_name: str | None,
    *,
    settings: Any = None,
    prefer_preferred_days: bool = True,
    limit_days: int = 21,
) -> datetime:
    """Next UTC instant when local B2B window opens (snapped to slot start)."""
    cfg = schedule_config(settings)
    tz = zoneinfo_for(tz_name, default=cfg["default_timezone"])
    if after_utc.tzinfo is None:
        after_utc = after_utc.replace(tzinfo=timezone.utc)
    local = after_utc.astimezone(tz)
    preferred = set(cfg["preferred_weekdays"])
    allowed = set(cfg["allowed_weekdays"])
    day_sets: list[set[int]] = []
    if prefer_preferred_days and cfg["prefer_tue_thu"]:
        day_sets.append(preferred)
    day_sets.append(allowed)

    for day_set in day_sets:
        cur_date = local.date()
        for _ in range(max(1, limit_days)):
            if cur_date.weekday() in day_set:
                for slot in cfg["slots"]:
                    candidate = datetime.combine(cur_date, slot.start, tzinfo=tz)
                    if candidate >= local:
                        return candidate.astimezone(timezone.utc)
            cur_date = cur_date + timedelta(days=1)
    # Fallback: tomorrow 10:00 local
    fallback = datetime.combine(
        local.date() + timedelta(days=1), time(10, 0), tzinfo=tz
    )
    return fallback.astimezone(timezone.utc)


def snap_followup_utc(
    anchor_utc: datetime,
    *,
    delay_days: int,
    tz_name: str | None,
    settings: Any = None,
    now_utc: datetime | None = None,
) -> datetime:
    """Absolute chain: first-letter date + delay_days, then snap to next local slot."""
    if anchor_utc.tzinfo is None:
        anchor_utc = anchor_utc.replace(tzinfo=timezone.utc)
    target = anchor_utc + timedelta(days=max(0, int(delay_days)))
    now = now_utc or datetime.now(timezone.utc)
    if target < now:
        target = now
    return next_send_datetime(target, tz_name, settings=settings)


def any_russian_window_open(
    now_utc: datetime | None = None,
    *,
    settings: Any = None,
) -> bool:
    """Broad runner gate: True if at least one RU offset is currently in a slot."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    for iana in UTC_OFFSET_TO_IANA.values():
        local = now.astimezone(ZoneInfo(iana))
        if in_send_window(local, settings=settings):
            return True
    return False


def window_status(
    tz_name: str | None,
    *,
    settings: Any = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Operator-facing status: in window now / next local slot.

    Returns keys: in_window, label, next_slot_at (UTC ISO), next_slot_local,
    timezone (resolved IANA).
    """
    cfg = schedule_config(settings)
    resolved = iana_from_utc_offset(tz_name or "") or cfg["default_timezone"]
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(zoneinfo_for(resolved))

    if not cfg["enabled"]:
        return {
            "in_window": True,
            "label": "окна выкл.",
            "next_slot_at": None,
            "next_slot_local": None,
            "timezone": resolved,
        }

    if in_send_window(local, settings=settings):
        return {
            "in_window": True,
            "label": "сейчас",
            "next_slot_at": now.replace(microsecond=0).isoformat(),
            "next_slot_local": local.strftime("%a %H:%M"),
            "timezone": resolved,
        }

    nxt = next_send_datetime(now, resolved, settings=settings)
    nxt_local = nxt.astimezone(zoneinfo_for(resolved))
    # Compact RU-friendly: «вт 10:00» / «завтра 14:30»
    wd = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")[nxt_local.weekday()]
    if nxt_local.date() == local.date():
        when = f"сегодня {nxt_local.strftime('%H:%M')}"
    elif nxt_local.date() == local.date() + timedelta(days=1):
        when = f"завтра {nxt_local.strftime('%H:%M')}"
    else:
        when = f"{wd} {nxt_local.strftime('%H:%M')}"
    return {
        "in_window": False,
        "label": when,
        "next_slot_at": nxt.replace(microsecond=0).isoformat(),
        "next_slot_local": nxt_local.strftime("%Y-%m-%d %H:%M"),
        "timezone": resolved,
    }
