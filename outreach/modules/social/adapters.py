"""Social source adapters + capability matrix (Slice B)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Capability:
    source_id: str
    label: str
    search: bool = False
    import_only: bool = False
    manual: bool = False
    auto_dm: bool = False
    notes: str = ""


@dataclass
class AdapterHit:
    source: str
    full_name: str = ""
    role_guess: str = ""
    profile_url: str | None = None
    email: str | None = None
    phone: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


class SocialSourceAdapter(Protocol):
    source_id: str
    capability: Capability

    def search(
        self,
        *,
        bitrix_company_id: str | None,
        company_title: str,
        inn: str | None,
        roles: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> tuple[list[AdapterHit], float]:
        """Return hits + cost estimate (currency units arbitrary, logged)."""
        ...


class ClientsAdapter:
    source_id = "clients"
    capability = Capability(
        source_id="clients",
        label="Bitrix / local clients mirror",
        search=True,
        notes="Contacts already synced into clients.db",
    )

    def search(
        self,
        *,
        bitrix_company_id: str | None,
        company_title: str,
        inn: str | None,
        roles: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> tuple[list[AdapterHit], float]:
        from modules.clients import ClientsStore

        cid = (bitrix_company_id or "").strip()
        if not cid:
            return [], 0.0
        store = ClientsStore()
        hits: list[AdapterHit] = []
        with store.connect() as conn:
            rows = conn.execute(
                """
                SELECT bitrix_id, display_name, primary_email, post
                FROM contacts
                WHERE company_bitrix_id = ?
                ORDER BY display_name ASC
                LIMIT 40
                """,
                (cid,),
            ).fetchall()
        for r in rows:
            hits.append(
                AdapterHit(
                    source=self.source_id,
                    full_name=str(r["display_name"] or "").strip(),
                    role_guess=str(r["post"] or "").strip(),
                    email=(str(r["primary_email"] or "").strip().lower() or None),
                    evidence={
                        "bitrix_contact_id": r["bitrix_id"],
                        "company_bitrix_id": cid,
                    },
                )
            )
        return hits, 0.01 * max(1, len(hits))


class DaDataAdapter:
    source_id = "dadata"
    capability = Capability(
        source_id="dadata",
        label="DaData registry (director)",
        search=True,
        notes="Uses cached party by INN; no live call required for MVP",
    )

    def search(
        self,
        *,
        bitrix_company_id: str | None,
        company_title: str,
        inn: str | None,
        roles: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> tuple[list[AdapterHit], float]:
        from modules.clients import ClientsStore
        from modules.dadata import DaDataStore, normalize_inn

        inn_n = normalize_inn(inn)
        if not inn_n and bitrix_company_id:
            clients = ClientsStore()
            company = clients.get_company(bitrix_company_id)
            if company:
                inn_n = normalize_inn(company.get("inn"))
        if not inn_n:
            return [], 0.0
        party = DaDataStore().get(inn_n)
        if not party:
            return [], 0.05
        director = str(party.get("director_name") or "").strip()
        if not director:
            return [], 0.05
        post = str(party.get("director_post") or "генеральный директор").strip()
        return [
            AdapterHit(
                source=self.source_id,
                full_name=director,
                role_guess=post,
                evidence={"inn": inn_n, "company_name": party.get("company_name")},
            )
        ], 0.1


class WebImportAdapter:
    source_id = "web_import"
    capability = Capability(
        source_id="web_import",
        label="Web URL paste",
        import_only=True,
        manual=True,
        notes="Operator pastes profile URL — no scrape",
    )

    def search(
        self,
        *,
        bitrix_company_id: str | None,
        company_title: str,
        inn: str | None,
        roles: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> tuple[list[AdapterHit], float]:
        hits: list[AdapterHit] = []
        for item in imports:
            if (item.get("source") or "web_import") not in ("web_import", "web"):
                continue
            url = (item.get("profile_url") or item.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                AdapterHit(
                    source=self.source_id,
                    full_name=str(item.get("full_name") or "").strip(),
                    role_guess=str(item.get("role") or item.get("role_guess") or "").strip(),
                    profile_url=url,
                    email=(str(item.get("email") or "").strip().lower() or None),
                    evidence={"import": True},
                )
            )
        return hits, 0.0


class TelegramImportAdapter:
    source_id = "telegram"
    capability = Capability(
        source_id="telegram",
        label="Telegram username import",
        import_only=True,
        manual=True,
        notes="Stores @username / t.me link; no auto-DM",
    )

    def search(
        self,
        *,
        bitrix_company_id: str | None,
        company_title: str,
        inn: str | None,
        roles: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> tuple[list[AdapterHit], float]:
        hits: list[AdapterHit] = []
        for item in imports:
            if (item.get("source") or "") != "telegram":
                continue
            username = (item.get("username") or "").strip().lstrip("@")
            url = (item.get("profile_url") or "").strip()
            if not url and username:
                url = f"https://t.me/{username}"
            if not url and not username:
                continue
            hits.append(
                AdapterHit(
                    source=self.source_id,
                    full_name=str(item.get("full_name") or username or "").strip(),
                    role_guess=str(item.get("role") or "").strip(),
                    profile_url=url or None,
                    evidence={"username": username or None, "import": True},
                )
            )
        return hits, 0.0


class StubAdapter:
    """VK / OK / TenChat / LinkedIn — capability only until official API."""

    def __init__(self, source_id: str, label: str, *, notes: str = "") -> None:
        self.source_id = source_id
        self.capability = Capability(
            source_id=source_id,
            label=label,
            import_only=True,
            manual=True,
            auto_dm=False,
            notes=notes or "Stub: no automated search in v0",
        )

    def search(
        self,
        *,
        bitrix_company_id: str | None,
        company_title: str,
        inn: str | None,
        roles: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> tuple[list[AdapterHit], float]:
        hits: list[AdapterHit] = []
        for item in imports:
            if (item.get("source") or "") != self.source_id:
                continue
            url = (item.get("profile_url") or item.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                AdapterHit(
                    source=self.source_id,
                    full_name=str(item.get("full_name") or "").strip(),
                    role_guess=str(item.get("role") or "").strip(),
                    profile_url=url,
                    evidence={"import": True, "stub": True},
                )
            )
        return hits, 0.0


ADAPTERS: list[SocialSourceAdapter] = [
    ClientsAdapter(),
    DaDataAdapter(),
    WebImportAdapter(),
    TelegramImportAdapter(),
    StubAdapter("vk", "VK", notes="import_only / manual"),
    StubAdapter("ok", "Odnoklassniki", notes="import_only / manual"),
    StubAdapter("tenchat", "TenChat", notes="import_only / manual"),
    StubAdapter("linkedin", "LinkedIn", notes="import_only / manual — no unofficial scrape"),
]

_ADAPTER_BY_ID = {a.source_id: a for a in ADAPTERS}


def list_capabilities() -> list[dict[str, Any]]:
    out = []
    for a in ADAPTERS:
        c = a.capability
        out.append(
            {
                "source_id": c.source_id,
                "label": c.label,
                "search": c.search,
                "import_only": c.import_only,
                "manual": c.manual,
                "auto_dm": c.auto_dm,
                "notes": c.notes,
            }
        )
    return out


def run_adapters(
    *,
    source_ids: list[str],
    bitrix_company_id: str | None,
    company_title: str,
    inn: str | None,
    roles: list[dict[str, Any]],
    imports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    hits: list[dict[str, Any]] = []
    cost = 0.0
    for sid in source_ids:
        adapter = _ADAPTER_BY_ID.get(sid)
        if not adapter:
            continue
        try:
            batch, batch_cost = adapter.search(
                bitrix_company_id=bitrix_company_id,
                company_title=company_title,
                inn=inn,
                roles=roles,
                imports=imports,
            )
        except Exception:  # noqa: BLE001
            continue
        cost += float(batch_cost or 0)
        for h in batch:
            hits.append(
                {
                    "id": _new_id(),
                    "source": h.source,
                    "full_name": h.full_name,
                    "role_guess": h.role_guess,
                    "profile_url": h.profile_url,
                    "email": h.email,
                    "phone": h.phone,
                    "evidence": h.evidence,
                    "status": "proposed",
                }
            )
    return hits, cost
