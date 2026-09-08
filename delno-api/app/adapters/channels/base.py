"""ChannelAdapter contract — parse webhooks, send outbound messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class InboundMessage:
    channel_type: str
    external_user_id: str
    text: str
    display_name: str | None = None
    username: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    text: str


class ChannelAdapter(Protocol):
    channel_type: str

    def parse_webhook(self, payload: dict[str, Any]) -> list[InboundMessage]:
        """Extract user messages from a provider webhook payload."""

    def verify_webhook_secret(self, *, secret_header: str | None, expected_secret: str | None) -> bool:
        """Return True when secret verification passes or is not configured."""

    def send_reply(
        self,
        *,
        external_user_id: str,
        message: OutboundMessage,
        credentials: dict[str, Any],
    ) -> dict[str, Any]:
        """Deliver a reply to the external user."""
