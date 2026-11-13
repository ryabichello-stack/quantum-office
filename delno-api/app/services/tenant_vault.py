"""Tenant secrets vault (settings.secrets) — never echo plaintext back."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.audit import write_audit
from app.services.events import emit_event

SUPPORTED_KINDS = frozenset(
    {
        "mango_sip",
        "files_yadisk",
        "files_mailru",
        "files_gdrive",
        "files_onedrive",
        "telegram_bot",
    }
)

CLOUD_KINDS = frozenset(
    {
        "files_yadisk",
        "files_mailru",
        "files_gdrive",
        "files_onedrive",
    }
)
FOREIGN_CLOUD_KINDS = frozenset({"files_gdrive", "files_onedrive"})

MANGO_SIP_FORM = {
    "kind": "mango_sip",
    "title": "SIP Mango — безопасный ввод",
    "hint": "Пароль не попадёт в ленту чата. Сохраняется только в кабинете tenant.",
    "fields": [
        {"name": "login", "label": "Логин / extension", "type": "text", "autocomplete": "username"},
        {"name": "password", "label": "SIP-пароль", "type": "password", "autocomplete": "current-password"},
    ],
    "submit_label": "Сохранить безопасно",
    "password_required": True,
    "login_optional": False,
}

CHANNEL_FORMS: dict[str, dict[str, Any]] = {
    "telegram_bot": {
        "kind": "telegram_bot",
        "title": "Telegram bot — токен",
        "hint": "Токен от @BotFather. В чат не попадёт; Hermес подключит branded webhook для tenant.",
        "fields": [
            {
                "name": "password",
                "label": "Bot token",
                "type": "password",
                "autocomplete": "off",
            }
        ],
        "submit_label": "Подключить Telegram",
        "password_required": True,
        "login_optional": True,
        "require_foreign_consent": False,
    },
}

CLOUD_FORMS: dict[str, dict[str, Any]] = {
    "files_yadisk": {
        "kind": "files_yadisk",
        "title": "Яндекс.Диск — токен",
        "hint": "OAuth-токен Диска. В чат не попадёт. Хранение в РФ у Яндекса + кэш у DELNO в вашем тенанте.",
        "fields": [
            {
                "name": "password",
                "label": "OAuth-токен Яндекс.Диска",
                "type": "password",
                "autocomplete": "off",
            }
        ],
        "submit_label": "Подключить Диск",
        "password_required": True,
        "login_optional": True,
        "require_foreign_consent": False,
    },
    "files_mailru": {
        "kind": "files_mailru",
        "title": "Облако Mail.ru — WebDAV",
        "hint": "Логин и пароль приложения WebDAV. В чат не попадут.",
        "fields": [
            {"name": "login", "label": "Логин Mail.ru", "type": "text", "autocomplete": "username"},
            {
                "name": "password",
                "label": "Пароль приложения / WebDAV",
                "type": "password",
                "autocomplete": "current-password",
            },
        ],
        "submit_label": "Подключить Mail.ru",
        "password_required": True,
        "login_optional": False,
        "require_foreign_consent": False,
    },
    "files_gdrive": {
        "kind": "files_gdrive",
        "title": "Google Drive — токен",
        "hint": "Access token Google. Данные обрабатываются у Google вне РФ — нужно согласие.",
        "fields": [
            {
                "name": "password",
                "label": "Google Drive access token",
                "type": "password",
                "autocomplete": "off",
            }
        ],
        "submit_label": "Подключить Google Drive",
        "password_required": True,
        "login_optional": True,
        "require_foreign_consent": True,
        "consent_label": (
            "Понимаю, что файлы Google Drive обрабатываются у Google вне РФ "
            "на условиях Google; DELNO хранит только токен и кэш в моём тенанте."
        ),
    },
    "files_onedrive": {
        "kind": "files_onedrive",
        "title": "OneDrive — токен",
        "hint": "Microsoft Graph token. Данные у Microsoft вне РФ — нужно согласие.",
        "fields": [
            {
                "name": "password",
                "label": "OneDrive / Graph access token",
                "type": "password",
                "autocomplete": "off",
            }
        ],
        "submit_label": "Подключить OneDrive",
        "password_required": True,
        "login_optional": True,
        "require_foreign_consent": True,
        "consent_label": (
            "Понимаю, что OneDrive обрабатывается у Microsoft вне РФ; "
            "DELNO хранит только токен и кэш в моём тенанте."
        ),
    },
}


def credential_form_spec(kind: str = "mango_sip", *, prefill: dict[str, str] | None = None) -> dict[str, Any]:
    kind = (kind or "mango_sip").strip()
    if kind in CLOUD_FORMS:
        form = dict(CLOUD_FORMS[kind])
    elif kind in CHANNEL_FORMS:
        form = dict(CHANNEL_FORMS[kind])
    elif kind == "mango_sip":
        form = dict(MANGO_SIP_FORM)
    else:
        # Unknown kinds fall back to SIP form shape but keep requested kind label only
        # when supported; otherwise mango_sip (legacy callers).
        form = dict(MANGO_SIP_FORM)
        if kind in SUPPORTED_KINDS:
            form["kind"] = kind
    if prefill:
        safe = {}
        if prefill.get("login"):
            safe["login"] = prefill["login"][:120]
        form["prefill"] = safe
    return form


def looks_like_credential_paste(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) > 400:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1:
        s = lines[0]
        if " " in s or len(s) < 8:
            return False
        classes = sum(
            [
                any(c.islower() for c in s),
                any(c.isupper() for c in s),
                any(c.isdigit() for c in s),
                any(not c.isalnum() for c in s),
            ]
        )
        return classes >= 3 and not any(w in s.lower() for w in ("http", "www.", ".ru", ".com"))
    if 2 <= len(lines) <= 4:
        joined = " ".join(lines).lower()
        if any(w in joined for w in ("добавь", "найди", "какой", "скажи", "привет", "настрой")):
            return False
        pw = max(lines, key=len)
        return len(pw) >= 6 and " " not in pw
    return False


def parse_credential_paste(message: str) -> dict[str, str]:
    lines = [ln.strip() for ln in (message or "").splitlines() if ln.strip()]
    if not lines:
        return {}
    if len(lines) == 1:
        return {"password": lines[0][:200]}
    return {"login": lines[0][:120], "password": lines[-1][:200]}


def wants_sip_secret_form(message: str) -> bool:
    lower = (message or "").lower()
    if looks_like_credential_paste(message):
        return True
    keys = (
        "sip-пароль",
        "sip пароль",
        "пароль mango",
        "пароль манго",
        "mango sip",
        "sip mango",
        "дай форму",
        "дай-ка форму",
        "пришли форму",
        "скинь форму",
        "открой форму",
        "покажи форму",
        "форму для",
        "форму sip",
        "форму логин",
        "безопасн",
        "введу логин",
        "введу пароль",
        "ввести логин",
        "ввести пароль",
    )
    if any(k in lower for k in keys):
        # Don't steal cloud-connect phrases into SIP form
        if any(k in lower for k in ("яндекс", "yadisk", "mail.ru", "google", "onedrive", "диск", "облак")):
            if "sip" not in lower and "mango" not in lower and "манго" not in lower:
                return False
        return True
    if "форм" in lower and any(
        k in lower for k in ("логин", "парол", "sip", "mango", "манго", "телефон", "секрет", "введ")
    ):
        if any(k in lower for k in ("яндекс", "google", "onedrive", "mail.ru", "облак")):
            if "sip" not in lower and "mango" not in lower and "манго" not in lower:
                return False
        return True
    if "пароль" in lower and any(k in lower for k in ("sip", "mango", "манго", "линии", "телефон")):
        return True
    if "логин" in lower and any(k in lower for k in ("sip", "mango", "манго", "телефон", "форм", "секрет")):
        return True
    return False


def list_secret_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    blob = settings.get("secrets") if isinstance(settings.get("secrets"), dict) else {}
    items = []
    for kind in sorted(SUPPORTED_KINDS):
        row = blob.get(kind) if isinstance(blob.get(kind), dict) else {}
        items.append(
            {
                "kind": kind,
                "configured": bool(row.get("password") or row.get("login")),
                "login_masked": _mask(str(row.get("login") or "")),
                "foreign_consent": bool(row.get("foreign_consent_at")),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"items": items}


def save_secret(
    db: Session,
    ctx: TenantContext,
    *,
    kind: str,
    login: str | None = None,
    password: str | None = None,
    foreign_consent: bool = False,
) -> dict[str, Any]:
    kind = (kind or "").strip()
    if kind not in SUPPORTED_KINDS:
        return {"ok": False, "error": "unsupported_kind"}
    login_s = (login or "").strip()
    password_s = (password or "").strip()
    max_pw = 4096 if kind in CLOUD_KINDS or kind in CHANNEL_FORMS else 200
    if not login_s and not password_s:
        return {"ok": False, "error": "empty"}
    if kind == "files_mailru" and not login_s:
        return {"ok": False, "error": "login_required"}
    if kind == "telegram_bot" and not password_s:
        return {"ok": False, "error": "password_required"}
    if password_s and len(password_s) < 4:
        return {"ok": False, "error": "password_too_short"}
    if kind in FOREIGN_CLOUD_KINDS and not foreign_consent:
        return {"ok": False, "error": "foreign_consent_required"}

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    blob = dict(settings.get("secrets") or {})
    current = dict(blob.get(kind) or {})
    old_public = {
        "login_masked": _mask(str(current.get("login") or "")),
        "has_password": bool(current.get("password")),
        "foreign_consent": bool(current.get("foreign_consent_at")),
    }
    if login_s:
        current["login"] = login_s[:120]
    if password_s:
        current["password"] = password_s[:max_pw]
    if kind in FOREIGN_CLOUD_KINDS and foreign_consent:
        current["foreign_consent_at"] = datetime.now(timezone.utc).isoformat()
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    blob[kind] = current
    settings["secrets"] = blob
    tenant.settings = settings

    write_audit(
        db,
        ctx,
        action="secrets.save",
        resource=f"secret:{kind}",
        old_value=old_public,
        new_value={
            "login_masked": _mask(str(current.get("login") or "")),
            "has_password": bool(current.get("password")),
            "foreign_consent": bool(current.get("foreign_consent_at")),
        },
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="secrets.updated",
        category="operational",
        source="tenant.secrets",
        payload={"kind": kind, "configured": True},
    )
    db.commit()
    if kind == "telegram_bot":
        msg = "Токен Telegram сохранён. В чат не попал."
    elif kind in CLOUD_KINDS:
        msg = "Данные сохранены в сейфе тенанта. В чат не попали."
    else:
        msg = "SIP-данные сохранены в кабинете. В чат не попали."
    out: dict[str, Any] = {
        "ok": True,
        "kind": kind,
        "configured": True,
        "login_masked": _mask(str(current.get("login") or "")),
        "message": msg,
    }
    if kind == "telegram_bot":
        try:
            from app.services.telegram_connect import connect_telegram_branded

            connected = connect_telegram_branded(db, ctx, str(current.get("password") or ""))
            out["channel_connect"] = {
                k: connected.get(k)
                for k in ("ok", "error", "account", "bot", "username", "message_ru", "webhook")
                if k in connected or connected.get(k) is not None
            }
            if connected.get("ok"):
                account = connected.get("account") if isinstance(connected.get("account"), dict) else {}
                bot = account.get("bot_username") or ""
                out["message"] = (
                    f"Telegram бот подключён{(' @' + str(bot).lstrip('@')) if bot else ''}. "
                    "Токен в чат не попал."
                )
            else:
                out["message"] = (
                    "Токен сохранён в сейфе, но подключить канал не удалось: "
                    + str(connected.get("error") or connected.get("message_ru") or "ошибка")
                )
        except Exception as exc:  # noqa: BLE001
            out["channel_connect"] = {"ok": False, "error": "telegram_connect_failed"}
            out["message"] = f"Токен сохранён, connect упал: {str(exc)[:120]}"
    if kind == "mango_sip":
        try:
            from app.services.sip_probe import after_vault_sip_save

            probe = after_vault_sip_save(tenant_slug=ctx.tenant_slug, login=current.get("login"), password=current.get("password"))
            out["sip_probe"] = {
                k: probe.get(k)
                for k in (
                    "ok",
                    "skipped",
                    "applied",
                    "message_ru",
                    "registration",
                    "next_actions",
                    "cursor_task",
                    "error",
                )
                if k in probe
            }
            if probe.get("message_ru"):
                out["message"] = (out["message"] + " " + str(probe.get("message_ru"))).strip()
        except Exception:  # noqa: BLE001
            __import__("logging").getLogger(__name__).exception("sip probe after vault save failed")
    elif kind in CLOUD_KINDS:
        try:
            from app.services.files_cloud import after_vault_cloud_save

            cloud = after_vault_cloud_save(db, ctx, kind=kind)
            out["cloud_probe"] = {
                k: cloud.get(k)
                for k in ("source", "title", "probe", "message_ru")
                if k in cloud
            }
            if cloud.get("message_ru"):
                out["message"] = (out["message"] + " " + str(cloud.get("message_ru"))).strip()
        except Exception:  # noqa: BLE001
            __import__("logging").getLogger(__name__).exception("cloud probe after vault save failed")
    return out


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    if "/" in value:
        left, _, right = value.partition("/")
        return f"{left[:2]}***/{right[:1]}***" if right else f"{left[:2]}***"
    return f"{value[:2]}***{value[-1]}"
