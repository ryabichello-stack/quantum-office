"""E2 — inbound channel adapters (Telegram, MAX, …)."""

from app.adapters.channels.base import ChannelAdapter, InboundMessage, OutboundMessage
from app.adapters.channels.registry import get_channel_adapter, register_channel_adapter
from app.adapters.channels.max import MaxAdapter
from app.adapters.channels.telegram import TelegramAdapter

register_channel_adapter(TelegramAdapter())
register_channel_adapter(MaxAdapter())

__all__ = [
    "ChannelAdapter",
    "InboundMessage",
    "OutboundMessage",
    "MaxAdapter",
    "TelegramAdapter",
    "get_channel_adapter",
    "register_channel_adapter",
]
