"""Registry of channel adapters by type."""

from __future__ import annotations

from app.adapters.channels.base import ChannelAdapter

_REGISTRY: dict[str, ChannelAdapter] = {}


def register_channel_adapter(adapter: ChannelAdapter) -> None:
    _REGISTRY[adapter.channel_type] = adapter


def get_channel_adapter(channel_type: str) -> ChannelAdapter | None:
    return _REGISTRY.get(channel_type)


def list_channel_adapters() -> list[str]:
    return sorted(_REGISTRY.keys())
