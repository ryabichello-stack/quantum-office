"""E2 — inbound channel adapters (Telegram, MAX, …)."""

from app.adapters.channels.base import ChannelAdapter, InboundMessage, OutboundMessage
from app.adapters.channels.registry import get_channel_adapter, register_channel_adapter
from app.adapters.channels.telegram import TelegramAdapter

register_channel_adapter(TelegramAdapter())

__all__ = [
    "ChannelAdapter",
    "InboundMessage",
    "OutboundMessage",
    "TelegramAdapter",
    "get_channel_adapter",
    "register_channel_adapter",
]
