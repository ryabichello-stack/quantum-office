"""Shared types for messenger channel adapters."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("ava-text-bot.channels")

# Shared pool so webhook handlers return 200 quickly (Max requires <30s).
_HANDLE_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="msg-ch")


@dataclass
class InboundMessage:
    channel: str
    user_id: str
    text: str
    reply_to: Optional[str] = None
    chat_type: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


def env_flag(name: str, default: str = "false") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def channel_status() -> dict[str, Any]:
    """Health snapshot for all optional messenger channels."""
    from channels import max_messenger, vk, whatsapp

    return {
        "whatsapp": whatsapp.status(),
        "max": max_messenger.status(),
        "vk": vk.status(),
    }


def process_async(
    msg: InboundMessage,
    *,
    send_reply: Callable[[InboundMessage, str], None],
    secretary_handle: Callable[..., dict[str, Any]],
) -> None:
    """Run secretary in a worker and deliver the reply."""

    def _run() -> None:
        try:
            result = secretary_handle(
                channel=msg.channel,
                user_id=msg.user_id,
                text=msg.text,
                reply_to=msg.reply_to,
                chat_type=msg.chat_type,
            )
            reply = str(result.get("reply") or "").strip() or "…"
            send_reply(msg, reply)
            logger.info(
                "%s replied user_id=%s ok=%s chars=%s",
                msg.channel,
                msg.user_id,
                result.get("ok"),
                len(reply),
            )
        except Exception:
            logger.exception("%s handle failed user_id=%s", msg.channel, msg.user_id)
            try:
                send_reply(
                    msg,
                    "Извините, произошла ошибка. Попробуйте ещё раз или напишите "
                    "office@quantumlabs.ru / позвоните на линию Quantum Labs.",
                )
            except Exception:
                logger.exception("%s error reply failed", msg.channel)

    _HANDLE_POOL.submit(_run)
