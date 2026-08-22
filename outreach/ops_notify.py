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


def notify_ops_event(
  *,
  event: str,
  title: str,
  body: str,
  settings: Any = None,
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

  to_addr = (
    _cfg(settings, "OPS_NOTIFY_EMAIL", "")
    or _cfg(settings, "REPLY_NOTIFY_EMAIL", "")
    or os.getenv("MAIL_REPLY_TO", "")
    or os.getenv("MAIL_USERNAME", "")
  ).strip()

  result: dict[str, Any] = {"ok": True, "event": event, "email": False, "telegram": False}
  subject = f"[Outreach] {title}"

  if email_on and to_addr:
    try:
      _notify_email(subject=subject, body=body, to_addr=to_addr)
      result["email"] = True
    except Exception as exc:  # noqa: BLE001
      logger.warning("ops notify email failed: %s", exc)
      result["email_error"] = str(exc)[:300]

  if tg_on and bot_token and chat_id:
    try:
      _notify_telegram(text=f"{title}\n\n{body}", bot_token=bot_token, chat_id=chat_id)
      result["telegram"] = True
    except Exception as exc:  # noqa: BLE001
      logger.warning("ops notify telegram failed: %s", exc)
      result["telegram_error"] = str(exc)[:300]

  if result.get("email") or result.get("telegram"):
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
    dedup_key=f"callback:{phone}",
    dedup_minutes=15,
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

