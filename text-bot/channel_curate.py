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
MEDIA_GROUP_WAIT_S = float(os.getenv("TELEGRAM_CURATE_ALBUM_WAIT_S", "2.8"))

REWRITE_SYSTEM = """Ты редактор канала «Заметки эпохи». Задача — МАКСИМАЛЬНО близко к исходному тексту.

ГЛАВНОЕ:
• Сохрани тон, ритм, иронию, резкость, «изюминку» и живые формулировки автора.
• Не превращай новость в бездушный пересказ, лид или «копирайтинг».
• Не меняй структуру ради «удобства чтения». Не придумывай заголовок/хук/вывод, если их не было.
• Почти дословно: правь только то, без чего нельзя (см. ниже). Если сомневаешься — оставь как было.

МОЖНО УБРАТЬ / ПОПРАВИТЬ:
• чужие «подписывайтесь», рекламу, водяные ссылки на другие каналы;
• явный мусор/битые символы;
• при необходимости — лёгкая правка опечаток, без смены смысла и стиля.

ЖЁСТКИЕ ЗАПРЕТЫ:
• Если вход пустой — верни пустую строку. Ничего не выдумывай.
• Не описывай фото/видео и не придумывай подпись.
• Не выдумывай цифры, имена, даты, факты.
• Не добавляй подпись нашего канала — её приклеит система.
• Не раздувай текст, не сглаживай характер, не делай «нейтральный пресс-релиз».

ОФОРМЛЕНИЕ (Telegram HTML):
• Разрешены ТОЛЬКО: <b> <i> <u> <s> <code> <a href="">
• Сохрани исходные выделения, если они уже есть по смыслу.
• Без Markdown, без <br>/<p>/<div>/<ul>/<li>/<h1>–<h6>.

Верни ТОЛЬКО текст поста (HTML), без кавычек, без пояснений и без ```."""


def rewrite_mode() -> str:
    """off | light (default) | full — how aggressively to rewrite source text."""
    raw = (os.getenv("TELEGRAM_CURATE_REWRITE_MODE") or "light").strip().lower()
    if raw in {"0", "false", "no", "off", "none", "passthrough"}:
        return "off"
    if raw in {"full", "copywriter", "aggressive"}:
        return "full"
    return "light"


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

# LLM/CMS junk that must become newlines / disappear — never show as literal tags.
_BLOCK_TAG_TO_NL = re.compile(
    r"</?(?:br|p|div|section|article|header|footer|h[1-6]|li|tr|blockquote)(?:\s[^>]*)?/?>",
    flags=re.I,
)
_STRIP_TAG = re.compile(
    r"</?(?:span|ul|ol|table|thead|tbody|td|th|font|center|hr|img|html|body|head|meta|style|script)(?:\s[^>]*)?/?>",
    flags=re.I,
)


def strip_html_to_plain(text: str) -> str:
    """Drop all tags; keep readable plain text (fallback when HTML parse fails)."""
    s = text or ""
    s = _BLOCK_TAG_TO_NL.sub("\n", s)
    s = _STRIP_TAG.sub("", s)
    s = re.sub(r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler)(?:\s[^>]*)?/?>", "", s, flags=re.I)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def sanitize_telegram_html(text: str) -> str:
    """Keep safe Telegram HTML tags; never leave raw <br>/<p>/… visible in the post."""
    s = (text or "").strip()
    if not s:
        return ""
    # Drop fences / accidental wrappers from the model
    s = re.sub(r"^```(?:html|xml|markdown)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    s = _BLOCK_TAG_TO_NL.sub("\n", s)
    s = _STRIP_TAG.sub("", s)
    s = _md_to_telegram_html(s)
    s = s.replace("<strong>", "<b>").replace("</strong>", "</b>")
    s = s.replace("<em>", "<i>").replace("</em>", "</i>")
    s = re.sub(r"\n{3,}", "\n\n", s)

    tokens: list[str] = []

    def protect(tag_html: str, name: str) -> str:
        name = name.lower()
        if name not in _ALLOWED_TG_TAGS:
            # Unknown tag → drop entirely (never show literal <tag> in the channel)
            return ""
        low = tag_html.lower()
        if name == "a" and not low.startswith("</"):
            if not re.match(
                r'^<a\s+href="(https?://[^"]+|tg://[^"]+)">$',
                tag_html,
                flags=re.I,
            ):
                return ""
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
    cleaned = "".join(out)
    # Drop empty / unpaired emphasis leftovers that Telegram rejects
    cleaned = re.sub(r"</?(?:b|i|u|s|code|pre)>\s*</?(?:b|i|u|s|code|pre)>", "", cleaned)
    return cleaned.strip()


def entities_to_html(text: str, entities: list[Any] | None) -> str:
    """Rebuild Telegram HTML from message entities (UTF-16 offsets)."""
    raw = text or ""
    if not raw:
        return ""
    if not entities:
        return html_escape(raw)

    # Work in UTF-16 code units (Telegram entity offsets)
    encoded = raw.encode("utf-16-le")
    units = [encoded[i : i + 2] for i in range(0, len(encoded), 2)]

    opens: dict[int, list[str]] = {}
    closes: dict[int, list[str]] = {}

    def add_open(pos: int, tag: str) -> None:
        opens.setdefault(pos, []).append(tag)

    def add_close(pos: int, tag: str) -> None:
        closes.setdefault(pos, []).insert(0, tag)

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        et = str(ent.get("type") or "")
        try:
            off = int(ent.get("offset") or 0)
            length = int(ent.get("length") or 0)
        except (TypeError, ValueError):
            continue
        if length <= 0 or off < 0 or off + length > len(units):
            continue
        end = off + length
        if et in {"bold", "strong"}:
            add_open(off, "<b>")
            add_close(end, "</b>")
        elif et in {"italic", "em"}:
            add_open(off, "<i>")
            add_close(end, "</i>")
        elif et in {"underline", "ins"}:
            add_open(off, "<u>")
            add_close(end, "</u>")
        elif et in {"strikethrough", "strike", "s"}:
            add_open(off, "<s>")
            add_close(end, "</s>")
        elif et == "code":
            add_open(off, "<code>")
            add_close(end, "</code>")
        elif et == "pre":
            add_open(off, "<pre>")
            add_close(end, "</pre>")
        elif et == "spoiler":
            add_open(off, "<tg-spoiler>")
            add_close(end, "</tg-spoiler>")
        elif et == "text_link":
            url = str(ent.get("url") or "").strip()
            if url.startswith(("http://", "https://", "tg://")):
                add_open(off, f'<a href="{html_escape(url)}">')
                add_close(end, "</a>")
        elif et == "text_mention":
            user = ent.get("user") or {}
            uid = user.get("id")
            if uid:
                add_open(off, f'<a href="tg://user?id={uid}">')
                add_close(end, "</a>")
        # mention / hashtag / cashtag / url / email / phone / bot_command — leave plain

    out: list[str] = []
    for i, unit in enumerate(units):
        for tag in closes.get(i, []):
            out.append(tag)
        for tag in opens.get(i, []):
            out.append(tag)
        ch = unit.decode("utf-16-le")
        out.append(html_escape(ch))
    for tag in closes.get(len(units), []):
        out.append(tag)
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
    raw_text = str(message.get("text") or message.get("caption") or "")
    text = raw_text.strip()
    entities = message.get("entities") or message.get("caption_entities") or []
    if not isinstance(entities, list):
        entities = []
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

    # Prefer original Telegram formatting when we publish without LLM rewrite
    text_html = entities_to_html(raw_text, entities) if text else ""

    return {
        "text": text,
        "text_html": text_html,
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


_FOREIGN_CTA_LINE = re.compile(
    r"(?im)^(?:\s*(?:👉|➡️|❗️|‼️|📢|📣)?\s*)?(?:"
    r"подпис(?:ывайтесь|ка|итесь)|"
    r"наш\s+канал|"
    r"читать\s+далее\s+в\s+канале|"
    r"t\.me/(?!epoch_z)[A-Za-z0-9_]+"
    r").*$"
)


def strip_foreign_cta(text: str) -> str:
    """Drop obvious foreign subscribe/promo lines; keep the rest intact."""
    s = text or ""
    lines = []
    for line in s.splitlines():
        if _FOREIGN_CTA_LINE.search(line.strip()):
            continue
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def rewrite_text(source: str, *, openai_api_key: str, model: str) -> str:
    src = (source or "").strip()
    if not src:
        return ""
    if not (openai_api_key or "").strip():
        logger.warning("rewrite skipped: OPENAI_API_KEY missing — publishing source text")
        return src
    from openai import OpenAI

    client = OpenAI(api_key=openai_api_key)
    mode = rewrite_mode()
    user = (
        "Отредактируй МАКСИМАЛЬНО близко к оригиналу (почти дословно). "
        "Сохрани характер и формулировки. Убери только чужой CTA/рекламу.\n\n"
        f"{src[:6000]}"
    )
    kwargs: dict = {
        "model": model or "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": REWRITE_SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    # gpt-5* / some mini models reject custom temperature
    model_l = (model or "").lower()
    if not model_l.startswith("gpt-5"):
        # Low temperature → stay close to source (was 0.7 → bland rewrite)
        kwargs["temperature"] = 0.35 if mode == "full" else 0.15
    resp = client.chat.completions.create(**kwargs)
    out = (resp.choices[0].message.content or "").strip()
    out = re.sub(r"^```(?:\w+)?\n|\n```$", "", out).strip()
    if (out.startswith("«") and out.endswith("»")) or (
        len(out) >= 2 and out[0] == '"' and out[-1] == '"'
    ):
        out = out[1:-1].strip()
    return out or src


def compose_post_html(body: str, *, channel_id: str | None = None) -> str:
    """Sanitize Telegram HTML body + append clickable footer.

    Empty body → footer only (media-only posts: no invented caption).
    """
    body_html = sanitize_telegram_html((body or "").rstrip())
    sig = signature(channel_id)
    if "📣" in body_html or "t.me/epoch_z" in body_html:
        return body_html
    if not body_html:
        return sig.lstrip("\n")
    return f"{body_html}{sig}"


def prepare_body(
    *,
    source: str,
    source_html: str = "",
    openai_api_key: str,
    model: str,
    has_media: bool,
) -> str:
    """Keep source voice; media-only → empty (footer only).

    TELEGRAM_CURATE_REWRITE_MODE:
      off   — publish original (entities HTML if any), only strip foreign CTA lines
      light — default; near-verbatim LLM edit (tone/spice kept)
      full  — same fidelity prompt, slightly higher temperature
    """
    src = (source or "").strip()
    if not src:
        # No caption/text: do not invent. Publish media as-is (+ footer).
        return ""

    mode = rewrite_mode()
    original = (source_html or html_escape(src)).strip()

    if mode == "off" or not (openai_api_key or "").strip():
        if not (openai_api_key or "").strip() and mode != "off":
            logger.warning("rewrite skipped: OPENAI_API_KEY missing — publishing source text")
        # Prefer original formatting; still drop obvious foreign CTAs from plain path
        if source_html:
            return original
        return html_escape(strip_foreign_cta(src))

    rewritten = rewrite_text(src, openai_api_key=openai_api_key, model=model)
    out = (rewritten or "").strip()
    if not out:
        return original
    return out


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
                "text_html": post.get("text_html") or "",
            }
        )
        if post.get("text"):
            bucket["texts"].append(post["text"])
            if post.get("text_html"):
                bucket.setdefault("texts_html", []).append(post["text_html"])

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
    source_html = ""
    for piece in pieces:
        if piece.get("text"):
            source = str(piece["text"])
            source_html = str(piece.get("text_html") or "")
            break
    if not source:
        for txt in bucket.get("texts") or []:
            if txt:
                source = str(txt)
                break
        htmls = bucket.get("texts_html") or []
        if htmls:
            source_html = str(htmls[0] or "")

    channel = target_channel()
    if not channel:
        tg_post(
            "sendMessage",
            {"chat_id": chat_id, "text": "Сначала укажите канал: /channel @epoch_z"},
            token=bot_token(),
            timeout=20.0,
        )
        return

    try:
        body = prepare_body(
            source=source,
            source_html=source_html,
            openai_api_key=openai_api_key,
            model=model,
            has_media=True,
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

    final = apply_signature(body, channel_id=channel)

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


def _is_html_parse_error(raw: dict[str, Any]) -> bool:
    desc = str(raw.get("description") or "").lower()
    return "parse" in desc and ("entities" in desc or "html" in desc or "tag" in desc)


def _send_message_html_or_plain(
    tg_post: "TgPostFn",
    *,
    channel: str,
    text: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """sendMessage with HTML; on parse error retry as plain text."""
    payload = {
        "chat_id": channel,
        "text": (text or "")[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if extra:
        payload.update(extra)
    raw = tg_post("sendMessage", payload, token=bot_token(), timeout=20.0)
    if raw.get("ok"):
        return raw
    if _is_html_parse_error(raw):
        logger.warning("HTML parse failed on sendMessage — retry plain: %s", raw.get("description"))
        plain = strip_html_to_plain(text)
        # Keep footer link readable even in plain mode
        payload_plain = {
            "chat_id": channel,
            "text": (plain or text or "")[:4096],
            "disable_web_page_preview": True,
        }
        if extra:
            payload_plain.update({k: v for k, v in extra.items() if k != "parse_mode"})
        raw2 = tg_post("sendMessage", payload_plain, token=bot_token(), timeout=20.0)
        if raw2.get("ok"):
            return raw2
        raise RuntimeError(raw2.get("description") or str(raw2))
    raise RuntimeError(raw.get("description") or str(raw))


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
    full = (text or "").strip()
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
    if not raw.get("ok") and _is_html_parse_error(raw) and full:
        # Retry album with plain caption (no parse_mode) so gallery still posts as one group
        logger.warning("HTML parse failed on album — retry plain caption: %s", raw.get("description"))
        media_payload = []
        plain = strip_html_to_plain(full) or full
        for i, item in enumerate(media_items):
            entry = {"type": item["type"], "media": item["media"]}
            if i == 0 and plain and len(plain) <= caption_limit:
                entry["caption"] = plain
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
        _send_message_html_or_plain(tg_post, channel=channel, text=full)

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
                    "Перешлите сюда пост (текст / фото / видео / карусель):\n"
                    "• есть текст — почти дословно (сохраняю тон), уберу чужой CTA;\n"
                    "• только фото/видео без текста — как есть, без выдуманной подписи;\n"
                    "• альбом — целиком; в конце ссылка на канал.\n"
                    "Режим: TELEGRAM_CURATE_REWRITE_MODE=light|off|full\n\n"
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

    try:
        body = prepare_body(
            source=source,
            source_html=str(post.get("text_html") or ""),
            openai_api_key=openai_api_key,
            model=model,
            has_media=has_media,
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

    final = apply_signature(body, channel_id=channel)

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
    full = (text or "").strip()
    photo = post.get("photo_file_id")
    video = post.get("video_file_id")
    animation = post.get("animation_file_id")
    document = post.get("document_file_id")

    def _send_media(method: str, file_field: str, file_id: str, kind: str) -> dict[str, Any]:
        if full and len(full) <= caption_limit:
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
            if not raw.get("ok") and _is_html_parse_error(raw):
                logger.warning(
                    "HTML parse failed on %s — retry plain caption: %s",
                    method,
                    raw.get("description"),
                )
                plain = strip_html_to_plain(full) or full
                raw = tg_post(
                    method,
                    {
                        "chat_id": channel,
                        file_field: file_id,
                        "caption": plain[:caption_limit],
                        "disable_web_page_preview": True,
                    },
                    token=bot_token(),
                    timeout=60.0,
                )
            if not raw.get("ok"):
                raise RuntimeError(raw.get("description") or str(raw))
            result = raw.get("result") or {}
            return {"message_id": result.get("message_id"), "kind": kind, "result": result}

        # No caption, or caption too long: media first, then text follow-up
        payload: dict[str, Any] = {"chat_id": channel, file_field: file_id}
        raw = tg_post(method, payload, token=bot_token(), timeout=60.0)
        if not raw.get("ok"):
            raise RuntimeError(raw.get("description") or str(raw))
        mid = (raw.get("result") or {}).get("message_id")
        if not full:
            return {"message_id": mid, "kind": kind, "result": raw.get("result")}
        raw2 = _send_message_html_or_plain(tg_post, channel=channel, text=full)
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

    raw = _send_message_html_or_plain(tg_post, channel=channel, text=full)
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
