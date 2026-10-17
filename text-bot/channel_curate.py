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
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("ava-text-bot.channel_curate")

DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))
STATE_PATH = DATA_DIR / "channel_curate.json"

_MEDIA_GROUP_LOCK = threading.Lock()
_MEDIA_GROUPS: dict[str, dict[str, Any]] = {}
_MEDIA_GROUP_TIMERS: dict[str, threading.Timer] = {}
MEDIA_GROUP_WAIT_S = float(os.getenv("TELEGRAM_CURATE_ALBUM_WAIT_S", "1.6"))

REWRITE_SYSTEM = """Ты старший копирайтер авторского Telegram-канала «Заметки эпохи».
Задача: переписать исходный пост так, чтобы его было удобно читать в Telegram.

СМЫСЛ:
• Сохрани факты и смысл, слегка освежи формулировки.
• Не выдумывай цифры, имена, даты и детали.
• Убери чужие призывы подписаться, рекламу, водяные ссылки на другие каналы.
• Не добавляй подпись канала и ссылку на нас — их приклеит система.

СТРУКТУРА (копирайтинг для Telegram):
1) Первая строка — сильный заголовок/хук: сразу понятно, о чём речь.
   Оформи заголовок жирным: <b>…</b>
2) Короткий лид (1–2 предложения) — суть.
3) Дальше — воздух: короткие абзацы (1–3 строки), пустая строка между блоками.
4) Если есть перечисления, шаги, плюсы/минусы, факты — сделай список:
   каждая строка с «• » (теги <ul>/<li> в Telegram не работают).
5) Ключевые слова и цифры выделяй <b>…</b> или <i>…</i>.
6) В конце можно одну спокойную мысль-вывод (без агрессивного CTA).

ОФОРМЛЕНИЕ (Telegram HTML):
• Разрешены ТОЛЬКО теги: <b> <i> <u> <s> <code> <a href="">
• Не используй Markdown (**bold**, _italic_) — только HTML-теги.
• Не используй заголовки #, цитаты >, таблицы.
• Эмодзи — умеренно (0–3), только если помогают сканировать текст.
• Без стены текста: лучше короче и яснее.

Верни ТОЛЬКО готовый текст поста (HTML), без кавычек, без пояснений и без ```."""


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

def _md_to_telegram_html(text: str) -> str:
    """Convert leftover Markdown emphasis to Telegram HTML."""
    s = text or ""
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"__(.+?)__", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s, flags=re.S)
    s = re.sub(
        r"(?<![A-Za-z0-9_])_(?!_)(.+?)(?<!_)_(?![A-Za-z0-9_])",
        r"<i>\1</i>",
        s,
        flags=re.S,
    )
    s = re.sub(r"(?m)^\s*[-*]\s+", "• ", s)
    s = re.sub(r"(?m)^\s*\d+[.)]\s+", "• ", s)
    return s


_ALLOWED_TG_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "code",
    "pre",
    "a",
    "tg-spoiler",
}


def sanitize_telegram_html(text: str) -> str:
    """Keep safe Telegram HTML tags; escape everything else."""
    s = _md_to_telegram_html((text or "").strip())
    s = s.replace("<strong>", "<b>").replace("</strong>", "</b>")
    s = s.replace("<em>", "<i>").replace("</em>", "</i>")

    tokens: list[str] = []

    def protect(tag_html: str, name: str) -> str:
        name = name.lower()
        # Leave unknown/invalid tags as raw text — final html_escape handles them once.
        if name not in _ALLOWED_TG_TAGS:
            return tag_html
        low = tag_html.lower()
        if name == "a" and not low.startswith("</"):
            if not re.match(
                r'^<a\s+href="(https?://[^"]+|tg://[^"]+)">$',
                tag_html,
                flags=re.I,
            ):
                return tag_html
        tokens.append(tag_html)
        return f"\x00TG{len(tokens) - 1}\x00"

    def repl(m: re.Match[str]) -> str:
        return protect(m.group(0), m.group(1))

    s = re.sub(r"</?([a-zA-Z0-9\-]+)(?:\s+[^>]*)?>", repl, s)
    parts = re.split(r"(\x00TG\d+\x00)", s)
    out: list[str] = []
    for part in parts:
        tm = re.match(r"\x00TG(\d+)\x00", part or "")
        if tm:
            out.append(tokens[int(tm.group(1))])
        else:
            out.append(html_escape(part))
    return "".join(out)




def signature(channel_id: str | None = None) -> str:
    """HTML footer: megaphone + clickable channel name."""
    raw = (os.getenv("TELEGRAM_CURATE_SIGNATURE") or "").strip()
    if raw:
        return raw.replace("\\n", "\n")
    link = channel_link(channel_id) or "https://t.me/epoch_z"
    name = (os.getenv("TELEGRAM_CURATE_CHANNEL_TITLE") or "Заметки эпохи").strip()
    return (
        "\n\n"
        f'📣 <a href="{html_escape(link)}">{html_escape(name)}</a>'
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


def extract_media_item(message: dict[str, Any]) -> dict[str, Any] | None:
    """One InputMedia* item for sendMediaGroup (photo/video)."""
    photos = message.get("photo") or []
    if isinstance(photos, list) and photos:
        last = photos[-1] if isinstance(photos[-1], dict) else None
        if last and last.get("file_id"):
            return {"type": "photo", "media": last["file_id"]}

    video = message.get("video") or {}
    if isinstance(video, dict) and video.get("file_id"):
        return {"type": "video", "media": video["file_id"]}

    document = message.get("document") or {}
    if isinstance(document, dict) and document.get("file_id"):
        mime = str(document.get("mime_type") or "")
        if mime.startswith("video/"):
            return {"type": "video", "media": document["file_id"]}
        if mime.startswith("image/"):
            return {"type": "photo", "media": document["file_id"]}
    return None


def extract_post(message: dict[str, Any]) -> dict[str, Any]:
    """Text/caption + media file_ids. Never use forwardMessage — re-send as new posts."""
    text = str(message.get("text") or message.get("caption") or "").strip()
    photo_file_id = None
    video_file_id = None
    animation_file_id = None
    document_file_id = None
    media_kind = None
    media_group_id = str(message.get("media_group_id") or "").strip() or None

    item = extract_media_item(message)
    if item and item["type"] == "photo":
        photo_file_id = item["media"]
        media_kind = "photo"
    elif item and item["type"] == "video":
        video_file_id = item["media"]
        media_kind = "video"

    animation = message.get("animation") or {}
    if isinstance(animation, dict) and animation.get("file_id"):
        animation_file_id = animation.get("file_id")
        media_kind = "animation"

    document = message.get("document") or {}
    if isinstance(document, dict) and document.get("file_id"):
        mime = str(document.get("mime_type") or "")
        if not media_kind:
            if mime.startswith("video/"):
                video_file_id = document.get("file_id")
                media_kind = "video"
            elif mime.startswith("image/"):
                photo_file_id = document.get("file_id")
                media_kind = "photo"
            else:
                document_file_id = document.get("file_id")
                media_kind = "document"

    # single-photo path if extract_media_item already set kinds above; keep animation
    photos = message.get("photo") or []
    if not photo_file_id and isinstance(photos, list) and photos:
        last = photos[-1] if isinstance(photos[-1], dict) else None
        if last and last.get("file_id"):
            photo_file_id = last.get("file_id")
            media_kind = media_kind or "photo"

    video = message.get("video") or {}
    if not video_file_id and isinstance(video, dict) and video.get("file_id"):
        video_file_id = video.get("file_id")
        media_kind = media_kind or "video"

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
        "media_group_id": media_group_id,
        "message_id": message.get("message_id"),
        "media_item": item,
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


def compose_post_html(body: str, *, channel_id: str | None = None) -> str:
    """Sanitize Telegram HTML body + append clickable footer."""
    body_html = sanitize_telegram_html((body or "").rstrip())
    sig = signature(channel_id)
    if "📣" in body_html or "t.me/epoch_z" in body_html:
        return body_html
    return f"{body_html}{sig}"


def apply_signature(body: str, *, channel_id: str | None = None) -> str:
    """Append channel footer with clickable 📣 Заметки эпохи."""
    return compose_post_html(body, channel_id=channel_id)



TgPostFn = Callable[..., dict[str, Any]]



def _queue_album_piece(
    *,
    media_group_id: str,
    message: dict[str, Any],
    chat_id: Any,
    tg_post: "TgPostFn",
    openai_api_key: str,
    model: str,
) -> None:
    """Buffer album parts; flush one sendMediaGroup after a short quiet period."""
    post = extract_post(message)
    item = post.get("media_item") or extract_media_item(message)
    if not item:
        # no usable media in this piece — ignore for album
        return

    with _MEDIA_GROUP_LOCK:
        bucket = _MEDIA_GROUPS.setdefault(
            media_group_id,
            {
                "chat_id": chat_id,
                "pieces": [],
                "texts": [],
                "tg_post": tg_post,
                "openai_api_key": openai_api_key,
                "model": model,
            },
        )
        bucket["pieces"].append(
            {
                "message_id": int(message.get("message_id") or 0),
                "item": item,
                "text": post.get("text") or "",
            }
        )
        if post.get("text"):
            bucket["texts"].append(post["text"])

        old = _MEDIA_GROUP_TIMERS.pop(media_group_id, None)
        if old is not None:
            try:
                old.cancel()
            except Exception:
                pass

        timer = threading.Timer(
            MEDIA_GROUP_WAIT_S,
            _flush_album,
            kwargs={"media_group_id": media_group_id},
        )
        timer.daemon = True
        _MEDIA_GROUP_TIMERS[media_group_id] = timer
        timer.start()

    # lightweight ack once
    try:
        tg_post(
            "sendChatAction",
            {"chat_id": chat_id, "action": "typing"},
            token=bot_token(),
            timeout=10.0,
        )
    except Exception:
        pass


def _flush_album(*, media_group_id: str) -> None:
    with _MEDIA_GROUP_LOCK:
        bucket = _MEDIA_GROUPS.pop(media_group_id, None)
        _MEDIA_GROUP_TIMERS.pop(media_group_id, None)
    if not bucket:
        return

    tg_post = bucket["tg_post"]
    chat_id = bucket["chat_id"]
    openai_api_key = bucket["openai_api_key"]
    model = bucket["model"]
    pieces = sorted(bucket.get("pieces") or [], key=lambda p: p.get("message_id") or 0)
    # dedupe by file_id keep order
    seen: set[str] = set()
    media_items: list[dict[str, Any]] = []
    for piece in pieces:
        item = dict(piece.get("item") or {})
        mid = str(item.get("media") or "")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        media_items.append(item)
        if len(media_items) >= 10:  # Telegram limit
            break

    if not media_items:
        return

    source = ""
    for piece in pieces:
        if piece.get("text"):
            source = str(piece["text"])
            break
    if not source:
        for txt in bucket.get("texts") or []:
            if txt:
                source = str(txt)
                break

    channel = target_channel()
    if not channel:
        tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": "Сначала укажите канал: /channel @epoch_z"},
            token=bot_token(),
            timeout=20.0,
        )
        return

    rewritten = ""
    if source:
        if not openai_api_key:
            tg_post(
                "sendMessage",
                {"chat_id": chat_id, "text": "OPENAI_API_KEY не настроен на сервере."},
                token=bot_token(),
                timeout=20.0,
            )
            return
        try:
            rewritten = rewrite_text(
                source, openai_api_key=openai_api_key, model=model
            )
        except Exception as exc:
            logger.exception("album rewrite failed")
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
        pub = _publish_album(
            tg_post,
            channel=channel,
            text=final,
            media_items=media_items,
        )
        mid = pub.get("message_id")
        n = pub.get("count") or len(media_items)
        tg_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    f"Готово → {channel}"
                    + (f" #{mid}" if mid else "")
                    + f" (альбом {n} файл.)"
                ),
            },
            token=bot_token(),
            timeout=20.0,
        )
    except Exception as exc:
        logger.exception("album publish failed")
        tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": f"Ошибка публикации альбома: {exc}"},
            token=bot_token(),
            timeout=20.0,
        )


def _publish_album(
    tg_post: "TgPostFn",
    *,
    channel: str,
    text: str,
    media_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Publish photo/video carousel as one native album (sendMediaGroup)."""
    if not media_items:
        raise RuntimeError("empty_album")
    if len(media_items) == 1:
        only = media_items[0]
        post = {
            "photo_file_id": only["media"] if only.get("type") == "photo" else None,
            "video_file_id": only["media"] if only.get("type") == "video" else None,
            "animation_file_id": None,
            "document_file_id": None,
        }
        return _publish_native(tg_post, channel=channel, text=text, post=post)

    caption_limit = 1024
    full = text or ""
    media_payload: list[dict[str, Any]] = []
    for i, item in enumerate(media_items):
        entry = {"type": item["type"], "media": item["media"]}
        if i == 0 and full and len(full) <= caption_limit:
            entry["caption"] = full
            entry["parse_mode"] = "HTML"
        media_payload.append(entry)

    raw = tg_post(
        "sendMediaGroup",
        {"chat_id": channel, "media": media_payload},
        token=bot_token(),
        timeout=120.0,
    )
    if not raw.get("ok"):
        raise RuntimeError(raw.get("description") or str(raw))
    results = raw.get("result") or []
    first = results[0] if results else {}
    mid = first.get("message_id") if isinstance(first, dict) else None

    # Caption did not fit on first item — send text as follow-up native message
    if full and len(full) > caption_limit:
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
        "message_id": mid,
        "kind": f"album:{len(media_items)}",
        "count": len(media_items),
        "result": first,
    }


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
                    "Перешлите сюда пост (текст / фото / видео / карусель) — "
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

    # Album / carousel: collect pieces, publish as one sendMediaGroup
    mgid = str(message.get("media_group_id") or "").strip()
    if mgid:
        _queue_album_piece(
            media_group_id=mgid,
            message=message,
            chat_id=chat_id,
            tg_post=tg_post,
            openai_api_key=openai_api_key,
            model=model,
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
