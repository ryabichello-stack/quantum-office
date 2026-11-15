"""Extensible catalog of office instruments.

Hermes must read this registry (via hermes.setup_status / hermes.capabilities),
not a frozen list inside the prompt. A future channel is one register_instrument()
call: it shows up in the checklist, the «сейчас или позже» offer, and stitch hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Instrument:
    id: str
    title: str
    hint: str
    optional: bool = False
    order: int = 0
    group: str = "office"  # knowledge | channel | office
    connect_tool: str = ""
    # In-call / messenger actions this instrument unlocks.
    actions: tuple[str, ...] = ()
    # Other instrument ids that become useful together.
    stitches_with: tuple[str, ...] = ()
    stitch_ru: dict[str, str] = field(default_factory=dict)
    plain_offer: str = ""


def _offer(title: str) -> str:
    return f"«{title}» можно подключить сейчас или позже."


_BUILTIN: tuple[Instrument, ...] = (
    Instrument(
        id="kb",
        title="О компании",
        hint="Расскажите о бизнесе своими словами, пришлите сайт или файл",
        order=10,
        group="knowledge",
        connect_tool="office.build_kb_draft",
        actions=("get_company_knowledge",),
        plain_offer="Сначала коротко о компании — без этого секретарь не знает, что отвечать.",
    ),
    Instrument(
        id="phone",
        title="Телефон",
        hint="Подключим номер, чтобы секретарь отвечал на звонки",
        order=20,
        group="channel",
        connect_tool="phones.provision",
        actions=("hangup_call",),
        stitches_with=("kb", "calendar", "mail", "conference"),
        stitch_ru={
            "kb": "Телефон и база знаний: секретарь отвечает на звонок фактами о компании.",
            "calendar": "Телефон и календарь: на звонке можно проверить свободное время и записать встречу.",
            "mail": "Телефон и почта: после звонка клиенту уходит письмо с временем встречи.",
            "conference": "Телефон и видеовстречи: на звонке можно создать ссылку на созвон.",
        },
        plain_offer=_offer("Телефон"),
    ),
    Instrument(
        id="telephony_script",
        title="Сценарий секретаря",
        hint="Соберём, что говорить клиенту, поставим голос и подключим действия",
        order=30,
        group="knowledge",
        connect_tool="telephony.script_propose",
        actions=("get_company_knowledge",),
        stitches_with=("phone", "kb"),
        stitch_ru={
            "phone": "Сценарий и телефон: секретарь отвечает по сценарию, а не пустой фразой.",
            "kb": "Сценарий собирается из того, что уже есть в базе знаний.",
        },
        plain_offer="Сценарий секретаря собирается из базы знаний — до пробного звонка.",
    ),
    Instrument(
        id="telegram",
        title="Telegram",
        hint="Бот или вход по QR — как удобнее. Можно сейчас или позже",
        optional=True,
        order=40,
        group="channel",
        connect_tool="credentials.open_form",
        actions=("meeting.book",),
        stitches_with=("calendar", "mail", "conference", "kb"),
        stitch_ru={
            "calendar": "Telegram и календарь: в переписке можно записать встречу так же, как по телефону.",
            "mail": "Telegram и почта: из чата можно отправить приглашение на почту.",
            "conference": "Telegram и видеовстречи: в чат можно прислать ссылку на созвон.",
            "kb": "Telegram и база знаний: бот отвечает фактами о компании.",
        },
        plain_offer=_offer("Telegram"),
    ),
    Instrument(
        id="max",
        title="MAX",
        hint="Бот или QR. Можно сейчас или позже",
        optional=True,
        order=50,
        group="channel",
        connect_tool="credentials.open_form",
        actions=("meeting.book",),
        stitches_with=("calendar", "mail", "conference", "kb"),
        stitch_ru={
            "calendar": "MAX и календарь: в переписке можно записать встречу.",
            "mail": "MAX и почта: из чата можно отправить приглашение.",
            "conference": "MAX и видеовстречи: в чат можно прислать ссылку на созвон.",
            "kb": "MAX и база знаний: бот отвечает фактами о компании.",
        },
        plain_offer=_offer("MAX"),
    ),
    Instrument(
        id="files",
        title="Файлы",
        hint="Диск, откуда брать презентации и документы. Можно позже",
        optional=True,
        order=60,
        group="office",
        connect_tool="credentials.open_form",
        stitches_with=("mail",),
        stitch_ru={
            "mail": "Файлы и почта: презентацию с диска можно приложить к письму клиенту.",
        },
        plain_offer=_offer("Файлы"),
    ),
    Instrument(
        id="calendar",
        title="Календарь",
        hint="Чтобы видеть свободное время и записывать встречи",
        order=70,
        group="office",
        connect_tool="office.connector_set",
        actions=("check_calendar", "create_calendar_event", "suggest_other_time"),
        stitches_with=("phone", "mail", "conference", "telegram", "max"),
        stitch_ru={
            "phone": "Календарь и телефон: секретарь на звонке смотрит свободное время и записывает встречу.",
            "mail": "Календарь и почта: приглашение со временем уходит клиенту на почту.",
            "conference": "Календарь и видеовстречи: к встрече добавляется ссылка на созвон.",
            "telegram": "Календарь и Telegram: записать встречу можно и из чата.",
            "max": "Календарь и MAX: записать встречу можно и из чата.",
        },
        plain_offer=_offer("Календарь"),
    ),
    Instrument(
        id="mail",
        title="Почта",
        hint="Чтобы отправлять приглашения и презентации",
        order=80,
        group="office",
        connect_tool="office.connector_set",
        actions=("send_email", "send_welcome_email"),
        stitches_with=("phone", "calendar", "conference", "telegram", "max"),
        stitch_ru={
            "phone": "Почта и телефон: после звонка клиенту уходит письмо.",
            "calendar": "Почта и календарь: в письме будет время встречи.",
            "conference": "Почта и видеовстречи: в письме будет ссылка на созвон.",
            "telegram": "Почта и Telegram: из чата можно отправить письмо.",
            "max": "Почта и MAX: из чата можно отправить письмо.",
        },
        plain_offer=_offer("Почту"),
    ),
    Instrument(
        id="conference",
        title="Видеовстречи",
        hint="Чтобы создавать ссылку на созвон",
        order=90,
        group="office",
        connect_tool="office.connector_set",
        actions=("create_conference",),
        stitches_with=("phone", "calendar", "mail", "telegram", "max"),
        stitch_ru={
            "phone": "Видеовстречи и телефон: на звонке можно создать ссылку на созвон.",
            "calendar": "Видеовстречи и календарь: ссылка сохраняется вместе со встречей.",
            "mail": "Видеовстречи и почта: ссылка уходит клиенту в письме.",
            "telegram": "Видеовстречи и Telegram: ссылку можно прислать в чат.",
            "max": "Видеовстречи и MAX: ссылку можно прислать в чат.",
        },
        plain_offer=_offer("Видеовстречи"),
    ),
    Instrument(
        id="outreach",
        title="Рассылка",
        hint="Необязательно: письма по базе контактов",
        optional=True,
        order=100,
        group="office",
        connect_tool="office.connector_set",
        stitches_with=("mail",),
        stitch_ru={
            "mail": "Рассылка использует уже подключённую почту.",
        },
        plain_offer=_offer("Рассылку"),
    ),
)

_EXTRA: list[Instrument] = []


def register_instrument(item: Instrument) -> None:
    """Add a platform instrument. Idempotent by id. Does not remove builtins."""
    if any(x.id == item.id for x in all_instruments()):
        return
    _EXTRA.append(item)


def unregister_instrument(instrument_id: str) -> None:
    """Test helper — only removes instruments added via register_instrument."""
    _EXTRA[:] = [x for x in _EXTRA if x.id != instrument_id]


def all_instruments() -> list[Instrument]:
    return sorted([*_BUILTIN, *_EXTRA], key=lambda x: (x.order, x.id))


def get_instrument(instrument_id: str) -> Instrument | None:
    for item in all_instruments():
        if item.id == instrument_id:
            return item
    return None


def setup_steps() -> list[dict[str, str]]:
    """Shape hermes_ops has always returned: id, title, hint."""
    return [
        {
            "id": item.id,
            "title": item.title,
            "hint": item.hint,
            "optional": item.optional,
        }
        for item in all_instruments()
    ]


def inventory_from_checks(
    checks: dict[str, Any] | None,
    *,
    deferred: set[str] | None = None,
) -> dict[str, Any]:
    """Platform catalog vs what THIS company has connected."""
    checks = checks or {}
    deferred = deferred or set()
    connected_ids: set[str] = set()
    platform: list[dict[str, Any]] = []
    connected: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for item in all_instruments():
        row = checks.get(item.id) if isinstance(checks.get(item.id), dict) else {}
        ok = bool(row.get("ok"))
        entry = {
            "id": item.id,
            "title": item.title,
            "hint": item.hint,
            "optional": item.optional,
            "group": item.group,
            "connect_tool": item.connect_tool,
            "actions": list(item.actions),
            "connected": ok,
            "deferred": item.id in deferred,
            "offer_ru": item.plain_offer or _offer(item.title),
        }
        platform.append(entry)
        if ok:
            connected_ids.add(item.id)
            connected.append(entry)
        else:
            missing.append(entry)
    return {
        "platform": platform,
        "connected": connected,
        "missing": missing,
        "deferred": sorted(deferred),
        "stitches": stitch_offers(connected_ids),
        "note_ru": (
            "Список инструментов приходит из реестра платформы. "
            "Не держите его в тексте промпта: новые каналы появляются здесь сами."
        ),
    }


def stitch_offers(connected_ids: set[str]) -> list[dict[str, str]]:
    """Plain sentences for pairs that are both already connected."""
    seen: set[tuple[str, str]] = set()
    offers: list[dict[str, str]] = []
    for item in all_instruments():
        if item.id not in connected_ids:
            continue
        for other in item.stitches_with:
            if other not in connected_ids:
                continue
            pair = tuple(sorted((item.id, other)))
            if pair in seen:
                continue
            text = item.stitch_ru.get(other) or ""
            if not text:
                continue
            seen.add(pair)
            offers.append({"a": pair[0], "b": pair[1], "text": text})
    return offers


def stitches_for_new(connected_ids: set[str], just_connected: str) -> list[dict[str, str]]:
    """What the newly connected instrument can do with what is already on."""
    item = get_instrument(just_connected)
    if item is None:
        return []
    out: list[dict[str, str]] = []
    ids = set(connected_ids) | {just_connected}
    for other in item.stitches_with:
        if other == just_connected or other not in ids:
            continue
        text = item.stitch_ru.get(other)
        if text:
            out.append({"with": other, "text": text})
    # Also sentences written on the other side.
    for other_item in all_instruments():
        if other_item.id == just_connected or other_item.id not in ids:
            continue
        if just_connected in other_item.stitches_with:
            text = other_item.stitch_ru.get(just_connected)
            if text and text not in {x["text"] for x in out}:
                out.append({"with": other_item.id, "text": text})
    return out
