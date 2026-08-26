"""Messenger channel adapters for the Quantum Labs secretary.

Dialogue core stays in ``secretary.py``. Each adapter only:
1) normalizes inbound events → ``InboundMessage``
2) calls ``secretary.handle``
3) sends the reply back via the channel API

Guest messengers (WhatsApp / Max / VK) always use guest role →
Second Brain principal ``service:text-guest`` (faq-safe).
"""

from __future__ import annotations

from channels.base import InboundMessage, channel_status
from channels import max_messenger, telegram_business, vk, whatsapp

__all__ = [
    "InboundMessage",
    "channel_status",
    "max_messenger",
    "telegram_business",
    "vk",
    "whatsapp",
]
