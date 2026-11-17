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
        "max_bot",
        "calendar_yandex",
        "calendar_mailru",

        "calendar_google",
        "calendar_outlook",
        "mail_yandex",
        "mail_mailru",
        "mail_regru",
        "mail_google",
        "mail_outlook",
        "conference_yandex",
        "conference_google",
        "conference_zoom",
        "conference_teams",
    }
)

CALENDAR_KINDS = frozenset(
    {
        "calendar_yandex",
        "calendar_mailru",
        "calendar_google",
        "calendar_outlook",
    }
)
FOREIGN_CALENDAR_KINDS = frozenset({"calendar_google", "calendar_outlook"})
MAIL_KINDS = frozenset({"mail_yandex", "mail_mailru", "mail_regru", "mail_google", "mail_outlook"})
CONFERENCE_KINDS = frozenset(
    {"conference_yandex", "conference_google", "conference_zoom", "conference_teams"}
)
FOREIGN_MAIL_KINDS = frozenset({"mail_google", "mail_outlook"})
FOREIGN_CONFERENCE_KINDS = frozenset(
    {"conference_google", "conference_zoom", "conference_teams"}
)

_APP_PASSWORD_HELP = {
    "yandex": (
        "Пароль приложения, не обычный пароль: Яндекс ID → Безопасность → "
        "Пароли приложений → создать (тип «{what}»)."
    ),
    "mailru": (
        "Пароль для внешнего приложения, не обычный пароль: Mail.ru → Настройки → "
        "Безопасность → Пароли для внешних приложений → добавить."
    ),
}


def _account_form(kind: str, title: str, provider: str, what: str, example: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "title": title,
        "hint": (
            "Подключаю ваш собственный аккаунт. Сразу проверю его по-настоящему; "
            "в чат данные не попадут."
        ),
        "fields": [
            {
                "name": "login",
                "label": "Адрес почты",
                "type": "text",
                "autocomplete": "username",
                "placeholder": example,
                "help": f"Полный адрес, например {example}.",
            },
            {
                "name": "password",
                "label": "Пароль приложения",
                "type": "password",
                "autocomplete": "off",
                "help": _APP_PASSWORD_HELP[provider].format(what=what),
            },
        ],
        "submit_label": "Подключить и проверить",
        "password_required": True,
        "login_optional": False,
    }


ACCOUNT_FORMS: dict[str, dict[str, Any]] = {
    "calendar_yandex": _account_form(
        "calendar_yandex", "Яндекс Календарь", "yandex", "Календарь CalDAV", "ivan@yandex.ru"
    ),
    "calendar_mailru": _account_form(
        "calendar_mailru", "Календарь Mail.ru", "mailru", "Календарь", "ivan@mail.ru"
    ),
    "mail_yandex": _account_form("mail_yandex", "Яндекс Почта", "yandex", "Почта", "ivan@yandex.ru"),
    "mail_mailru": _account_form("mail_mailru", "Почта Mail.ru", "mailru", "Почта", "ivan@mail.ru"),
    "mail_regru": {
        "kind": "mail_regru",
        "title": "Почта Reg.ru / хостинг",
        "hint": (
            "Подключаю ящик на хостинге (например office@ваш-домен.ru через mail.hosting.reg.ru). "
            "Нужен пароль ящика или SMTP-пароль из панели хостинга; в чат данные не попадут."
        ),
        "fields": [
            {
                "name": "login",
                "label": "Адрес почты",
                "type": "text",
                "autocomplete": "username",
                "placeholder": "office@example.ru",
                "help": "Полный адрес ящика на хостинге, например office@dlno.ru.",
            },
            {
                "name": "password",
                "label": "Пароль ящика / SMTP",
                "type": "password",
                "autocomplete": "off",
                "help": "Пароль почтового ящика из панели Reg.ru (или отдельный SMTP-пароль, если задан).",
            },
        ],
        "submit_label": "Подключить и проверить",
        "password_required": True,
        "login_optional": False,
    },
}


CLOUD_KINDS = frozenset(
    {
        "files_yadisk",
        "files_mailru",
        "files_gdrive",
        "files_onedrive",
    }
)
FOREIGN_CLOUD_KINDS = frozenset({"files_gdrive", "files_onedrive"})
_FOREIGN_SECRET_KINDS = FOREIGN_CLOUD_KINDS | FOREIGN_CALENDAR_KINDS | FOREIGN_MAIL_KINDS | FOREIGN_CONFERENCE_KINDS
_LONG_SECRET_KINDS = CLOUD_KINDS | CALENDAR_KINDS | MAIL_KINDS | CONFERENCE_KINDS | frozenset(
    {"telegram_bot", "max_bot"}
)

MANGO_SIP_FORM = {
    "kind": "mango_sip",
    "title": "SIP Mango — безопасный ввод",
    "hint": (
        "Данные SIP-учётной записи сотрудника из личного кабинета Манго: логин вида "
        "сотрудник@vpbxНОМЕР.mangosip.ru или номер_аккаунта/сотрудник и SIP-пароль. "
        "В ленту чата они не попадут и сохранятся только в этом кабинете."
    ),
    "fields": [
        {
            "name": "login",
            "label": "SIP-логин сотрудника",
            "type": "text",
            "autocomplete": "username",
            "placeholder": "ivan@vpbx123456789.mangosip.ru",
            "help": (
                "SIP-адрес целиком, например ivan@vpbx123456789.mangosip.ru "
                "или 123456789/ivan."
            ),
        },
        {
            "name": "password",
            "label": "SIP-пароль",
            "type": "password",
            "autocomplete": "current-password",
            "help": (
                "СИП-пароль сотрудника: ЛК Манго → Сотрудники → карточка сотрудника → "
                "Телефония → учётная запись SIP → «Показать». "
                "Пароль от личного кабинета не подойдёт."
            ),
        },
    ],
    "submit_label": "Сохранить безопасно",
    "password_required": True,
    "login_optional": False,
}

CHANNEL_FORMS: dict[str, dict[str, Any]] = {
    "telegram_bot": {
        "kind": "telegram_bot",
        "title": "Telegram bot — токен",
        "hint": "Токен от @BotFather. В чат не попадёт; Hermes подключит branded webhook для tenant.",
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
    "max_bot": {
        "kind": "max_bot",
        "title": "MAX bot — access token",
        "hint": "Access token MAX-бота. В чат не попадёт; Hermes подключит webhook для tenant.",
        "fields": [
            {
                "name": "password",
                "label": "Access token",
                "type": "password",
                "autocomplete": "off",
            }
        ],
        "submit_label": "Подключить MAX",
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


CALENDAR_FORMS: dict[str, dict[str, Any]] = {
    "calendar_yandex": {
        "kind": "calendar_yandex",
        "title": "Яндекс.Календарь",
        "hint": "Логин, пароль приложения и ссылка CalDAV. В чат не попадут.",
        "fields": [
            {"name": "login", "label": "Логин", "type": "text", "autocomplete": "username"},
            {"name": "password", "label": "Пароль приложения", "type": "password", "autocomplete": "off"},
        ],
        "submit_label": "Подключить календарь",
        "password_required": True,
        "login_optional": False,
        "require_foreign_consent": False,
    },
    "calendar_mailru": {
        "kind": "calendar_mailru",
        "title": "Календарь Mail.ru",
        "hint": "Укажите адрес почты и пароль приложения. Данные останутся в защищённой форме.",
        "fields": [
            {"name": "login", "label": "Адрес почты", "type": "text", "autocomplete": "username", "placeholder": "ivan@mail.ru"},
            {"name": "password", "label": "Пароль приложения", "type": "password", "autocomplete": "off", "help": "Mail.ru → Настройки → Безопасность → Пароли для внешних приложений"},
        ],
        "submit_label": "Подключить календарь",
        "password_required": True,
        "login_optional": False,
        "require_foreign_consent": False,
    },
    "calendar_google": {
        "kind": "calendar_google",
        "title": "Google Calendar",
        "hint": "Access token Google. Данные у Google вне РФ — нужно согласие.",
        "fields": [
            {"name": "password", "label": "Access token", "type": "password", "autocomplete": "off"},
        ],
        "submit_label": "Подключить Google Calendar",
        "password_required": True,
        "login_optional": True,
        "require_foreign_consent": True,
    },
    "calendar_outlook": {
        "kind": "calendar_outlook",
        "title": "Outlook Calendar",
        "hint": "Microsoft Graph token. Данные у Microsoft вне РФ — нужно согласие.",
        "fields": [
            {"name": "password", "label": "Graph token", "type": "password", "autocomplete": "off"},
        ],
        "submit_label": "Подключить Outlook",
        "password_required": True,
        "login_optional": True,
        "require_foreign_consent": True,
    },
}


def credential_form_spec(kind: str = "mango_sip", *, prefill: dict[str, str] | None = None) -> dict[str, Any]:
    kind = (kind or "mango_sip").strip()
    if kind in CLOUD_FORMS:
        form = dict(CLOUD_FORMS[kind])
    elif kind in CALENDAR_FORMS:
        form = dict(CALENDAR_FORMS[kind])
    elif kind in CHANNEL_FORMS:
        form = dict(CHANNEL_FORMS[kind])
    elif kind == "mango_sip":
        form = dict(MANGO_SIP_FORM)
    elif kind in ACCOUNT_FORMS:
        form = dict(ACCOUNT_FORMS[kind])
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
                "configured": bool(row.get("password") or row.get("login") or row.get("has_token")),
                "login_masked": _mask(str(row.get("login") or "")),
                "foreign_consent": bool(row.get("foreign_consent_at")),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"items": items}


_EXTRA_SECRET_KEYS = frozenset({"calendar_url", "url", "calendar_id"})


def save_secret(
    db: Session,
    ctx: TenantContext,
    *,
    kind: str,
    login: str | None = None,
    password: str | None = None,
    foreign_consent: bool = False,
    extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    kind = (kind or "").strip()
    if kind not in SUPPORTED_KINDS:
        return {"ok": False, "error": "unsupported_kind"}
    login_s = (login or "").strip()
    password_s = (password or "").strip()
    max_pw = 4096 if kind in _LONG_SECRET_KINDS else 200
    if not login_s and not password_s:
        return {"ok": False, "error": "empty"}
    if kind == "files_mailru" and not login_s:
        return {"ok": False, "error": "login_required"}
    if kind in ("telegram_bot", "max_bot") and not password_s:
        return {"ok": False, "error": "password_required"}
    if password_s and len(password_s) < 4:
        return {"ok": False, "error": "password_too_short"}
    if kind in _FOREIGN_SECRET_KINDS and not foreign_consent:
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
    if login_s and kind == "mango_sip":
        from app.services.sip_probe import normalize_mango_login

        login_s = normalize_mango_login(login_s)
    if login_s:
        current["login"] = login_s[:120]
    if password_s and kind not in ("telegram_bot", "max_bot"):
        current["password"] = password_s[:max_pw]
    elif kind in ("telegram_bot", "max_bot"):
        # The bot token belongs only in the encrypted ChannelAccount record.
        current.pop("password", None)
    if kind in _FOREIGN_SECRET_KINDS and foreign_consent:
        current["foreign_consent_at"] = datetime.now(timezone.utc).isoformat()
    for key, value in (extra or {}).items():
        if key in _EXTRA_SECRET_KEYS and str(value or "").strip():
            current[key] = str(value).strip()[:500]
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
        msg = "Подключаю Telegram. Токен в чат не попал."
    elif kind == "max_bot":
        msg = "Подключаю MAX. Токен в чат не попал."
    elif kind in CLOUD_KINDS or kind in CALENDAR_KINDS or kind in MAIL_KINDS or kind in CONFERENCE_KINDS:
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

            connected = connect_telegram_branded(db, ctx, password_s)
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
                    "Подключить канал не удалось: "
                    + str(connected.get("error") or connected.get("message_ru") or "ошибка")
                )
        except Exception as exc:  # noqa: BLE001
            out["channel_connect"] = {"ok": False, "error": "telegram_connect_failed"}
            out["message"] = "Подключить Telegram не удалось. Повторите попытку."
    if kind == "max_bot":
        try:
            from app.services.max_connect import connect_max_branded

            connected = connect_max_branded(db, ctx, password_s)
            out["channel_connect"] = {
                k: connected.get(k)
                for k in ("ok", "error", "account", "message_ru", "webhook")
                if k in connected or connected.get(k) is not None
            }
            if connected.get("ok"):
                out["message"] = "MAX бот подключён. Токен в чат не попал."
            else:
                out["message"] = (
                    "Подключить MAX не удалось: "
                    + str(connected.get("error") or "ошибка")
                )
        except Exception as exc:  # noqa: BLE001
            out["channel_connect"] = {"ok": False, "error": "max_connect_failed"}
            out["message"] = "Подключить MAX не удалось. Повторите попытку."
    if kind in ("telegram_bot", "max_bot"):
        connected_ok = bool((out.get("channel_connect") or {}).get("ok"))
        current["has_token"] = connected_ok
        blob[kind] = current
        settings["secrets"] = blob
        tenant.settings = settings
        db.commit()
        out["configured"] = connected_ok
    if kind == "mango_sip":
        try:
            from app.models.phone_number import PhoneNumber
            from app.services.sip_probe import after_vault_sip_save, trunk_id_for_tenant

            # Prefer an active DID of THIS tenant — never a shared dogfood number.
            did_row = (
                db.query(PhoneNumber)
                .filter(PhoneNumber.tenant_id == ctx.tenant_id, PhoneNumber.status == "active")
                .order_by(PhoneNumber.created_at.desc())
                .first()
            )
            did = did_row.e164 if did_row else None
            probe = after_vault_sip_save(
                tenant_slug=ctx.tenant_slug,
                login=current.get("login"),
                password=current.get("password"),
                did=did,
            )
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
                    "trunk_id",
                )
                if k in probe
            }
            trunk_id = str(probe.get("trunk_id") or trunk_id_for_tenant(ctx.tenant_slug))
            if did_row and trunk_id:
                cfg = dict(did_row.routing_config or {})
                cfg["trunk_id"] = trunk_id
                cfg["frontline"] = True
                cfg["outbound"] = True
                did_row.routing_config = cfg
                db.commit()
            from app.services.sip_probe import classify_sip_outcome

            outcome = classify_sip_outcome(probe)
            out["sip_outcome"] = outcome
            _remember_sip_outcome(db, ctx, outcome)
            if outcome["code"] in ("format", "rejected"):
                out["message"] = (out["message"] + " " + outcome["message_ru"]).strip()
            elif probe.get("message_ru"):
                out["message"] = (out["message"] + " " + str(probe.get("message_ru"))).strip()
            # Rejected / not Registered → reopen SIP form so owner can fix password without
            # hunting for «пришли форму» (follow-up chat used to block vault reopen).
            if not probe.get("ok") and not probe.get("skipped"):
                out["pending_credential_form"] = credential_form_spec("mango_sip")
                out["message"] = (
                    (out.get("message") or "") + " Форма SIP открыта ниже."
                ).strip()
            elif probe.get("ok") and not did:
                out["message"] = (
                    (out.get("message") or "")
                    + " SIP Registered. Следующий шаг — привяжите DID этого кабинета (скажите номер)."
                ).strip()
        except Exception:  # noqa: BLE001
            __import__("logging").getLogger(__name__).exception("sip probe after vault save failed")
    elif kind in ACCOUNT_FORMS:
        out.update(_verify_office_account(db, ctx, kind, current))
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


def _verify_office_account(
    db: Session, ctx: TenantContext, kind: str, current: dict[str, Any]
) -> dict[str, Any]:
    """Real check of the owner's calendar/mail account. Only a pass marks it verified."""
    from app.services.office_accounts import verify_account

    try:
        result = verify_account(kind, str(current.get("login") or ""), str(current.get("password") or ""))
    except Exception:  # noqa: BLE001
        result = {"ok": False, "code": "error", "message_ru": "Проверка аккаунта упала, попробуем ещё раз."}
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    blob = dict(settings.get("secrets") or {})
    row = dict(blob.get(kind) or {})
    if result.get("ok"):
        row["verified_at"] = datetime.now(timezone.utc).isoformat()
        row["verified_summary"] = str(result.get("message_ru") or "")[:300]
    else:
        row.pop("verified_at", None)
        row.pop("verified_summary", None)
    blob[kind] = row
    settings["secrets"] = blob
    tenant.settings = settings
    db.commit()
    public = {k: v for k, v in result.items() if k in ("ok", "code", "message_ru", "calendars", "events_14d")}
    extra: dict[str, Any] = {"account_probe": public, "message": str(result.get("message_ru") or "")}
    if not result.get("ok"):
        extra["pending_credential_form"] = credential_form_spec(kind)
    return extra


def _remember_sip_outcome(db: Session, ctx: TenantContext, outcome: dict[str, str]) -> None:
    """Keep the last SIP form result as a tenant fact Hermes can read (no secrets)."""
    try:
        tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
        settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
        settings["telephony_sip_last"] = {
            "code": str(outcome.get("code") or "")[:32],
            "message_ru": str(outcome.get("message_ru") or "")[:400],
            "at": datetime.now(timezone.utc).isoformat(),
        }
        tenant.settings = settings
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    if "/" in value:
        left, _, right = value.partition("/")
        return f"{left[:2]}***/{right[:1]}***" if right else f"{left[:2]}***"
    return f"{value[:2]}***{value[-1]}"
