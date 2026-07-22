"""Bitrix24 REST client via incoming webhook (crm scope)."""

from __future__ import annotations

import logging
import re
from typing import Any, Iterator
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("ava-outreach.bitrix")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_DIGITS_RE = re.compile(r"\D+")


def normalize_phone(value: Any) -> str | None:
    """Return digits-only phone; keep leading country code when present."""
    if value is None:
        return None
    if isinstance(value, dict):
        return normalize_phone(value.get("VALUE") or value.get("value"))
    if isinstance(value, list):
        for item in value:
            found = normalize_phone(item)
            if found:
                return found
        return None
    digits = _PHONE_DIGITS_RE.sub("", str(value))
    if len(digits) < 10:
        return None
    # RU local 10-digit → 7XXXXXXXXXX
    if len(digits) == 10 and digits[0] == "9":
        digits = "7" + digits
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    return digits


def extract_phones_from_fields(fields: dict[str, Any]) -> list[str]:
    phones: list[str] = []
    seen: set[str] = set()
    for key in ("PHONE", "phone", "UF_PHONE"):
        if key not in fields:
            continue
        raw = fields[key]
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            phone = normalize_phone(item)
            if phone and phone not in seen:
                seen.add(phone)
                phones.append(phone)
    return phones


# Bitrix list select: all standard fields + user fields + multi-fields.
# Narrow selects previously dropped INN/requisites and most CRM columns.
_SELECT_ALL = ["*", "UF_*", "EMAIL", "PHONE", "WEB", "IM"]
_SELECT_REQUISITE_ALL = ["*"]

# crm.enum.ownertype
OWNER_LEAD = 1
OWNER_DEAL = 2
OWNER_CONTACT = 3
OWNER_COMPANY = 4

# crm.enum.activitytype
ACTIVITY_EMAIL = 4

# Direction: 2 = outgoing
DIRECTION_OUTGOING = 2


def normalize_email(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            found = normalize_email(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        return normalize_email(value.get("VALUE") or value.get("value"))
    text = str(value).strip().lower()
    text = text.strip("<>\"' ")
    if not text or not _EMAIL_RE.match(text):
        return None
    return text


def extract_emails_from_fields(fields: dict[str, Any]) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    for key in ("EMAIL", "email", "UF_EMAIL"):
        if key not in fields:
            continue
        raw = fields[key]
        candidates: list[Any]
        if isinstance(raw, list):
            candidates = raw
        else:
            candidates = [raw]
        for item in candidates:
            email = normalize_email(item)
            if email and email not in seen:
                seen.add(email)
                emails.append(email)
    return emails


def contact_display_name(fields: dict[str, Any]) -> str:
    parts = [
        str(fields.get("NAME") or "").strip(),
        str(fields.get("LAST_NAME") or "").strip(),
    ]
    name = " ".join(p for p in parts if p).strip()
    if name:
        return name
    company = str(fields.get("COMPANY_TITLE") or fields.get("POST") or "").strip()
    return company or "коллега"


def company_display_name(fields: dict[str, Any]) -> str:
    title = str(fields.get("TITLE") or "").strip()
    return title or "компания"


class BitrixClient:
    def __init__(self, webhook_url: str, *, timeout: float = 30.0) -> None:
        base = (webhook_url or "").strip()
        if not base:
            raise ValueError("BITRIX_WEBHOOK_URL is empty")
        if not base.endswith("/"):
            base += "/"
        self.base = base
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base, method.lstrip("/"))
        resp = self._client.post(url, json=params or {})
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"Bitrix error {data.get('error')}: {data.get('error_description')}")
        return data if isinstance(data, dict) else {"result": data}

    def _list_crm(
        self,
        method: str,
        *,
        select: list[str],
        page_size: int = 50,
        filter_params: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        start = 0
        while True:
            params: dict[str, Any] = {
                "select": select,
                "start": start,
                "order": {"ID": "ASC"},
            }
            if filter_params:
                params["filter"] = filter_params
            payload = self.call(method, params)
            items = payload.get("result") or []
            if not isinstance(items, list):
                break
            for item in items:
                if isinstance(item, dict):
                    yield item
            next_start = payload.get("next")
            if next_start is None:
                break
            start = int(next_start)
            if page_size and len(items) == 0:
                break

    def list_contacts(self, *, page_size: int = 50) -> Iterator[dict[str, Any]]:
        """All contact fields (standard + UF_* + EMAIL/PHONE/WEB/IM)."""
        yield from self._list_crm(
            "crm.contact.list", select=list(_SELECT_ALL), page_size=page_size
        )

    def list_companies(self, *, page_size: int = 50) -> Iterator[dict[str, Any]]:
        """All company fields (standard + UF_* + EMAIL/PHONE/WEB/IM)."""
        yield from self._list_crm(
            "crm.company.list", select=list(_SELECT_ALL), page_size=page_size
        )

    def list_requisites(self, *, page_size: int = 50) -> Iterator[dict[str, Any]]:
        """All CRM requisites (RQ_INN, OGRN, director fields, etc.)."""
        yield from self._list_crm(
            "crm.requisite.list",
            select=list(_SELECT_REQUISITE_ALL),
            page_size=page_size,
        )

    def list_company_field_names(self) -> list[str]:
        payload = self.call("crm.company.fields")
        result = payload.get("result") or {}
        return sorted(result.keys()) if isinstance(result, dict) else []

    def list_contact_field_names(self) -> list[str]:
        payload = self.call("crm.contact.fields")
        result = payload.get("result") or {}
        return sorted(result.keys()) if isinstance(result, dict) else []

    def list_requisite_field_names(self) -> list[str]:
        payload = self.call("crm.requisite.fields")
        result = payload.get("result") or {}
        return sorted(result.keys()) if isinstance(result, dict) else []

    def create_company(
        self,
        *,
        title: str,
        email: str | None = None,
        phone: str | None = None,
        assigned_by_id: int | None = None,
        industry: str | None = None,
    ) -> int:
        fields: dict[str, Any] = {
            "TITLE": title,
            "OPENED": "Y",
        }
        if email:
            fields["EMAIL"] = [{"VALUE": email, "VALUE_TYPE": "WORK"}]
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
        if assigned_by_id:
            fields["ASSIGNED_BY_ID"] = int(assigned_by_id)
        if industry:
            fields["INDUSTRY"] = industry
        payload = self.call("crm.company.add", {"fields": fields})
        return int(payload["result"])

    def create_contact(
        self,
        *,
        name: str,
        last_name: str = "",
        phone: str | None = None,
        email: str | None = None,
        company_id: str | int | None = None,
        assigned_by_id: int | None = None,
    ) -> int:
        name = (name or "").strip() or "Клиент"
        fields: dict[str, Any] = {
            "NAME": name,
            "OPENED": "Y",
        }
        if last_name:
            fields["LAST_NAME"] = last_name.strip()
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
        if email:
            fields["EMAIL"] = [{"VALUE": email, "VALUE_TYPE": "WORK"}]
        if company_id:
            fields["COMPANY_ID"] = int(company_id)
        if assigned_by_id:
            fields["ASSIGNED_BY_ID"] = int(assigned_by_id)
        payload = self.call("crm.contact.add", {"fields": fields})
        return int(payload["result"])

    def find_contacts_by_phone(self, phone: str) -> list[dict[str, Any]]:
        phone_n = normalize_phone(phone)
        if not phone_n:
            return []
        # Prefer duplicate API
        try:
            payload = self.call(
                "crm.duplicate.findbycomm",
                {"type": "PHONE", "values": [phone_n], "entity_type": "CONTACT"},
            )
            result = payload.get("result") or {}
            ids = []
            if isinstance(result, dict):
                ids = result.get("CONTACT") or result.get("contact") or []
            out: list[dict[str, Any]] = []
            for cid in ids:
                got = self.call("crm.contact.get", {"id": int(cid)}).get("result")
                if isinstance(got, dict):
                    out.append(got)
            if out:
                return out
        except Exception:  # noqa: BLE001
            logger.debug("findbycomm phone failed", exc_info=True)
        return []

    def find_contacts_by_email(self, email: str) -> list[dict[str, Any]]:
        email_n = normalize_email(email)
        if not email_n:
            return []
        try:
            payload = self.call(
                "crm.duplicate.findbycomm",
                {"type": "EMAIL", "values": [email_n], "entity_type": "CONTACT"},
            )
            result = payload.get("result") or {}
            ids = []
            if isinstance(result, dict):
                ids = result.get("CONTACT") or result.get("contact") or []
            out: list[dict[str, Any]] = []
            for cid in ids:
                got = self.call("crm.contact.get", {"id": int(cid)}).get("result")
                if isinstance(got, dict):
                    out.append(got)
            return out
        except Exception:  # noqa: BLE001
            logger.debug("findbycomm email failed", exc_info=True)
        return []

    def find_company_by_title(self, title: str) -> dict[str, Any] | None:
        title_n = (title or "").strip()
        if not title_n:
            return None
        payload = self.call(
            "crm.company.list",
            {
                "filter": {"=TITLE": title_n},
                "select": ["ID", "TITLE", "EMAIL", "PHONE"],
                "start": 0,
            },
        )
        items = payload.get("result") or []
        if items and isinstance(items[0], dict):
            return items[0]
        # loose contains
        payload = self.call(
            "crm.company.list",
            {
                "filter": {"%TITLE": title_n},
                "select": ["ID", "TITLE"],
                "start": 0,
            },
        )
        items = payload.get("result") or []
        return items[0] if items and isinstance(items[0], dict) else None

    def find_open_deals_for_contact(
        self,
        contact_id: str | int,
        *,
        source_id: str | None = "CALL",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        filt: dict[str, Any] = {
            "CONTACT_ID": int(contact_id),
            "CLOSED": "N",
        }
        if source_id:
            filt["SOURCE_ID"] = source_id
        payload = self.call(
            "crm.deal.list",
            {
                "filter": filt,
                "select": ["ID", "TITLE", "STAGE_ID", "COMPANY_ID", "CONTACT_ID", "DATE_CREATE"],
                "order": {"ID": "DESC"},
                "start": 0,
            },
        )
        items = payload.get("result") or []
        return [i for i in items[:limit] if isinstance(i, dict)]

    def create_deal(
        self,
        *,
        title: str,
        assigned_by_id: int,
        company_id: str | int | None = None,
        contact_id: str | int | None = None,
        stage_id: str = "NEW",
        comments: str = "",
        source_id: str = "EMAIL",
    ) -> int:
        fields: dict[str, Any] = {
            "TITLE": title,
            "STAGE_ID": stage_id,
            "ASSIGNED_BY_ID": int(assigned_by_id),
            "OPENED": "Y",
            "SOURCE_ID": source_id,
        }
        if company_id:
            fields["COMPANY_ID"] = int(company_id)
        if contact_id:
            fields["CONTACT_ID"] = int(contact_id)
        if comments:
            fields["COMMENTS"] = comments
        payload = self.call("crm.deal.add", {"fields": fields})
        return int(payload["result"])

    def create_task(
        self,
        *,
        title: str,
        description: str = "",
        responsible_id: int = 1,
        priority: str = "1",
        crm_company_id: str | int | None = None,
        crm_deal_id: str | int | None = None,
        crm_contact_id: str | int | None = None,
    ) -> int | None:
        """Create Bitrix task for sales follow-up. Returns task id or None."""
        fields: dict[str, Any] = {
            "TITLE": title[:255],
            "DESCRIPTION": description[:5000],
            "RESPONSIBLE_ID": int(responsible_id),
            "PRIORITY": str(priority),  # 2=high in many portals; 1=normal
        }
        uf: list[str] = []
        if crm_deal_id:
            uf.append(f"D_{int(crm_deal_id)}")
        if crm_company_id:
            uf.append(f"CO_{int(crm_company_id)}")
        if crm_contact_id:
            uf.append(f"C_{int(crm_contact_id)}")
        if uf:
            fields["UF_CRM_TASK"] = uf
        try:
            payload = self.call("tasks.task.add", {"fields": fields})
            result = payload.get("result") or {}
            if isinstance(result, dict):
                task = result.get("task") or result
                tid = task.get("id") if isinstance(task, dict) else result.get("ID")
                if tid is not None:
                    return int(tid)
            if result:
                return int(result)  # type: ignore[arg-type]
        except Exception:
            logger = __import__("logging").getLogger("ava-outreach.bitrix")
            logger.warning("tasks.task.add failed", exc_info=True)
        return None

    def add_email_activity(
        self,
        *,
        deal_id: str | int,
        subject: str,
        body: str,
        to_email: str,
        from_email: str,
        company_id: str | int | None = None,
        responsible_id: int | None = None,
        html: bool = False,
    ) -> int:
        """DEPRECATED — Bitrix CRM_EMAIL *sends* real mail (IS_MESSAGE_SENT).

        Keep for debugging only. Outreach logging must use timeline/comments.
        """
        fields: dict[str, Any] = {
            "OWNER_TYPE_ID": OWNER_DEAL,
            "OWNER_ID": int(deal_id),
            "TYPE_ID": ACTIVITY_EMAIL,
            "SUBJECT": subject,
            "DESCRIPTION": body,
            "DESCRIPTION_TYPE": 3 if html else 1,  # 1=text, 3=html
            "DIRECTION": DIRECTION_OUTGOING,
            "COMPLETED": "Y",
            "SETTINGS": {"MESSAGE_FROM": from_email},
        }
        if responsible_id:
            fields["RESPONSIBLE_ID"] = int(responsible_id)
        communications: list[dict[str, Any]] = [
            {
                "VALUE": to_email,
                "TYPE": "EMAIL",
            }
        ]
        if company_id:
            communications[0]["ENTITY_ID"] = int(company_id)
            communications[0]["ENTITY_TYPE_ID"] = OWNER_COMPANY
        fields["COMMUNICATIONS"] = communications
        payload = self.call("crm.activity.add", {"fields": fields})
        return int(payload["result"])

    def update_company(self, company_id: str | int, fields: dict[str, Any]) -> bool:
        payload = self.call(
            "crm.company.update",
            {"id": int(company_id), "fields": fields},
        )
        return bool(payload.get("result"))

    def update_requisite(self, requisite_id: str | int, fields: dict[str, Any]) -> bool:
        payload = self.call(
            "crm.requisite.update",
            {"id": int(requisite_id), "fields": fields},
        )
        return bool(payload.get("result"))

    def list_requisites_for_company(self, company_id: str | int) -> list[dict[str, Any]]:
        payload = self.call(
            "crm.requisite.list",
            {
                "filter": {
                    "ENTITY_TYPE_ID": OWNER_COMPANY,
                    "ENTITY_ID": int(company_id),
                },
                "select": ["*"],
            },
        )
        items = payload.get("result") or []
        return [i for i in items if isinstance(i, dict)]

    def add_timeline_comment(
        self,
        entity_id: str | int,
        comment: str,
        *,
        entity_type: str = "deal",
    ) -> None:
        self.call(
            "crm.timeline.comment.add",
            {
                "fields": {
                    "ENTITY_ID": int(entity_id),
                    "ENTITY_TYPE": entity_type,
                    "COMMENT": comment,
                }
            },
        )

    def smoke_contact_count(self) -> int:
        payload = self.call("crm.contact.list", {"select": ["ID"], "start": 0})
        total = payload.get("total")
        if total is not None:
            return int(total)
        result = payload.get("result") or []
        return len(result) if isinstance(result, list) else 0

    def smoke_company_count(self) -> int:
        payload = self.call("crm.company.list", {"select": ["ID"], "start": 0})
        total = payload.get("total")
        if total is not None:
            return int(total)
        result = payload.get("result") or []
        return len(result) if isinstance(result, list) else 0
