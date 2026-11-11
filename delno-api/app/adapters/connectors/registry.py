from __future__ import annotations

from app.adapters.connectors.base import CONNECTOR_KINDS, OfficeConnector
from app.adapters.connectors.calendar import CalendarConnector
from app.adapters.connectors.conference import ConferenceConnector
from app.adapters.connectors.files import FilesConnector
from app.adapters.connectors.mail import MailConnector

_REGISTRY: dict[str, OfficeConnector] = {}


def register_connector(connector: OfficeConnector) -> None:
    _REGISTRY[connector.kind] = connector


def get_connector(kind: str) -> OfficeConnector | None:
    return _REGISTRY.get(kind)


def list_connectors() -> list[OfficeConnector]:
    return [_REGISTRY[k] for k in CONNECTOR_KINDS if k in _REGISTRY]


# default registrations
register_connector(MailConnector())
register_connector(CalendarConnector())
register_connector(FilesConnector())
register_connector(ConferenceConnector())
