"""Operator push notifications: email + optional Telegram."""

from __future__ import annotations

import logging
import os
import smtplib
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Any, Iterator
from urllib import error, parse, request

from core.paths import MODULES_DB

logger = logging.getLogger("ava-outreach.ops_notify")

PANEL_BRAND = os.getenv("PANEL_NOTIFY_BRAND", "Quantum Panel").strip() or "Quantum Panel"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _cfg(settings: Any, key: str, default: str = "") -> str:
    if settings is None:
        return os.getenv(key, default) or default
    try:
        if hasattr(settings, "get"):
            return str(settings.get(key, default) or default)
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(key, default) or default


def _cfg_bool(settings: Any, key: str, default: bool = True) -> bool:
    raw = (_cfg(settings, key, "true" if default else "false") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class OpsNotifyStore:
  def __init__(self, db_path: Path | None = None) -> None:
    self.db_path = Path(db_path or MODULES_DB)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.init_db()

  @contextmanager
  def connect(self) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    try:
      yield conn
      conn.commit()
    except Exception:
      conn.rollback()
      raise
    finally:
      conn.close()

  def init_db(self) -> None:
    with self.connect() as conn:
      conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_notify_dedup (
          event_key TEXT PRIMARY KEY,
          sent_at TEXT NOT NULL
        )
        """
      )

  def should_send(self, event_key: str, *, dedup_minutes: int = 30) -> bool:
    with self.connect() as conn:
      row = conn.execute(
        "SELECT sent_at FROM ops_notify_dedup WHERE event_key = ?", (event_key,)
      ).fetchone()
    if not row:
      return True
    try:
      sent = datetime.fromisoformat(str(row["sent_at"]).replace("Z", "+00:00"))
      if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
      return datetime.now(timezone.utc) - sent > timedelta(minutes=max(1, dedup_minutes))
    except ValueError:
      return True

  def mark_sent(self, event_key: str) -> None:
    with self.connect() as conn:
      conn.execute(
        """
        INSERT INTO ops_notify_dedup(event_key, sent_at) VALUES (?, ?)
        ON CONFLICT(event_key) DO UPDATE SET sent_at = excluded.sent_at
        """,
        (event_key, _utc_now()),
      )


_store: OpsNotifyStore | None = None


def _notify_store() -> OpsNotifyStore:
    global _store
    if _store is None:
        _store = OpsNotifyStore()
    return _store


def _notify_email(*, subject: str, body: str, to_addr: str) -> None:
  host = os.getenv("MAIL_SMTP_HOST", "").strip()
  port = int(os.getenv("MAIL_SMTP_PORT", "465"))
  user = os.getenv("MAIL_USERNAME", "").strip()
  password = os.getenv("MAIL_PASSWORD", "")
  if not (host and user and password and to_addr):
    raise RuntimeError("SMTP not configured for ops notify")
  msg = MIMEText(body, "plain", "utf-8")
  msg["From"] = formataddr((os.getenv("MAIL_FROM_NAME", "Quantum Labs Outreach"), user))
  msg["To"] = to_addr
  msg["Subject"] = subject
  msg["Message-ID"] = make_msgid(domain=user.split("@")[-1] if "@" in user else "localhost")
  with smtplib.SMTP_SSL(host, port, timeout=20) as server:
    server.login(user, password)
    server.send_message(msg)


def _notify_telegram(*, text: str, bot_token: str, chat_id: str) -> None:
  url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
  payload = parse.urlencode(
    {"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": "true"}
  ).encode("utf-8")
  req = request.Request(url, data=payload, method="POST")
  try:
    with request.urlopen(req, timeout=15) as resp:
      if resp.status >= 400:
        raise RuntimeError(f"telegram HTTP {resp.status}")
  except error.HTTPError as exc:
    raise RuntimeError(f"telegram HTTP {exc.code}") from exc


def _notify_oncall_webhook(
  *,
  url: str,
  event: str,
  source: str,
  title: str,
  body: str,
) -> None:
  hook = (url or "").strip()
  if not hook:
    return
  payload = json.dumps(
    {
      "event": event,
      "source": source,
      "title": title,
      "body": body,
      "brand": PANEL_BRAND,
    },
    ensure_ascii=False,
  ).encode("utf-8")
  req = request.Request(
    hook,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
  )
  with request.urlopen(req, timeout=15) as resp:
    if resp.status >= 400:
      raise RuntimeError(f"oncall webhook HTTP {resp.status}")


def _format_panel_subject(*, source: str, title: str) -> str:
  src = (source or "Panel").strip() or "Panel"
  return f"[{PANEL_BRAND} · {src}] {title}"


def _format_panel_telegram(*, source: str, title: str, body: str) -> str:
  src = (source or "Panel").strip() or "Panel"
  return f"🔔 {PANEL_BRAND} · {src}\n\n{title}\n\n{body}".strip()


def notify_ops_event(
  *,
  event: str,
  title: str,
  body: str,
  settings: Any = None,
  source: str = "Outreach",
  dedup_key: str | None = None,
  dedup_minutes: int = 30,
  force_email: bool = False,
  force_telegram: bool = False,
) -> dict[str, Any]:
  """Send operator alert via configured channels (email and/or Telegram)."""
  if not _cfg_bool(settings, "OPS_NOTIFY_ENABLED", True):
    return {"ok": True, "skipped": True, "reason": "disabled"}

  event_key = dedup_key or f"{event}:{title[:80]}"
  if not _notify_store().should_send(event_key, dedup_minutes=dedup_minutes):
    return {"ok": True, "skipped": True, "reason": "dedup"}

  email_on = force_email or _cfg_bool(settings, "OPS_NOTIFY_EMAIL_ENABLED", True)
  bot_token = _cfg(settings, "OPS_NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()
  chat_id = _cfg(settings, "OPS_NOTIFY_TELEGRAM_CHAT_ID", "").strip()
  tg_default = bool(bot_token and chat_id)
  tg_on = force_telegram or _cfg_bool(settings, "OPS_NOTIFY_TELEGRAM_ENABLED", tg_default)
  oncall_url = _cfg(settings, "OPS_NOTIFY_ONCALL_WEBHOOK_URL", "").strip()
  oncall_on = _cfg_bool(settings, "OPS_NOTIFY_ONCALL_ENABLED", bool(oncall_url))

  to_addr = (
    _cfg(settings, "OPS_NOTIFY_EMAIL", "")
    or _cfg(settings, "REPLY_NOTIFY_EMAIL", "")
    or os.getenv("MAIL_REPLY_TO", "")
    or os.getenv("MAIL_USERNAME", "")
  ).strip()

  result: dict[str, Any] = {"ok": True, "event": event, "email": False, "telegram": False, "oncall": False}
  subject = _format_panel_subject(source=source, title=title)

  if email_on and to_addr:
    try:
      _notify_email(subject=subject, body=body, to_addr=to_addr)
      result["email"] = True
    except Exception as exc:  # noqa: BLE001
      logger.warning("ops notify email failed: %s", exc)
      result["email_error"] = str(exc)[:300]

  if tg_on and bot_token and chat_id:
    try:
      _notify_telegram(
        text=_format_panel_telegram(source=source, title=title, body=body),
        bot_token=bot_token,
        chat_id=chat_id,
      )
      result["telegram"] = True
    except Exception as exc:  # noqa: BLE001
      logger.warning("ops notify telegram failed: %s", exc)
      result["telegram_error"] = str(exc)[:300]

  if oncall_on and oncall_url:
    try:
      _notify_oncall_webhook(
        url=oncall_url,
        event=event,
        source=source,
        title=title,
        body=body,
      )
      result["oncall"] = True
    except Exception as exc:  # noqa: BLE001
      logger.warning("ops notify oncall webhook failed: %s", exc)
      result["oncall_error"] = str(exc)[:300]

  if result.get("email") or result.get("telegram") or result.get("oncall"):
    _notify_store().mark_sent(event_key)
  else:
    result["skipped"] = True
    result["reason"] = "no_channel_delivered"

  return result


def notify_positive_reply(
  *,
  classification: str,
  from_email: str,
  subject: str,
  preview: str,
  company_name: str = "",
  company_id: str = "",
  settings: Any = None,
) -> dict[str, Any]:
  if not _cfg_bool(settings, "OPS_NOTIFY_ON_POSITIVE_REPLY", True):
    return {"ok": True, "skipped": True}
  if classification not in ("positive_interest", "human_unclassified", "forwarded", "negative"):
    return {"ok": True, "skipped": True}
  body = (
    f"Класс: {classification}\n"
    f"От: {from_email}\n"
    f"Компания: {company_name or '—'} (id={company_id or '—'})\n"
    f"Тема: {subject}\n\n"
    f"{preview[:1500]}"
  )
  return notify_ops_event(
    event="positive_reply",
    title=f"Ответ: {classification} — {from_email}",
    body=body,
    settings=settings,
    source="Outreach",
    dedup_key=f"reply:{from_email}:{classification}",
    dedup_minutes=60,
  )


def notify_mailbox_paused(*, reason: str, settings: Any = None) -> dict[str, Any]:
  if not _cfg_bool(settings, "OPS_NOTIFY_ON_MAILBOX_PAUSE", True):
    return {"ok": True, "skipped": True}
  return notify_ops_event(
    event="mailbox_paused",
    title="Ящик на паузе",
    body=f"Outreach приостановил отправку.\nПричина: {reason}\n\nПроверьте Anti-ban в настройках.",
    settings=settings,
    source="Outreach",
    dedup_key=f"mailbox_pause:{reason[:120]}",
    dedup_minutes=120,
    force_telegram=True,
  )


def notify_callback_request(
  *,
  fio: str,
  phone: str,
  source_email: str = "",
  settings: Any = None,
) -> dict[str, Any]:
  if not _cfg_bool(settings, "OPS_NOTIFY_ON_CALLBACK", True):
    return {"ok": True, "skipped": True}
  return notify_ops_event(
    event="callback",
    title=f"Заявка на звонок: {fio or phone}",
    body=f"ФИО: {fio}\nТелефон: {phone}\nEmail CTA: {source_email or '—'}",
    settings=settings,
    source="Outreach",
    dedup_key=f"callback:{phone}",
    dedup_minutes=15,
  )


def notify_panel_event(
  *,
  event: str,
  title: str,
  body: str,
  source: str = "Console",
  settings: Any = None,
  dedup_key: str | None = None,
  dedup_minutes: int = 30,
) -> dict[str, Any]:
  """Panel-wide operator alert (Console, telephony, services, etc.)."""
  return notify_ops_event(
    event=event,
    title=title,
    body=body,
    settings=settings,
    source=source,
    dedup_key=dedup_key,
    dedup_minutes=dedup_minutes,
  )


def _telegram_api(token: str, method: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
  tok = (token or "").strip()
  if not tok:
    return {"ok": False, "error": "bot_token_required"}
  url = f"https://api.telegram.org/bot{tok}/{method}"
  data = None
  if params:
    data = parse.urlencode({k: v for k, v in params.items() if v is not None}).encode("utf-8")
  req = request.Request(url, data=data, method="POST" if data else "GET")
  try:
    with request.urlopen(req, timeout=20) as resp:
      payload = json.loads(resp.read().decode("utf-8"))
  except error.HTTPError as exc:
    try:
      payload = json.loads(exc.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
      return {"ok": False, "error": f"telegram_http_{exc.code}"}
  except Exception as exc:  # noqa: BLE001
    return {"ok": False, "error": str(exc)[:300]}
  if not payload.get("ok"):
    return {"ok": False, "error": payload.get("description") or "telegram_error", "raw": payload}
  return {"ok": True, "result": payload.get("result")}


def telegram_verify_bot(token: str) -> dict[str, Any]:
  out = _telegram_api(token, "getMe")
  if not out.get("ok"):
    return out
  bot = out.get("result") or {}
  return {
    "ok": True,
    "bot_id": bot.get("id"),
    "username": bot.get("username"),
    "first_name": bot.get("first_name"),
    "link": f"https://t.me/{bot.get('username')}" if bot.get("username") else None,
  }


def telegram_discover_chats(token: str, *, limit: int = 20) -> dict[str, Any]:
  out = _telegram_api(token, "getUpdates", params={"limit": str(max(1, min(limit, 100)))})
  if not out.get("ok"):
    return out
  chats: dict[str, dict[str, Any]] = {}
  for upd in out.get("result") or []:
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = msg.get("chat") or {}
    cid = chat.get("id")
    if cid is None:
      continue
    key = str(cid)
    title = (
      chat.get("title")
      or " ".join(
        p for p in (chat.get("first_name"), chat.get("last_name")) if p
      )
      or chat.get("username")
      or key
    )
    chats[key] = {
      "chat_id": key,
      "type": chat.get("type"),
      "title": title,
      "username": chat.get("username"),
    }
  items = list(chats.values())
  items.sort(key=lambda c: c.get("title") or "")
  return {
    "ok": True,
    "chats": items,
    "hint": "Напишите боту /start в Telegram, затем нажмите «Найти chat id» снова."
    if not items
    else "",
  }


def telegram_send_message(token: str, chat_id: str, text: str) -> dict[str, Any]:
  out = _telegram_api(
    token,
    "sendMessage",
    params={"chat_id": str(chat_id).strip(), "text": text[:3900]},
  )
  if not out.get("ok"):
    return out
  return {"ok": True, "message_id": (out.get("result") or {}).get("message_id")}


def resolve_bot_token(token: str | None, settings: Any = None) -> str:
  cand = (token or "").strip()
  if cand:
    return cand
  return _cfg(settings, "OPS_NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()


def resolve_avatar_jpg(explicit: str | None = None) -> Path | None:
  if explicit:
    p = Path(explicit)
    return p if p.is_file() else None
  for cand in (
    os.getenv("PANEL_BOT_AVATAR_JPG", "").strip(),
    "/opt/quantum-console/static/brand/quantum-panel-bot-512.jpg",
    "/opt/ava-outreach/static/brand/quantum-panel-bot-512.jpg",
  ):
    if cand and Path(cand).is_file():
      return Path(cand)
  return None


def telegram_set_profile_photo(token: str, jpg_path: str) -> dict[str, Any]:
  import httpx

  path = Path(jpg_path)
  if not path.is_file():
    return {"ok": False, "error": "avatar_jpg_not_found"}
  tok = (token or "").strip()
  if not tok:
    return {"ok": False, "error": "bot_token_required"}
  url = f"https://api.telegram.org/bot{tok}/setMyProfilePhoto"
  try:
    with httpx.Client(timeout=60) as client, path.open("rb") as handle:
      resp = client.post(
        url,
        files={
          "photo": (None, '{"type":"static","photo":"attach://myfile"}'),
          "myfile": ("avatar.jpg", handle, "image/jpeg"),
        },
      )
    data = resp.json()
  except Exception as exc:  # noqa: BLE001
    return {"ok": False, "error": str(exc)[:300]}
  if not data.get("ok"):
    return {"ok": False, "error": data.get("description") or "set_profile_photo_failed", "raw": data}
  return {"ok": True}


def telegram_apply_branding(
  token: str,
  *,
  avatar_jpg: str | None = None,
  include_profile_photo: bool = True,
) -> dict[str, Any]:
  """Set bot name, RU descriptions, and optionally profile photo via Bot API."""
  tok = (token or "").strip()
  if not tok:
    return {"ok": False, "error": "bot_token_required"}

  short_ru = (
    "Quantum Panel — операторский центр Quantum Labs. Outreach, телефония, сервисы."
  )
  desc_ru = (
    "Quantum Panel\n\n"
    "Операторский центр управления Quantum Labs — один канал для важных событий.\n\n"
    "Outreach · ответы и заявки на звонок\n"
    "Console · статус робота и сервисов\n"
    "Телефония · звонки и обзвоны\n\n"
    "a.47z.ru/_quantum_console"
  )
  out: dict[str, Any] = {"ok": True, "steps": {}}

  name = _telegram_api(tok, "setMyName", params={"name": "Quantum Panel"})
  out["steps"]["name"] = name
  if not name.get("ok"):
    out["ok"] = False
    out["error"] = name.get("error") or "set_name_failed"
    return out

  short = _telegram_api(
    tok,
    "setMyShortDescription",
    params={"short_description": short_ru, "language_code": "ru"},
  )
  out["steps"]["short_description"] = short
  if not short.get("ok"):
    out["ok"] = False
    out["error"] = short.get("error") or "set_short_description_failed"
    return out

  desc = _telegram_api(
    tok,
    "setMyDescription",
    params={"description": desc_ru, "language_code": "ru"},
  )
  out["steps"]["description"] = desc
  if not desc.get("ok"):
    out["ok"] = False
    out["error"] = desc.get("error") or "set_description_failed"
    return out

  if include_profile_photo:
    jpg = resolve_avatar_jpg(avatar_jpg)
    if jpg:
      photo = telegram_set_profile_photo(tok, str(jpg))
      out["steps"]["profile_photo"] = photo
      if not photo.get("ok"):
        out["ok"] = False
        out["error"] = photo.get("error") or "set_profile_photo_failed"
    else:
      out["steps"]["profile_photo"] = {"ok": False, "skipped": True, "error": "avatar_jpg_not_found"}
  else:
    out["steps"]["profile_photo"] = {"ok": True, "skipped": True, "reason": "include_profile_photo_false"}

  return out

