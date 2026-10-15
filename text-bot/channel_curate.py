"""Owner curates news: forward post to channel-bot → rewrite → auto-publish.

Uses TELEGRAM_CHANNEL_BOT_TOKEN (channel admin bot).
Posts as *new* channel messages (sendPhoto/sendVideo/sendMessage) — not forwardMessage,
so they look native. Signature with channel link appended to every post.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("ava-text-bot.channel_curate")

DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))
STATE_PATH = DATA_DIR / "channel_curate.json"

REWRITE_SYSTEM = (
    "Ты редактор авторского Telegram-канала.\n"
    "Перепиши исходный пост на русском: сохрани факты и смысл, слегка освежи формулировки,\n"
    "убери чужие призывы подписаться / рекламу / водяные ссылки на чужие каналы.\n"
    "Не выдумывай фактов. Не добавляй эмодзи сверх меры (0–2 уместны).\n"
    "Не добавляй подпись канала и ссылки — их приклеит система.\n"
    "Верни ТОЛЬКО текст поста без кавычек и без пояснений."
)


def enabled() -> bool:
    flag = (os.getenv("TELEGRAM_CURATE_ENABLED") or "true").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return bool((os.getenv("TELEGRAM_CHANNEL_BOT_TOKEN") or "").strip())


def bot_token() -> str:
    return (os.getenv("TELEGRAM_CHANNEL_BOT_TOKEN") or "").strip()


def owner_ids() -> set[str]:
    raw = (
        os.getenv("TELEGRAM_CURATE_OWNER_IDS")
        or os.getenv("SECRETARY_OWNER_IDS")
        or ""
    )
    return {x.strip() for x in raw.split(",") if x.strip()}


def default_channel_id() -> str:
    return (os.getenv("TELEGRAM_CURATE_CHANNEL_ID") or "").strip() or "@epoch_z"


def channel_link(channel_id: str | None = None) -> str:
    ch = (channel_id or default_channel_id() or "").strip()
    if ch.startswith("@"):
        return f"https://t.me/{ch[1:]}"
    custom = (os.getenv("TELEGRAM_CURATE_CHANNEL_LINK") or "").strip()
    return custom


def html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def signature(channel_id: str | None = None) -> str:
    """HTML footer: megaphone + underlined clickable channel name."""
    raw = (os.getenv("TELEGRAM_CURATE_SIGNATURE") or "").strip()
    if raw:
        return raw.replace("\\n", "\n")
    link = channel_link(channel_id) or "https://t.me/epoch_z"
    name = (os.getenv("TELEGRAM_CURATE_CHANNEL_TITLE") or "Заметки эпохи").strip()
    return (
        "\n\n—\n"
        f'📢 <a href="{html_escape(link)}"><u>{html_escape(name)}</u></a>'
    )


def confirm_required() -> bool:
    # Default: auto-publish without confirmation (owner asked for instant rewrite+post)
    flag = (os.getenv("TELEGRAM_CURATE_CONFIRM") or "false").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _load_state() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        return {"channel_id": default_channel_id(), "pending": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"channel_id": default_channel_id(), "pending": {}}
        data.setdefault("channel_id", default_channel_id())
        data.setdefault("pending", {})
        return data
    except Exception:
        logger.exception("curate state load failed")
        return {"channel_id": default_channel_id(), "pending": {}}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def target_channel() -> str:
    state = _load_state()
    return str(state.get("channel_id") or default_channel_id() or "").strip()


def set_target_channel(channel_id: str) -> str:
    ch = (channel_id or "").strip()
    if (
        ch
        and not ch.startswith("@")
        and not ch.startswith("-")
        and not ch.lstrip("-").isdigit()
    ):
        ch = f"@{ch}"
    state = _load_state()
    state["channel_id"] = ch
    _save_state(state)
    return ch


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "channel_id": target_channel() or None,
        "channel_link": channel_link(target_channel()),
        "confirm": confirm_required(),
        "owners": len(owner_ids()),
        "auto_publish": not confirm_required(),
    }


def extract_post(message: dict[str, Any]) -> dict[str, Any]:
    """Text/caption + media file_ids. Never use forwardMessage — re-send as new posts."""
    text = str(message.get("text") or message.get("caption") or "").strip()
    photo_file_id = None
    video_file_id = None
    animation_file_id = None
    document_file_id = None
    media_kind = None

    photos = message.get("photo") or []
    if isinstance(photos, list) and photos:
        last = photos[-1] if isinstance(photos[-1], dict) else None
        if last and last.get("file_id"):
            photo_file_id = last.get("file_id")
            media_kind = "photo"

    video = message.get("video") or {}
    if isinstance(video, dict) and video.get("file_id"):
        video_file_id = video.get("file_id")
        media_kind = "video"

    animation = message.get("animation") or {}
    if isinstance(animation, dict) and animation.get("file_id"):
        animation_file_id = animation.get("file_id")
        media_kind = "animation"

    # video sent as document (common)
    document = message.get("document") or {}
    if isinstance(document, dict) and document.get("file_id"):
        mime = str(document.get("mime_type") or "")
        if mime.startswith("video/") and not video_file_id:
            video_file_id = document.get("file_id")
            media_kind = "video"
        elif not media_kind:
            document_file_id = document.get("file_id")
            media_kind = "document"

    forward_from = None
    if message.get("forward_from_chat"):
        fc = message["forward_from_chat"] or {}
        forward_from = fc.get("title") or fc.get("username") or str(fc.get("id") or "")
    elif message.get("forward_from"):
        fu = message["forward_from"] or {}
        forward_from = (
            " ".join(x for x in [fu.get("first_name"), fu.get("last_name")] if x).strip()
            or fu.get("username")
        )
    elif message.get("forward_sender_name"):
        forward_from = str(message.get("forward_sender_name"))

    return {
        "text": text,
        "photo_file_id": photo_file_id,
        "video_file_id": video_file_id,
        "animation_file_id": animation_file_id,
        "document_file_id": document_file_id,
        "media_kind": media_kind,
        "forward_from": forward_from,
        "is_forward": bool(
            message.get("forward_date")
            or message.get("forward_from")
            or message.get("forward_from_chat")
            or message.get("forward_sender_name")
        ),
    }


def rewrite_text(source: str, *, openai_api_key: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=openai_api_key)
    src = (source or "").strip()
    if not src:
        return ""
    kwargs: dict = {
        "model": model or "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": src[:6000]},
        ],
    }
    # gpt-5* / some mini models reject custom temperature
    model_l = (model or "").lower()
    if not model_l.startswith("gpt-5"):
        kwargs["temperature"] = 0.7
    resp = client.chat.completions.create(**kwargs)
    out = (resp.choices[0].message.content or "").strip()
    out = re.sub(r"^```(?:\w+)?\n|\n```$", "", out).strip()
    if (out.startswith("«") and out.endswith("»")) or (
        len(out) >= 2 and out[0] == '"' and out[-1] == '"'
    ):
        out = out[1:-1].strip()
    return out or src


def apply_signature(body: str, *, channel_id: str | None = None) -> str:
    """Backward-compatible alias → HTML post with clickable footer."""
    return compose_post_html(body, channel_id=channel_id)


TgPostFn = Callable[..., dict[str, Any]]


def handle_owner_message(
    message: dict[str, Any],
    *,
    tg_post: TgPostFn,
    openai_api_key: str,
    model: str,
) -> None:
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = str(from_user.get("id") or "")
    if chat_id is None:
        return
    if str(chat.get("type") or "") != "private":
        return
    owners = owner_ids()
    if owners and user_id not in owners:
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Этот бот принимает посты только от владельца канала.",
            },
            token=bot_token(),
            timeout=20.0,
        )
        return

    text_cmd = str(message.get("text") or "").strip()
    low = text_cmd.lower()

    if low in {"/start", "/help", "помощь", "старт"}:
        ch = target_channel() or "(не задан — /channel @username)"
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "Лента «Заметки эпохи»\n\n"
                    "Перешлите сюда пост (текст / фото / видео) — "
                    "сразу перепишу и опубликую в канал как обычное сообщение "
                    "(не репост), с подписью и ссылкой.\n\n"
                    f"Канал: {ch}\n"
                    f"Ссылка: {channel_link(ch) or '—'}\n"
                    "Сменить канал: /channel @epoch_z\n"
                    "Статус: /status"
                ),
            },
            token=bot_token(),
            timeout=20.0,
        )
        return

    if low.startswith("/channel"):
        parts = text_cmd.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            tg_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"Сейчас: {target_channel() or '—'}\nПример: /channel @epoch_z",
                },
                token=bot_token(),
                timeout=20.0,
            )
            return
        ch = set_target_channel(parts[1].strip())
        try:
            info = tg_post("getChat", {"chat_id": ch}, token=bot_token(), timeout=20.0)
            title = ((info.get("result") or {}).get("title")) if info.get("ok") else None
            tg_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"Ок, канал: {ch}" + (f" («{title}»)" if title else ""),
                },
                token=bot_token(),
                timeout=20.0,
            )
        except Exception as exc:
            tg_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": (
                        f"Сохранил {ch}, но getChat не удался: {exc}. "
                        "Добавьте бота админом с правом Post messages."
                    ),
                },
                token=bot_token(),
                timeout=20.0,
            )
        return

    if low in {"/status", "статус"}:
        st = status()
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    f"enabled={st['enabled']}\n"
                    f"channel={st['channel_id']}\n"
                    f"link={st['channel_link']}\n"
                    f"auto_publish={st['auto_publish']}\n"
                    f"owners={st['owners']}"
                ),
            },
            token=bot_token(),
            timeout=20.0,
        )
        return

    post = extract_post(message)
    source = post["text"]
    has_media = bool(
        post.get("photo_file_id")
        or post.get("video_file_id")
        or post.get("animation_file_id")
        or post.get("document_file_id")
    )
    if not source and not has_media:
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Пришлите текст или перешлите пост с текстом / фото / видео.",
            },
            token=bot_token(),
            timeout=20.0,
        )
        return

    if source and not openai_api_key:
        tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": "OPENAI_API_KEY не настроен на сервере."},
            token=bot_token(),
            timeout=20.0,
        )
        return

    channel = target_channel()
    if not channel:
        tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": "Сначала укажите канал: /channel @epoch_z"},
            token=bot_token(),
            timeout=20.0,
        )
        return

    tg_post(
        "sendChatAction",
        {"chat_id": chat_id, "action": "typing"},
        token=bot_token(),
        timeout=10.0,
    )

    rewritten = ""
    if source:
        try:
            rewritten = rewrite_text(
                source, openai_api_key=openai_api_key, model=model
            )
        except Exception as exc:
            logger.exception("rewrite failed")
            tg_post(
                "sendMessage",
                {"chat_id": chat_id, "text": f"Не смог переписать: {exc}"},
                token=bot_token(),
                timeout=20.0,
            )
            return

    body = (rewritten or source or "").rstrip()
    final = apply_signature(body if body else " ", channel_id=channel)

    try:
        pub = _publish_native(
            tg_post,
            channel=channel,
            text=final,
            post=post,
        )
        mid = pub.get("message_id")
        kind = pub.get("kind") or "text"
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    f"Готово → {channel}"
                    + (f" #{mid}" if mid else "")
                    + f" ({kind})"
                ),
            },
            token=bot_token(),
            timeout=20.0,
        )
    except Exception as exc:
        logger.exception("publish failed")
        tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": f"Ошибка публикации: {exc}"},
            token=bot_token(),
            timeout=20.0,
        )


def _publish_native(
    tg_post: TgPostFn,
    *,
    channel: str,
    text: str,
    post: dict[str, Any],
) -> dict[str, Any]:
    """Publish as a fresh channel post (not forwardMessage / not 'переслано')."""
    caption_limit = 1024
    full = text or ""
    photo = post.get("photo_file_id")
    video = post.get("video_file_id")
    animation = post.get("animation_file_id")
    document = post.get("document_file_id")

    def _send_media(method: str, file_field: str, file_id: str, kind: str) -> dict[str, Any]:
        if len(full) <= caption_limit:
            raw = tg_post(
                method,
                {
                    "chat_id": channel,
                    file_field: file_id,
                    "caption": full,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                token=bot_token(),
                timeout=60.0,
            )
            if not raw.get("ok"):
                raise RuntimeError(raw.get("description") or str(raw))
            result = raw.get("result") or {}
            return {"message_id": result.get("message_id"), "kind": kind, "result": result}

        # Caption too long: media first, then text as follow-up (still native posts)
        raw = tg_post(
            method,
            {"chat_id": channel, file_field: file_id},
            token=bot_token(),
            timeout=60.0,
        )
        if not raw.get("ok"):
            raise RuntimeError(raw.get("description") or str(raw))
        mid = (raw.get("result") or {}).get("message_id")
        raw2 = tg_post(
            "sendMessage",
            {
                "chat_id": channel,
                "text": full[:4096],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            token=bot_token(),
            timeout=20.0,
        )
        if not raw2.get("ok"):
            raise RuntimeError(raw2.get("description") or str(raw2))
        return {
            "message_id": mid or (raw2.get("result") or {}).get("message_id"),
            "kind": f"{kind}+text",
            "result": raw2.get("result"),
        }

    if photo:
        return _send_media("sendPhoto", "photo", photo, "photo")
    if video:
        return _send_media("sendVideo", "video", video, "video")
    if animation:
        return _send_media("sendAnimation", "animation", animation, "animation")
    if document:
        return _send_media("sendDocument", "document", document, "document")

    raw = tg_post(
        "sendMessage",
        {
            "chat_id": channel,
            "text": full[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        token=bot_token(),
        timeout=20.0,
    )
    if not raw.get("ok"):
        raise RuntimeError(raw.get("description") or str(raw))
    result = raw.get("result") or {}
    return {"message_id": result.get("message_id"), "kind": "text", "result": result}


def handle_callback(callback: dict[str, Any], *, tg_post: TgPostFn) -> None:
    # Confirm flow disabled by default; ignore leftover buttons gracefully
    cq_id = callback.get("id")
    if cq_id:
        tg_post(
            "answerCallbackQuery",
            {
                "callback_query_id": cq_id,
                "text": "Автопубликация включена — просто перешлите пост.",
            },
            token=bot_token(),
            timeout=15.0,
        )


def handle_update(
    update: dict[str, Any],
    *,
    tg_post: TgPostFn,
    openai_api_key: str,
    model: str,
) -> bool:
    if not enabled():
        return False
    if "callback_query" in update:
        handle_callback(update["callback_query"] or {}, tg_post=tg_post)
        return True
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    handle_owner_message(
        message,
        tg_post=tg_post,
        openai_api_key=openai_api_key,
        model=model,
    )
    return True
