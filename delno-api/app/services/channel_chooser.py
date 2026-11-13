"""Telegram / MAX connect chooser — bot token vs QR (Telegram Web-style).

PRODUCT_LOOP: Hermes asks which path is convenient, explains pros/cons,
helps create a bot step-by-step, then opens vault form (never paste secrets in chat).
QR path uses channel_qr stubs until a live QR worker is on the bridge.
"""

from __future__ import annotations

from typing import Any, Literal

ChannelKind = Literal["telegram", "max"]

_BOT_PATH_MARKERS = (
    "через бота",
    "через бот",
    "токен бота",
    "бот токен",
    "bot token",
    "botfather",
    "access token",
    "вариантом бота",
    "вариант бота",
    "способ бота",
    "подключи бота",
    "подключить бота",
    "телеграм бот",
    "telegram bot",
    "тг бот",
    "tg bot",
    "макс бот",
    "max bot",
    "max_bot",
)

_QR_PATH_MARKERS = (
    "через qr",
    "через q.r",
    "qr-код",
    "qr код",
    "qr-кодом",
    "как веб",
    "как telegram web",
    "как доп",
    "дополнительн",
    "доп. устройств",
    "доп устройств",
    "session",
    "вариантом qr",
    "вариант qr",
)

_HELP_BOT_MARKERS = (
    "помоги создать бота",
    "помоги создать телеграм",
    "помоги создать telegram",
    "помоги создать max",
    "помоги создать макс",
    "как создать бота",
    "нет токена",
    "нет ключа",
    "нет бота",
    "создай бота",
    "создать бота",
    "создать телеграм бота",
    "создать telegram бота",
    "инструкц",
    "пошагов",
)


def detect_channel(message: str) -> ChannelKind | None:
    low = (message or "").lower()
    if any(m in low for m in ("telegram", "телеграм", "тг ", " tg", "tg ", "тг-")) or low.strip() in (
        "тг",
        "tg",
    ):
        return "telegram"
    if any(m in low for m in ("max_bot", "макс бот", "бот max", "бот макс", "мессенджер max", "мессенджер макс")):
        return "max"
    # Bare «макс» only with connect verbs — handled by caller context.
    if " max" in f" {low}" or low.startswith("max") or "макс" in low:
        if any(m in low for m in ("подключ", "настро", "канал", "бот", "qr", "токен")):
            return "max"
    return None


def wants_bot_path(message: str) -> bool:
    low = (message or "").lower()
    return any(m in low for m in _BOT_PATH_MARKERS)


def wants_qr_path(message: str) -> bool:
    low = (message or "").lower()
    return any(m in low for m in _QR_PATH_MARKERS)


def wants_bot_help(message: str) -> bool:
    low = (message or "").lower()
    return any(m in low for m in _HELP_BOT_MARKERS)


def wants_channel_connect_intent(message: str) -> ChannelKind | None:
    """Generic «подключи Telegram/MAX» — show chooser, not vault yet."""
    low = (message or "").lower()
    channel = detect_channel(message)
    if not channel:
        return None
    connectish = any(
        m in low
        for m in (
            "подключи",
            "подключить",
            "подключим",
            "настрой",
            "настроить",
            "подключение",
            "подключим канал",
            "давай telegram",
            "давай телеграм",
            "давай max",
            "давай макс",
        )
    )
    if not connectish and not wants_bot_path(message) and not wants_qr_path(message) and not wants_bot_help(
        message
    ):
        return None
    return channel


def explicit_bot_form_kind(message: str) -> str | None:
    """Only open vault when owner already chose the bot-token path (or asks for the form)."""
    low = (message or "").lower()
    channel = detect_channel(message)
    if not channel:
        return None
    kind = "telegram_bot" if channel == "telegram" else "max_bot"
    if "credentials.open_form" in low or "открой форму" in low or "пришли форму" in low:
        return kind
    if wants_bot_path(message) or wants_bot_help(message):
        return kind
    # Token paste hints without «подключи» already covered by open_form wording.
    if "botfather" in low or "access token" in low:
        return kind
    return None


def chooser_reply(channel: ChannelKind) -> dict[str, Any]:
    if channel == "telegram":
        title = "Telegram"
        bot_label = "бота @BotFather"
        qr_label = "QR как Telegram Web (доп. устройство)"
        reply = (
            "Подключим Telegram. Есть два способа — какой удобнее?\n\n"
            f"1) **Бот ({bot_label})** — офисный канал «от имени компании».\n"
            "   + Свой бренд, стабильные вебхуки, секретарь отвечает в боте.\n"
            "   − Нужно создать бота и вставить токен (помогу по шагам).\n\n"
            f"2) **{qr_label}** — как вход в Telegram Web с телефона.\n"
            "   + Быстро, без BotFather.\n"
            "   − Это сессия аккаунта, не branded-бот; для клиентов обычно хуже.\n\n"
            "Нажмите вариант ниже или напишите: «через бота» / «через QR» / "
            "«помоги создать бота»."
        )
        actions = [
            {"title": "Бот (токен)", "text": "подключи телеграм через бота"},
            {"title": "QR как веб", "text": "подключи телеграм через QR"},
            {"title": "Помоги создать бота", "text": "помоги создать телеграм бота"},
        ]
    else:
        title = "MAX"
        reply = (
            "Подключим MAX. Два способа — какой удобнее?\n\n"
            "1) **Бот (access token)** — канал «от имени компании» в MAX для бизнеса.\n"
            "   + Свой бренд, webhook, переписка в Диалогах.\n"
            "   − Нужен бот в кабинете MAX и токен (помогу по шагам).\n\n"
            "2) **QR / web-login** — как доп. устройство к аккаунту.\n"
            "   + Быстрее, если токена нет.\n"
            "   − Личная/рабочая сессия, не branded-бот; для клиентов обычно хуже.\n\n"
            "Нажмите вариант ниже или напишите: «через бота» / «через QR» / "
            "«помоги создать бота MAX»."
        )
        actions = [
            {"title": "Бот (токен)", "text": "подключи MAX через бота"},
            {"title": "QR / web", "text": "подключи MAX через QR"},
            {"title": "Помоги создать бота", "text": "помоги создать бота MAX"},
        ]
    return {
        "channel": channel,
        "title": title,
        "reply": reply,
        "suggested_actions": actions,
        "pending_channel_chooser": {"channel": channel, "modes": ["bot", "qr"]},
    }


def bot_help_reply(channel: ChannelKind) -> dict[str, Any]:
    if channel == "telegram":
        steps = (
            "Ок, сделаем бота вместе — токен в чат не пишите, только в форму.\n\n"
            "1. Откройте Telegram → найдите **@BotFather**.\n"
            "2. Отправьте `/newbot`.\n"
            "3. Придумайте имя (видно людям) и username (заканчивается на `bot`).\n"
            "4. BotFather пришлёт **HTTP API token** вида `123456:AAH…`.\n"
            "5. Вставьте токен в безопасную форму ниже → «Подключить Telegram».\n"
            "6. Я сам настрою webhook — вручную в Telegram ничего не нужно.\n\n"
            "Нет доступа к BotFather? Напишите «через QR» — другой способ."
        )
        form_kind = "telegram_bot"
        actions = [
            {"title": "У меня есть токен", "text": "открой форму telegram_bot"},
            {"title": "Лучше QR", "text": "подключи телеграм через QR"},
        ]
    else:
        steps = (
            "Ок, заведём бота MAX — токен только в форму, не в чат.\n\n"
            "1. Откройте кабинет **MAX для бизнеса**.\n"
            "2. Создайте / выберите бота компании и пройдите верификацию, если просят.\n"
            "3. В настройках бота скопируйте **access token**.\n"
            "4. Вставьте токен в безопасную форму ниже → «Подключить MAX».\n"
            "5. Webhook зарегистрирую сам.\n\n"
            "Нет кабинета MAX? Напишите «через QR» или попросите админа выдать токен."
        )
        form_kind = "max_bot"
        actions = [
            {"title": "У меня есть токен", "text": "открой форму max_bot"},
            {"title": "Лучше QR", "text": "подключи MAX через QR"},
        ]
    return {
        "channel": channel,
        "form_kind": form_kind,
        "reply": steps,
        "suggested_actions": actions,
    }


def bot_path_reply(channel: ChannelKind) -> dict[str, Any]:
    help_blob = bot_help_reply(channel)
    if channel == "telegram":
        head = (
            "Подключаем Telegram **через бота**. "
            "Токен только в форме. Если бота ещё нет — шаги ниже."
        )
    else:
        head = (
            "Подключаем MAX **через бота**. "
            "Access token только в форме. Если бота нет — шаги ниже."
        )
    # Reuse help body without the "Ок, сделаем" opener duplication.
    body = help_blob["reply"]
    if body.startswith("Ок,"):
        body = body.split("\n\n", 1)[-1]
    return {
        "channel": channel,
        "form_kind": help_blob["form_kind"],
        "reply": f"{head}\n\n{body}",
        "suggested_actions": help_blob["suggested_actions"],
    }


def qr_path_reply(channel: ChannelKind, *, qr_start: dict[str, Any] | None = None) -> dict[str, Any]:
    label = "Telegram" if channel == "telegram" else "MAX"
    started = bool(qr_start and qr_start.get("ok"))
    account_id = (qr_start or {}).get("account_id")
    base = (
        f"Вариант QR для {label}: как вход «доп. устройством» (похож на веб-клиент).\n\n"
        "Сейчас мост умеет **создать QR-сессию** и принять подтверждение; "
        "живая картинка QR на экране ещё доводится — если QR не появится за минуту, "
        "лучше перейти на бота (стабильнее для клиентов).\n"
    )
    if started:
        base += (
            f"\nСессия создана (`pending_qr`, id `{account_id}`). "
            "Когда QR-воркер отдаст картинку — отсканируйте с телефона. "
            "Или напишите «через бота»."
        )
    else:
        err = (qr_start or {}).get("error") or "unavailable"
        base += f"\nНе удалось стартовать QR ({err}). Предлагаю **бота** — открою форму."
    actions = [
        {
            "title": "Через бота",
            "text": (
                "подключи телеграм через бота" if channel == "telegram" else "подключи MAX через бота"
            ),
        },
        {
            "title": "Помоги создать бота",
            "text": (
                "помоги создать телеграм бота" if channel == "telegram" else "помоги создать бота MAX"
            ),
        },
    ]
    return {
        "channel": channel,
        "reply": base,
        "suggested_actions": actions,
        "qr_start": qr_start,
        "fallback_form_kind": None if started else ("telegram_bot" if channel == "telegram" else "max_bot"),
    }


def cancel_stale_pending_qr(db: Any, ctx: Any, channel: ChannelKind) -> int:
    """Drop abandoned pending_qr rows so health stops nagging."""
    from app.models.channel_account import ChannelAccount

    rows = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == channel,
            ChannelAccount.status == "pending_qr",
        )
        .all()
    )
    n = 0
    for row in rows:
        row.status = "cancelled"
        meta = dict(row.meta or {})
        meta["cancelled_reason"] = "chooser_or_bot_path"
        row.meta = meta
        n += 1
    if n:
        db.commit()
    return n
