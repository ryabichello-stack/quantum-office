"""Canonical /api/v1 facade — wraps modules without breaking /api/modules/*."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query


def build_v1_router(*, require_auth: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "api": "v1", "service": "ava-outreach"}

    @router.get("/accounts")
    def list_accounts(
        q: str | None = None, limit: int = Query(50, ge=1, le=200)
    ) -> dict[str, Any]:
        from modules.accounts import AccountStore

        return {"ok": True, "items": AccountStore().list_accounts(q=q, limit=limit)}

    @router.get("/accounts/{account_id}")
    def get_account(account_id: str) -> dict[str, Any]:
        from modules.accounts import AccountStore
        from company_card import build_company_card

        store = AccountStore()
        acc = store.get_account(account_id)
        if not acc:
            raise HTTPException(404, "account_not_found")
        card = None
        bx = (acc.get("bitrix_company_id") or "").strip()
        if bx:
            try:
                card = build_company_card(bx)
            except Exception:  # noqa: BLE001
                card = None
        return {
            "ok": True,
            "account": acc,
            "timeline": store.timeline(account_id, limit=30),
            "company_card": card,
        }

    @router.get("/people")
    def list_people(
        account_id: str | None = None, limit: int = Query(50, ge=1, le=200)
    ) -> dict[str, Any]:
        from modules.accounts import AccountStore

        store = AccountStore()
        with store.connect() as conn:
            if account_id:
                rows = conn.execute(
                    """
                    SELECT p.* FROM people p
                    JOIN employments e ON e.person_id = p.id
                    WHERE p.tenant_id = ? AND e.account_id = ?
                    ORDER BY p.updated_at DESC LIMIT ?
                    """,
                    (store.tenant_id, account_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM people WHERE tenant_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (store.tenant_id, limit),
                ).fetchall()
        return {"ok": True, "items": [dict(r) for r in rows]}

    @router.get("/conversations")
    def conversations(
        unprocessed_only: bool = True, limit: int = Query(50, ge=1, le=200)
    ) -> dict[str, Any]:
        from modules.replies import ReplyInboxStore

        inbox = ReplyInboxStore()
        items = (
            inbox.list_unprocessed(limit)
            if unprocessed_only
            else inbox.list_recent(limit)
        )
        return {"ok": True, "counts": inbox.counts(), "items": items}

    @router.get("/conversations/{inbox_id}")
    def conversation(inbox_id: int) -> dict[str, Any]:
        from modules.replies.thread import build_inbox_thread

        out = build_inbox_thread(inbox_id)
        if not out.get("ok"):
            raise HTTPException(404, out.get("error") or "not_found")
        return out

    @router.get("/leads")
    def leads(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        from modules.accounts import AccountStore

        store = AccountStore()
        with store.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM leads WHERE tenant_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (store.tenant_id, limit),
            ).fetchall()
        return {"ok": True, "items": [dict(r) for r in rows]}

    return router
