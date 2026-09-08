"""DaData party lookup adapter (findById/party). Keys stay server-side only."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import get_settings

_INN_RE = re.compile(r"^\d{10}(\d{2})?$")
PARTY_FIND_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
PARTY_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"


def normalize_inn(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    if _INN_RE.match(digits):
        return digits
    return None


def extract_party_fields(suggestion: dict[str, Any]) -> dict[str, Any]:
    """Flatten useful fields from a DaData party suggestion."""
    data = suggestion.get("data") if isinstance(suggestion.get("data"), dict) else {}
    management = data.get("management") if isinstance(data.get("management"), dict) else {}
    name = data.get("name") if isinstance(data.get("name"), dict) else {}
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    fio = data.get("fio") if isinstance(data.get("fio"), dict) else {}

    director = (
        str(management.get("name") or "").strip()
        or " ".join(
            p
            for p in (
                str(fio.get("surname") or "").strip(),
                str(fio.get("name") or "").strip(),
                str(fio.get("patronymic") or "").strip(),
            )
            if p
        ).strip()
        or None
    )

    return {
        "inn": str(data.get("inn") or "").strip() or None,
        "ogrn": str(data.get("ogrn") or data.get("ogrnip") or "").strip() or None,
        "kpp": str(data.get("kpp") or "").strip() or None,
        "okved": str(data.get("okved") or "").strip() or None,
        "company_name": (
            str(name.get("short_with_opf") or name.get("short") or "").strip()
            or str(suggestion.get("value") or "").strip()
            or None
        ),
        "company_full_name": str(name.get("full_with_opf") or name.get("full") or "").strip() or None,
        "director_name": director,
        "director_post": str(management.get("post") or "").strip() or None,
        "address": str(address.get("unrestricted_value") or address.get("value") or "").strip() or None,
        "status": str(state.get("status") or "").strip() or None,
        "party_type": str(data.get("type") or "").strip() or None,
        "value": str(suggestion.get("value") or "").strip() or None,
    }


class PartyLookupAdapter:
    """HTTP client for DaData party findById."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    @staticmethod
    def configured() -> bool:
        return bool((get_settings().dadata_api_key or "").strip())

    def _headers(self) -> dict[str, str]:
        settings = get_settings()
        api_key = (settings.dadata_api_key or "").strip()
        if not api_key:
            raise RuntimeError("DADATA_API_KEY is not set")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {api_key}",
        }
        secret = (settings.dadata_secret_key or "").strip()
        if secret:
            headers["X-Secret"] = secret
        return headers

    def find_by_inn(self, inn: str) -> list[dict[str, Any]]:
        inn_n = normalize_inn(inn)
        if not inn_n:
            raise ValueError("INN must be 10 or 12 digits")
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                PARTY_FIND_URL,
                headers=self._headers(),
                json={"query": inn_n},
            )
            response.raise_for_status()
            data = response.json()
        suggestions = data.get("suggestions") if isinstance(data, dict) else None
        if not isinstance(suggestions, list):
            return []
        return [s for s in suggestions if isinstance(s, dict)]

    def suggest_parties(self, query: str, *, count: int = 5) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                PARTY_SUGGEST_URL,
                headers=self._headers(),
                json={"query": q, "count": max(1, min(20, count))},
            )
            response.raise_for_status()
            data = response.json()
        suggestions = data.get("suggestions") if isinstance(data, dict) else None
        if not isinstance(suggestions, list):
            return []
        return [s for s in suggestions if isinstance(s, dict)]
