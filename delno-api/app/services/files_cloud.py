"""Per-tenant cloud disk connections (Yandex / Mail.ru / Google / OneDrive).

Credentials live in tenant vault (`files_*` kinds). Files broker receives
optional per-request overrides so SaaS tenants do not share one env token.
Foreign clouds (gdrive/onedrive) require explicit consent (152‑FZ).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import get_connector
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.connectors import connector_config_for, update_tenant_connector
from app.services.events import emit_event

CLOUD_SOURCES: dict[str, dict[str, Any]] = {
    "yadisk": {
        "vault_kind": "files_yadisk",
        "title": "Яндекс.Диск",
        "residency": "ru",
        "auth": "token",
        "hint": "OAuth-токен Яндекс.Диска (не пароль от Яндекс ID в чат).",
    },
    "mailru": {
        "vault_kind": "files_mailru",
        "title": "Облако Mail.ru",
        "residency": "ru",
        "auth": "webdav",
        "hint": "Логин и пароль приложения WebDAV Облака Mail.ru.",
    },
    "gdrive": {
        "vault_kind": "files_gdrive",
        "title": "Google Drive",
        "residency": "foreign",
        "auth": "token",
        "hint": "Access token Google Drive. Данные у Google вне РФ — нужно согласие.",
    },
    "onedrive": {
        "vault_kind": "files_onedrive",
        "title": "OneDrive",
        "residency": "foreign",
        "auth": "token",
        "hint": "Microsoft Graph / OneDrive token. Данные у Microsoft вне РФ — нужно согласие.",
    },
}

SOURCE_BY_VAULT = {v["vault_kind"]: k for k, v in CLOUD_SOURCES.items()}
FOREIGN_SOURCES = frozenset(k for k, v in CLOUD_SOURCES.items() if v["residency"] == "foreign")


def normalize_source(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()
    aliases = {
        "yandex": "yadisk",
        "yandex_disk": "yadisk",
        "яндекс": "yadisk",
        "яндекс.диск": "yadisk",
        "ядиск": "yadisk",
        "mail": "mailru",
        "mail.ru": "mailru",
        "мейл": "mailru",
        "google": "gdrive",
        "google_drive": "gdrive",
        "гугл": "gdrive",
        "гугл диск": "gdrive",
        "one_drive": "onedrive",
        "вандрайв": "onedrive",
    }
    if s in CLOUD_SOURCES:
        return s
    return aliases.get(s)


def detect_source_from_message(message: str) -> str | None:
    lower = (message or "").lower()
    checks = (
        (("яндекс", "yadisk", "yandex", "я.диск", "ядиск"), "yadisk"),
        (("mail.ru", "mailru", "мейл", "облако mail"), "mailru"),
        (("google", "gdrive", "гугл"), "gdrive"),
        (("onedrive", "one drive", "вандрайв", "microsoft"), "onedrive"),
    )
    for keys, source in checks:
        if any(k in lower for k in keys):
            return source
    return None


def _secrets_blob(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    raw = settings.get("secrets")
    return raw if isinstance(raw, dict) else {}


def cloud_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    blob = _secrets_blob(tenant)
    items = []
    for source, meta in CLOUD_SOURCES.items():
        kind = meta["vault_kind"]
        row = blob.get(kind) if isinstance(blob.get(kind), dict) else {}
        configured = bool(row.get("password") or (meta["auth"] == "webdav" and row.get("login")))
        foreign_ok = bool(row.get("foreign_consent_at")) if source in FOREIGN_SOURCES else True
        items.append(
            {
                "source": source,
                "vault_kind": kind,
                "title": meta["title"],
                "residency": meta["residency"],
                "configured": configured,
                "foreign_consent": foreign_ok,
                "ready": configured and foreign_ok,
                "login_masked": _mask(str(row.get("login") or "")),
                "updated_at": row.get("updated_at"),
            }
        )
    ready_n = sum(1 for i in items if i["ready"])
    return {
        "ok": True,
        "ready_count": ready_n,
        "items": items,
        "message_ru": (
            f"Подключено облаков: {ready_n}. "
            "Рекомендуем Яндекс.Диск или Mail.ru (РФ). Google/OneDrive — только с согласием."
        ),
    }


def credentials_for_source(db: Session, ctx: TenantContext, source: str) -> dict[str, str] | None:
    src = normalize_source(source) or source
    meta = CLOUD_SOURCES.get(src)
    if not meta:
        return None
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    row = _secrets_blob(tenant).get(meta["vault_kind"])
    if not isinstance(row, dict):
        return None
    if src in FOREIGN_SOURCES and not row.get("foreign_consent_at"):
        return None
    if meta["auth"] == "webdav":
        user = str(row.get("login") or "").strip()
        password = str(row.get("password") or "").strip()
        if not (user and password):
            return None
        return {"username": user, "password": password}
    token = str(row.get("password") or "").strip()
    if not token:
        return None
    return {"token": token}


def ensure_files_connector_enabled(db: Session, ctx: TenantContext) -> None:
    cfg = connector_config_for(db, ctx, "files")
    if cfg.get("enabled"):
        return
    update_tenant_connector(db, ctx, "files", enabled=True)


def after_vault_cloud_save(
    db: Session,
    ctx: TenantContext,
    *,
    kind: str,
) -> dict[str, Any]:
    source = SOURCE_BY_VAULT.get(kind)
    if not source:
        return {}
    ensure_files_connector_enabled(db, ctx)
    probe = probe_cloud_list(db, ctx, source=source, path="/")
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="files.cloud.connected",
        category="operational",
        source="tenant.vault",
        payload={"cloud": source, "probe_ok": bool(probe.get("ok"))},
    )
    db.commit()
    return {
        "source": source,
        "title": CLOUD_SOURCES[source]["title"],
        "probe": probe,
        "message_ru": probe.get("message_ru")
        or f"{CLOUD_SOURCES[source]['title']} сохранён в сейфе тенанта.",
    }


def probe_cloud_list(
    db: Session,
    ctx: TenantContext,
    *,
    source: str,
    path: str = "/",
) -> dict[str, Any]:
    src = normalize_source(source) or source
    meta = CLOUD_SOURCES.get(src)
    if not meta:
        return {"ok": False, "error": "unknown_source", "message_ru": "Неизвестный источник облака."}
    creds = credentials_for_source(db, ctx, src)
    if not creds:
        if src in FOREIGN_SOURCES:
            return {
                "ok": False,
                "error": "consent_or_creds_missing",
                "message_ru": (
                    f"{meta['title']} ещё не готов: нужен токен и явное согласие "
                    "на обработку у зарубежного провайдера."
                ),
            }
        return {
            "ok": False,
            "error": "not_configured",
            "message_ru": f"{meta['title']} ещё не подключён — откройте безопасную форму." ,
        }

    connector = get_connector("files")
    if not connector:
        return {"ok": False, "error": "no_connector"}
    config = dict(connector_config_for(db, ctx, "files"))
    config["enabled"] = True
    config["_request_credentials"] = creds
    result = connector.list_entries(  # type: ignore[attr-defined]
        tenant_slug=ctx.tenant_slug,
        config=config,
        source=src,
        path=path or "/",
    )
    upstream = (result.data or {}).get("upstream") if isinstance(result.data, dict) else {}
    counts = (upstream or {}).get("counts") if isinstance(upstream, dict) else {}
    ok = bool(result.ok) and not result.error
    if result.error == "not_configured" or (result.data or {}).get("stub"):
        # Upstream broker missing — still mark vault as saved; list later.
        return {
            "ok": True,
            "deferred": True,
            "source": src,
            "message_ru": (
                f"Креды {meta['title']} сохранены. Брокер файлов пока stub/недоступен — "
                "список появится после FILES_BASE_URL."
            ),
            "status": result.as_dict(),
        }
    if not ok:
        return {
            "ok": False,
            "source": src,
            "error": result.error or "list_failed",
            "message_ru": (
                f"Не удалось прочитать {meta['title']}: {result.message or result.error}. "
                "Проверьте токен/пароль."
            ),
            "status": result.as_dict(),
        }
    total = (counts or {}).get("total")
    return {
        "ok": True,
        "source": src,
        "counts": counts or {},
        "message_ru": (
            f"{meta['title']} отвечает. В корне: {total if total is not None else 'записи есть'}."
        ),
        "status": result.as_dict(),
        "next_actions": [
            {"title": "Список", "text": f"Покажи файлы на {meta['title']}"},
            {"title": "Другое облако", "text": "Подключи Яндекс.Диск"},
            {"title": "Статус облаков", "text": "Какие облака подключены"},
        ],
    }


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[:2]}***{value[-1]}"


def stamp_foreign_consent(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["foreign_consent_at"] = datetime.now(timezone.utc).isoformat()
    return out
