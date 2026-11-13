"""Deterministic Hermes coach replies — used when OpenAI egress is down."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services import hermes_ops, phone_provision
from app.services.tenant_vault import credential_form_spec, list_secret_status


def _sip_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    items = list_secret_status(db, ctx).get("items") or []
    row = next((i for i in items if i.get("kind") == "mango_sip"), None) or {}
    return {
        "configured": bool(row.get("configured")),
        "login_masked": row.get("login_masked") or "",
        "updated_at": row.get("updated_at"),
        "login_looks_partial": bool(row.get("configured") and "/" not in (row.get("login_masked") or "")),
    }


def _phone_block(db: Session, ctx: TenantContext, *, sip: dict[str, Any] | None = None) -> str:
    sip = sip or _sip_status(db, ctx)
    phones = phone_provision.list_phones(db, ctx).get("items") or []
    active = [p for p in phones if p.get("status") == "active"]

    lines: list[str] = []
    if active:
        lines.append("Номер в кабинете уже привязан:")
        for p in active[:5]:
            lines.append(f"• {p.get('e164')} · {p.get('label') or 'main'} · {p.get('status')}")
    else:
        lines.append(
            "Номер (DID) ещё не привязан. Скажите: «привяжи номер +7…» "
            "или нажмите чип «Настроить телефон»."
        )

    if sip.get("configured"):
        lines.append(
            f"SIP Mango сохранён в сейфе кабинета ({sip.get('login_masked') or '••••'}) "
            "— в чат пароль не попадал."
        )
        if sip.get("login_looks_partial"):
            lines.append(
                "Внимание: логин выглядит неполным (ожидается вид `номер/сотрудник`, "
                "например `400348777/garik`). Откройте форму ещё раз и сохраните полный логин."
            )
        else:
            lines.append(
                "Дальше — регистрация линии на Asterisk/Cloud4Box (статус Registered). "
                "Скажите «проверь здоровье» или «какие звонки были»."
            )
    else:
        lines.append(
            "SIP-логин и пароль Mango ещё не сохранены. "
            "Введите их в безопасной форме ниже — не вставляйте пароль в чат."
        )
    return "\n".join(lines)


def _is_status_question(lower: str) -> bool:
    status_cues = (
        "настроен",
        "настроена",
        "настроено",
        "уже сохран",
        "сохранил",
        "сохранено",
        "готово",
        "готов ли",
        "работает",
        "статус",
        "провери",
        "как дела",
        "что с телефон",
        "телефон ок",
    )
    return any(c in lower for c in status_cues)


def _wants_new_sip_form(lower: str, *, sip_configured: bool) -> bool:
    if any(
        k in lower
        for k in (
            "форму",
            "заново",
            "ещё раз",
            "еще раз",
            "сменить пароль",
            "поменять пароль",
            "обновить sip",
            "новый пароль",
        )
    ):
        return True
    if not sip_configured and any(k in lower for k in ("пароль", "логин", "sip", "mango", "манго")):
        return True
    return not sip_configured and not _is_status_question(lower)


def _voice_block(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    lower = message.lower()
    voice_words = ("голос", "voice", "realtime", "смени голос", "какой голос")
    if not any(w in lower for w in voice_words):
        return None
    from app.core.config import get_settings
    from app.models.tenant_voice_profile import TenantVoiceProfile

    settings = get_settings()
    model = getattr(settings, "openai_realtime_model", None) or "gpt-realtime-2.1-mini"
    default_voice = getattr(settings, "openai_realtime_voice", None) or "cedar"
    row = (
        db.query(TenantVoiceProfile)
        .filter(TenantVoiceProfile.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    current = (row.preset_id if row and row.preset_id else default_voice) or default_voice
    # "смени голос на X"
    new_voice = None
    for token in ("на ", "to ", "voice "):
        if token in lower:
            part = lower.split(token, 1)[-1].strip().split()[0].strip(".,!")
            if part.isalpha() and 3 <= len(part) <= 32:
                new_voice = part
                break
    if new_voice and new_voice not in ("голос", "voice", "realtime"):
        if row is None:
            row = TenantVoiceProfile(
                tenant_id=ctx.tenant_id,
                mode="preset",
                provider="openai",
                preset_id=new_voice,
                language="ru",
            )
            db.add(row)
        else:
            row.preset_id = new_voice
            row.provider = "openai"
            row.mode = "preset"
        db.commit()
        current = new_voice
        head = f"Голос Realtime переключил на «{current}» (модель {model})."
    else:
        head = f"Сейчас голос «{current}», модель {model} (как в архиве: gpt-realtime-2.1-mini / cedar)."
    return {
        "reply": (
            f"{head}\n"
            "Скажите «смени голос на cedar|alloy|echo|shimmer|…». "
            "Для звонков AVA читает ai-agent.local.yaml; кабинетный профиль — tenant_voice_profiles."
        ),
        "tool_calls": [{"tool": "hermes.voice", "ok": True, "voice": current, "model": model}],
        "suggested_actions": [
            {"title": "Голос cedar", "text": "Смени голос на cedar"},
            {"title": "Тест линии", "text": "Проверь регистрацию SIP и здоровье телефонии"},
        ],
    }


def _lost_user_guide(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Plain-language next steps when the owner is confused — any new tenant."""
    from app.services.sip_probe import probe_registration
    from app.services.telephony_script import get_telephony_config

    setup = hermes_ops.office_setup_status(db, ctx)
    sip = _sip_status(db, ctx)
    probe = probe_registration()
    phones = phone_provision.list_phones(db, ctx).get("items") or []
    active = [p for p in phones if p.get("status") == "active"]
    script = get_telephony_config(db, ctx)
    checks = setup.get("checks") or {}
    kb_ok = bool((checks.get("kb") or {}).get("ok"))

    lines = [
        "Ок, с нуля — делаем по порядку. Я подскажу каждый шаг.",
        "",
    ]
    step = 1
    if not kb_ok:
        lines.append(
            f"{step}) Сначала компания: расскажите о бизнесе, пришлите сайт "
            "или скачайте MD-шаблон профиля (кнопка ниже) и прикрепите заполненный файл."
        )
        step += 1
    else:
        lines.append(f"{step}) Профиль компании уже есть — этот шаг закрыт.")
        step += 1
    if not active:
        lines.append(f"{step}) Привязать номер (DID). Скажите: «привяжи номер +7…».")
        step += 1
    else:
        lines.append(f"{step}) Номер есть: {active[0].get('e164')}.")
        step += 1
    if not sip.get("configured"):
        lines.append(
            f"{step}) SIP в безопасной форме (логин + пароль). Скажите «пришли форму» — в чат пароль не пишите."
        )
        step += 1
    elif not probe.get("ok"):
        lines.append(
            f"{step}) SIP сохранён, но линия {probe.get('status') or 'не Registered'}. "
            "Пересохраните форму или «дай задание Cursor»."
        )
        step += 1
    else:
        lines.append(f"{step}) Линия Registered.")
        step += 1
    if not script.get("configured"):
        lines.append(
            f"{step}) Сценарий секретаря: «предложи сценарий из базы знаний», "
            "или надиктуйте своими словами и скажите «формализуй сценарий» / «сохрани сценарий»."
        )
        step += 1
    else:
        lines.append(f"{step}) Сценарий уже сохранён. Tools: {', '.join(script.get('tools') or [])}.")
        step += 1
    nxt = (setup.get("next_steps") or [None])[0]
    if nxt and nxt.get("id") not in ("phone", "telephony_script", "kb"):
        lines.append(f"{step}) Дальше: {nxt.get('title')} — {nxt.get('hint')}.")
    lines.append("")
    lines.append("Напишите, с какого шага идём — или «статус сетапа».")

    out: dict[str, Any] = {
        "reply": "\n".join(lines),
        "tool_calls": [{"tool": "hermes.guide.lost", "ok": True}],
        "suggested_actions": [
            {"title": "Шаблон компании", "text": "Дай шаблон профиля компании"},
            {"title": "Сценарий", "text": "Предложи сценарий из базы знаний"},
            {"title": "Форма SIP", "text": "Пришли форму, я введу логин"},
            {"title": "Статус", "text": "Статус сетапа"},
        ],
    }
    if not kb_ok:
        download = _company_template_download()
        if download:
            out["pending_download"] = download
            out["tool_calls"].append(
                {"tool": "hermes.templates.download", "ok": True, "pending_download": download}
            )
            out["suggested_actions"] = [
                {"title": "Расскажу сам", "text": "Сейчас расскажу о компании голосом"},
                {"title": "Есть сайт", "text": "Зайди на мой сайт и собери знания"},
                {"title": "Шаблон MD", "text": "Дай шаблон профиля компании"},
            ]
    if not sip.get("configured") or not probe.get("ok"):
        out["pending_credential_form"] = credential_form_spec("mango_sip")
    return out


def _files_cloud_coach(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    """Connect / status / list cloud disks per tenant via vault forms."""
    from app.services.files_cloud import (
        CLOUD_SOURCES,
        cloud_status,
        detect_source_from_message,
        probe_cloud_list,
    )

    lower = (message or "").lower().strip()
    status_cues = (
        "какие облака",
        "статус облак",
        "облака подключен",
        "какие диски",
        "файловые коннектор",
    )
    connect_cues = (
        "подключи диск",
        "подключи облак",
        "подключить диск",
        "подключить облак",
        "подключи яндекс",
        "подключи yandex",
        "подключи mail",
        "подключи google",
        "подключи onedrive",
        "подключи гугл",
        "яндекс.диск",
        "я.диск",
        "облако mail",
        "google drive",
        "гугл диск",
    )
    list_cues = (
        "покажи файлы",
        "список файлов",
        "что на диске",
        "файлы на яндекс",
        "файлы на google",
        "файлы на mail",
        "файлы на onedrive",
    )

    wants_status = any(k in lower for k in status_cues) or lower in (
        "облака",
        "диски",
        "файлы облако",
    )
    wants_connect = any(k in lower for k in connect_cues)
    wants_list = any(k in lower for k in list_cues)
    if not (wants_status or wants_connect or wants_list):
        return None

    source = detect_source_from_message(message)
    status = cloud_status(db, ctx)

    if wants_list:
        src = source or next(
            (i["source"] for i in status.get("items") or [] if i.get("ready")),
            None,
        )
        if not src:
            return {
                "reply": (
                    "Пока ни одно облако не подключено. "
                    "Скажите «подключи Яндекс.Диск» или «подключи Mail.ru» (рекомендуем РФ)."
                ),
                "tool_calls": [{"tool": "hermes.files.status", "ok": True}],
                "suggested_actions": [
                    {"title": "Яндекс.Диск", "text": "Подключи Яндекс.Диск"},
                    {"title": "Mail.ru", "text": "Подключи облако Mail.ru"},
                    {"title": "Статус", "text": "Какие облака подключены"},
                ],
            }
        probe = probe_cloud_list(db, ctx, source=src, path="/")
        return {
            "reply": probe.get("message_ru") or "Готово.",
            "tool_calls": [{"tool": "hermes.files.list", "ok": bool(probe.get("ok")), "source": src}],
            "suggested_actions": probe.get("next_actions")
            or [
                {"title": "Другое облако", "text": "Подключи Яндекс.Диск"},
                {"title": "Статус", "text": "Какие облака подключены"},
            ],
        }

    if wants_status and not wants_connect:
        lines = [status.get("message_ru") or "Статус облаков:", ""]
        for item in status.get("items") or []:
            mark = "готово" if item.get("ready") else ("токен есть, нет согласия" if item.get("configured") else "не подключено")
            res = "РФ" if item.get("residency") == "ru" else "зарубежье"
            lines.append(f"- {item['title']} ({res}): {mark}")
        lines.append("")
        lines.append(
            "Чтобы подключить: «подключи Яндекс.Диск» / «Mail.ru» / «Google Drive» (с согласием) / «OneDrive»."
        )
        return {
            "reply": "\n".join(lines),
            "tool_calls": [{"tool": "hermes.files.status", "ok": True}],
            "suggested_actions": [
                {"title": "Яндекс.Диск", "text": "Подключи Яндекс.Диск"},
                {"title": "Mail.ru", "text": "Подключи облако Mail.ru"},
                {"title": "Google", "text": "Подключи Google Drive"},
            ],
        }

    # Connect flow
    if not source:
        return {
            "reply": (
                "Какое облако подключаем?\n"
                "1) Яндекс.Диск (РФ) — предпочтительно\n"
                "2) Облако Mail.ru (РФ)\n"
                "3) Google Drive — только с согласием (данные у Google вне РФ)\n"
                "4) OneDrive — только с согласием (Microsoft вне РФ)\n\n"
                "Скажите, например: «подключи Яндекс.Диск»."
            ),
            "tool_calls": [{"tool": "hermes.files.connect", "ok": True, "step": "choose"}],
            "suggested_actions": [
                {"title": "Яндекс.Диск", "text": "Подключи Яндекс.Диск"},
                {"title": "Mail.ru", "text": "Подключи облако Mail.ru"},
                {"title": "Google Drive", "text": "Подключи Google Drive"},
            ],
        }

    meta = CLOUD_SOURCES[source]
    kind = meta["vault_kind"]
    form = credential_form_spec(kind)
    item = next((i for i in status.get("items") or [] if i.get("source") == source), {})
    if item.get("ready"):
        return {
            "reply": (
                f"{meta['title']} уже подключён"
                + (f" ({item.get('login_masked')})" if item.get("login_masked") else "")
                + ". Могу показать файлы в корне или заменить токен — скажите «форма снова»."
            ),
            "tool_calls": [{"tool": "hermes.files.connect", "ok": True, "source": source, "already": True}],
            "pending_credential_form": form,
            "suggested_actions": [
                {"title": "Файлы", "text": f"Покажи файлы на {meta['title']}"},
                {"title": "Статус", "text": "Какие облака подключены"},
            ],
        }

    foreign_note = ""
    if meta["residency"] == "foreign":
        foreign_note = (
            "\n\nВажно: это зарубежный провайдер. В форме отметьте согласие — "
            "без него токен не сохранится (152‑ФЗ / резидентность)."
        )
    return {
        "reply": (
            f"Открываю безопасную форму для «{meta['title']}». "
            f"{meta['hint']} Токен/пароль в ленту чата не попадёт."
            f"{foreign_note}"
        ),
        "tool_calls": [{"tool": "hermes.files.connect", "ok": True, "source": source}],
        "pending_credential_form": form,
        "suggested_actions": [
            {"title": "Статус облаков", "text": "Какие облака подключены"},
            {"title": "Другое облако", "text": "Подключи Яндекс.Диск"},
        ],
    }


def _wants_telephony_tools(lower: str) -> bool:
    """True when owner asks to enable in-call tools — must beat SIP status hijack."""
    cues = (
        "какие tools",
        "какие тулзы",
        "какие тулы",
        "tools для",
        "тулы для",
        "тулзы для",
        "подключи tools",
        "подключи тулз",
        "подключи тулы",
        "подключить tools",
        "подключить тулз",
        "включи tools",
        "включи тулз",
        "включи тулы",
        "включи календарь",
        "включи письмо",
        "включи почт",
        "tools сценари",
        "тулзы к",
        "тулы к",
        "tools к",
        "tools на лини",
        "тулзы на лини",
    )
    if any(k in lower for k in cues):
        return True
    # «подключи … календарь … почту … телемост» without the word tools
    if ("подключ" in lower or "включи" in lower) and (
        "календар" in lower
        or "телемост" in lower
        or "конференц" in lower
        or "почт" in lower
        or "письм" in lower
    ):
        return True
    return False


def _tools_from_message(lower: str, current: list[str]) -> list[str]:
    enable: list[str] = list(current)
    if "календар" in lower:
        for t in ("check_calendar", "create_calendar_event"):
            if t not in enable:
                enable.append(t)
    if any(k in lower for k in ("письм", "email", "почт", "презентац", "smtp")):
        for t in ("send_welcome_email", "send_email"):
            if t not in enable:
                enable.append(t)
    if any(k in lower for k in ("вкс", "телемост", "конференц", "meet", "jitsi")):
        if "create_conference" not in enable:
            enable.append("create_conference")
    if any(k in lower for k in ("баз", "знан", "knowledge")):
        if "get_company_knowledge" not in enable:
            enable.insert(0, "get_company_knowledge")
    # Bare «подключи тулзы» without specifics → useful default set
    if enable == list(current) and any(k in lower for k in ("тулз", "тулы", "tools")):
        for t in (
            "get_company_knowledge",
            "check_calendar",
            "create_calendar_event",
            "send_welcome_email",
            "send_email",
            "create_conference",
        ):
            if t not in enable:
                enable.append(t)
    return enable


def _telephony_tools_reply(
    db: Session,
    ctx: TenantContext,
    lower: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    from app.services.telephony_script import AVAILABLE_TOOLS, set_telephony_tools

    catalog = "\n".join(f"- `{t['id']}` — {t['title']}: {t['hint']}" for t in AVAILABLE_TOOLS)
    current = list(cfg.get("tools") or [])
    enable = _tools_from_message(lower, current)

    if enable != current and cfg.get("configured"):
        upd = set_telephony_tools(db, ctx, tools=enable)
        return {
            "reply": (
                f"{upd.get('message_ru')}\n\nДоступный каталог:\n{catalog}\n\n"
                "Скажите точнее («включи только календарь и знания»), если нужно сузить."
            ),
            "tool_calls": [{"tool": "hermes.telephony.tools", "ok": True, "tools": enable}],
            "suggested_actions": [
                {"title": "Тест линии", "text": "Проверь регистрацию SIP и здоровье телефонии"},
                {"title": "Сценарий", "text": "Покажи сценарий"},
            ],
        }

    if enable != current and not cfg.get("configured"):
        return {
            "reply": (
                "Понял: к линии нужно подключить "
                + ", ".join(enable)
                + ".\n"
                "Сначала сохраним сценарий секретаря — без него tools не к чему привязать.\n"
                "Скажите «предложи сценарий из базы знаний» или «сохрани сценарий», "
                "затем повторите «включи календарь, телемост и почту».\n\n"
                f"Каталог:\n{catalog}"
            ),
            "tool_calls": [
                {
                    "tool": "hermes.telephony.tools",
                    "ok": False,
                    "error": "script_missing",
                    "wanted": enable,
                }
            ],
            "suggested_actions": [
                {"title": "Предложи сценарий", "text": "Предложи сценарий из базы знаний"},
                {"title": "Сохранить сценарий", "text": "Сохрани сценарий"},
                {"title": "Повторить tools", "text": "Включи календарь телемост и почту"},
            ],
        }

    status = (
        "Сценарий ещё не сохранён — сначала «сохрани сценарий»."
        if not cfg.get("configured")
        else "Сейчас включено: " + (", ".join(current) if current else "—")
    )
    return {
        "reply": f"{status}\n\nКаталог tools:\n{catalog}",
        "tool_calls": [{"tool": "hermes.telephony.tools", "ok": True, "list_only": True}],
        "suggested_actions": [
            {"title": "Календарь+почта+ВКС", "text": "Включи календарь телемост и почту"},
            {"title": "Сохранить сценарий", "text": "Сохрани сценарий"},
        ],
    }


def _script_coach(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    """Onboarding: company templates + telephony script/tools for any tenant."""
    from app.services.onboarding_templates import get_template, list_templates
    from app.services.telephony_script import (
        formalize_rough_script,
        get_telephony_config,
        propose_script_from_knowledge,
        save_telephony_script,
    )

    lower = (message or "").lower().strip()
    cfg = get_telephony_config(db, ctx)

    if any(
        k in lower
        for k in (
            "дай шаблон",
            "скачай шаблон",
            "шаблон профиля",
            "шаблон компании",
            "шаблон сценария",
            "шаблон секретаря",
        )
    ):
        items = list_templates(include_examples=True)
        want_script = "сценари" in lower or "секретар" in lower or "телефон" in lower
        tid = "telephony-script" if want_script else "company-profile"
        tpl = get_template(tid)
        if not tpl:
            return {
                "reply": "Шаблоны временно недоступны на сервере. Откройте раздел «Знания» в кабинете.",
                "tool_calls": [{"tool": "hermes.templates", "ok": False}],
            }
        lines = [
            f"Шаблон «{tpl['title']}» — заполните и загрузите в Знания, либо надиктуйте мне содержимое.",
            "",
            "Также доступны:",
        ]
        for it in items:
            mark = "← этот" if it["id"] == tid else ""
            lines.append(f"- {it['title']} (`{it['id']}`) {mark}".rstrip())
        lines.append("")
        lines.append("Скачать в кабинете: Знания → Шаблоны. Ниже текст шаблона:")
        lines.append("")
        lines.append(tpl["body"][:6000])
        return {
            "reply": "\n".join(lines),
            "tool_calls": [{"tool": "hermes.templates", "ok": True, "template_id": tid}],
            "suggested_actions": [
                {"title": "Сценарий", "text": "Дай шаблон сценария секретаря"},
                {"title": "Предложи сценарий", "text": "Предложи сценарий из базы знаний"},
            ],
        }

    if any(
        k in lower
        for k in (
            "предложи сценарий",
            "сгенерируй сценарий",
            "сценарий из базы",
            "сценарий из знаний",
            "черновик сценария",
        )
    ):
        draft = propose_script_from_knowledge(db, ctx)
        return {
            "reply": draft["message_ru"] + "\n\n" + draft["draft"][:7000],
            "tool_calls": [{"tool": "hermes.telephony.propose", "ok": True}],
            "suggested_actions": [
                {"title": "Сохранить", "text": "Сохрани сценарий"},
                {"title": "Tools", "text": "Какие tools можно включить"},
            ],
            "_pending_script_draft": draft["draft"],
        }

    if any(k in lower for k in ("формализуй сценарий", "оформи сценарий", "структурируй сценарий")):
        # Strip the cue; remainder is owner dictation
        rough = message
        for cue in ("формализуй сценарий", "оформи сценарий", "структурируй сценарий"):
            idx = lower.find(cue)
            if idx >= 0:
                rough = message[idx + len(cue) :].strip(" :\n") or message
                break
        if len(rough.strip()) < 40:
            return {
                "reply": (
                    "Надиктуйте или вставьте текст сценария после фразы «формализуй сценарий …». "
                    "Я приведу к шаблону и предложу сохранить."
                ),
                "tool_calls": [{"tool": "hermes.telephony.formalize", "ok": False}],
            }
        formal = formalize_rough_script(rough)
        saved = save_telephony_script(db, ctx, script=formal, source="hermes.formalize")
        return {
            "reply": (
                f"{saved.get('message_ru')}\n\nВот формализованный сценарий:\n\n{formal[:6500]}"
            ),
            "tool_calls": [{"tool": "hermes.telephony.formalize", "ok": bool(saved.get("ok"))}],
            "suggested_actions": [
                {"title": "Tools", "text": "Включи календарь и письмо в сценарии"},
                {"title": "Статус", "text": "Статус сетапа"},
            ],
        }

    if any(k in lower for k in ("сохрани сценарий", "сохранить сценарий", "зафиксируй сценарий")):
        # Prefer body after cue; else keep existing draft request
        body = message
        for cue in ("сохрани сценарий", "сохранить сценарий", "зафиксируй сценарий"):
            idx = lower.find(cue)
            if idx >= 0:
                body = message[idx + len(cue) :].strip(" :\n")
                break
        if len(body) < 40:
            if cfg.get("configured"):
                return {
                    "reply": "Сценарий уже сохранён. Чтобы заменить — пришлите новый текст после «сохрани сценарий».",
                    "tool_calls": [{"tool": "hermes.telephony.save", "ok": True, "already": True}],
                }
            draft = propose_script_from_knowledge(db, ctx)
            saved = save_telephony_script(db, ctx, script=draft["draft"], source="hermes.propose_save")
            return {
                "reply": saved.get("message_ru") + "\n\nСохранил черновик из знаний/шаблона. Можете править.",
                "tool_calls": [{"tool": "hermes.telephony.save", "ok": bool(saved.get("ok"))}],
            }
        saved = save_telephony_script(db, ctx, script=body, source="hermes.save")
        return {
            "reply": saved.get("message_ru") or "Сохранено.",
            "tool_calls": [{"tool": "hermes.telephony.save", "ok": bool(saved.get("ok"))}],
        }

    if _wants_telephony_tools(lower):
        return _telephony_tools_reply(db, ctx, lower, cfg)

    if any(
        k in lower
        for k in (
            "сценарий секретар",
            "сценарий телефон",
            "сценарий авы",
            "сценарий ava",
            "где сценарий",
            "покажи сценарий",
            "наш сценарий",
        )
    ):
        if cfg.get("configured"):
            preview = (cfg.get("script") or "")[:3500]
            return {
                "reply": (
                    "Сценарий входящей линии уже в кабинете (сохранён через онбординг Hermes).\n"
                    f"Приветствие: {cfg.get('greeting') or '—'}\n"
                    f"Tools: {', '.join(cfg.get('tools') or [])}\n\n{preview}"
                ),
                "tool_calls": [{"tool": "hermes.telephony.status", "ok": True}],
            }
        return {
            "reply": (
                "Сценария ещё нет — это нормально для нового кабинета.\n"
                "Варианты:\n"
                "1) «дай шаблон сценария секретаря» — скачать/заполнить\n"
                "2) «предложи сценарий из базы знаний» — черновик из ваших Знаний\n"
                "3) Надиктуйте своими словами: «формализуй сценарий: …»\n"
                "Потом «сохрани сценарий» и при необходимости «включи календарь и письмо»."
            ),
            "tool_calls": [{"tool": "hermes.telephony.status", "ok": True, "configured": False}],
            "suggested_actions": [
                {"title": "Шаблон", "text": "Дай шаблон сценария секретаря"},
                {"title": "Из знаний", "text": "Предложи сценарий из базы знаний"},
            ],
        }

    return None


def coach_reply(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    lower = (message or "").lower().strip()
    if not lower:
        return None

    # Don't steal list/health/billing/website intents
    if any(
        t in lower
        for t in (
            "какие звонки",
            "список звонков",
            "проверь здоровье",
            "здоровье офиса",
            "баланс",
            "тариф",
            "расход токенов",
            "зайди на",
            "собери знания",
            "импорт сайта",
            "парси",
            ".ru",
            ".com",
            "http://",
            "https://",
        )
    ):
        return None

    lost_cues = (
        "ничего не понимаю",
        "не понимаю",
        "что делать",
        "что мне делать",
        "подскажи что",
        "с чего начать",
        "помоги разобраться",
        "я запутался",
        "я запуталась",
        "объясни по шагам",
        "по шагам",
        "что нужно сделать",
        "что дальше делать",
    )
    if any(c in lower for c in lost_cues):
        # If company profile missing — lost guide already covers it; keep that path.
        return _lost_user_guide(db, ctx)

    voice = _voice_block(db, ctx, message)
    if voice:
        return voice

    # Owner saying they will describe the company / starting from zero
    if any(
        k in lower
        for k in (
            "расскажу о компании",
            "рассказать о компании",
            "данные компании",
            "сначала о компании",
            "соберем данные",
            "соберём данные",
        )
    ):
        return _setup_status_coach(db, ctx)

    files_cloud = _files_cloud_coach(db, ctx, message)
    if files_cloud:
        return files_cloud

    scripted = _script_coach(db, ctx, message)
    if scripted:
        scripted.pop("_pending_script_draft", None)
        return scripted

    if any(k in lower for k in ("задание cursor", "задачу cursor", "дай задание", "почини через cursor")):
        from app.services.sip_probe import CURSOR_TASK_SIP_REJECTED, probe_registration

        probe = probe_registration()
        return {
            "reply": (
                "Вот задание для Cursor по SIP/телефонии. Скопируйте в агент:\n\n"
                f"{CURSOR_TASK_SIP_REJECTED}\n\n"
                f"Текущий статус линии: {probe.get('message_ru')}"
            ),
            "tool_calls": [{"tool": "hermes.cursor_task", "ok": True, "topic": "sip"}],
            "suggested_actions": [
                {"title": "Форма SIP", "text": "Открой безопасную форму SIP Mango"},
                {"title": "Статус линии", "text": "Проверь регистрацию SIP"},
            ],
        }

    # Password paste / explicit form requests handled elsewhere; don't swallow
    # pure credential paste into the coach.
    if any(t in lower for t in ("password", "login")) and "телефон" not in lower:
        return None

    # Tool-enable intents must not fall into SIP status dump («…к sip календарь…»).
    if _wants_telephony_tools(lower):
        from app.services.telephony_script import get_telephony_config

        return _telephony_tools_reply(db, ctx, lower, get_telephony_config(db, ctx))

    phone_words = (
        "телефон",
        "секретар",
        "номер",
        "did",
        "mango",
        "манго",
        "входящ",
        "исходящ",
        "лини",
        "sip",
        "настроить телефон",
        "настрой телефон",
        "помоги настроить",
    )
    if any(w in lower for w in phone_words) or (
        _is_status_question(lower) and any(w in lower for w in ("телефон", "sip", "лини", "секретар", "звон"))
    ):
        sip = _sip_status(db, ctx)
        setup = hermes_ops.office_setup_status(db, ctx)
        health = hermes_ops.office_health_report(db, ctx)
        status_q = _is_status_question(lower)
        show_form = _wants_new_sip_form(lower, sip_configured=bool(sip.get("configured")))

        if status_q and sip.get("configured"):
            head = "Да — SIP уже сохранён в кабинете. Не начинаю настройку заново."
        elif sip.get("configured"):
            head = "Телефония частично готова: данные SIP уже есть. Смотрим, что ещё осталось."
        else:
            head = "Ок, настраиваем телефонного секретаря — без лишних вопросов."

        body = [
            head,
            _phone_block(db, ctx, sip=sip),
            "",
            f"Сетап: {setup.get('message_ru')}",
            f"Здоровье: {health.get('message_ru')}",
        ]
        out: dict[str, Any] = {
            "reply": "\n".join(body),
            "tool_calls": [
                {"tool": "hermes.guide.phone", "ok": True, "sip_configured": bool(sip.get("configured"))},
                {"tool": "phones.list", "ok": True},
                {"tool": "hermes.setup_status", "ok": True},
                {"tool": "hermes.health", "ok": True},
            ],
        }
        if show_form:
            out["pending_credential_form"] = credential_form_spec("mango_sip")
        # Proactive next chips
        try:
            from app.services.sip_probe import probe_registration, _next_actions

            probe = probe_registration()
            out["tool_calls"].append(
                {
                    "tool": "sip.probe",
                    "ok": bool(probe.get("ok")),
                    "status": probe.get("status"),
                    "suggested_actions": _next_actions(probe),
                }
            )
            if not probe.get("ok") and sip.get("configured"):
                out["pending_credential_form"] = credential_form_spec("mango_sip")
                out["reply"] += (
                    "\n\nАвтопроверка: линия ещё не Registered "
                    f"({probe.get('status') or 'unknown'}). "
                    "Открываю форму SIP снова — проверьте логин (номер/сотрудник) и пароль."
                )
            elif probe.get("ok"):
                out["reply"] += "\n\nАвтопроверка: линия Registered. Следующий шаг — тестовый звонок."
        except Exception:  # noqa: BLE001
            pass
        return out

    setup_words = (
        "настрой офис",
        "настроить офис",
        "как начать",
        "что делать дальше",
        "что дальше",
        "помоги с сетапом",
        "статус сетапа",
        "владельец офиса",
        "я владелец",
    )
    if any(w in lower for w in setup_words) or (
        "сетап" in lower and any(w in lower for w in ("статус", "что", "помог", "покаж"))
    ):
        return _setup_status_coach(db, ctx)

    return None


def _company_template_download() -> dict[str, Any] | None:
    from app.services.onboarding_templates import get_template

    tpl = get_template("company-profile")
    if not tpl:
        return None
    return {
        "filename": tpl["filename"],
        "title": tpl["title"],
        "body": tpl["body"],
        "content_type": tpl.get("content_type") or "text/markdown; charset=utf-8",
    }


def _setup_status_coach(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Always put company knowledge first for a new / incomplete office."""
    setup = hermes_ops.office_setup_status(db, ctx)
    checks = setup.get("checks") or {}
    kb_ok = bool((checks.get("kb") or {}).get("ok"))
    next_steps = setup.get("next_steps") or []

    if not kb_ok:
        download = _company_template_download()
        lines = [
            "Сначала мне нужно понять вашу компанию — без этого секретарь и каналы бесполезны.",
            "",
            "Выберите удобный способ:",
            "1) Расскажите своими словами: чем занимаетесь, для кого, цены, как записывать клиентов.",
            "2) Пришлите ссылку на сайт — соберу черновик знаний.",
            "3) Скачайте шаблон профиля (кнопка ниже / файл), заполните и прикрепите сюда.",
            "",
            "После этого перейдём к телефонии, сценарию секретаря и Telegram.",
        ]
        tool_calls: list[dict[str, Any]] = [{"tool": "hermes.guide.setup", "ok": True, "step": "company"}]
        if download:
            tool_calls.append(
                {
                    "tool": "hermes.templates.download",
                    "ok": True,
                    "pending_download": download,
                }
            )
        return {
            "reply": "\n".join(lines),
            "tool_calls": tool_calls,
            "pending_download": download,
            "suggested_actions": [
                {"title": "Расскажу сам", "text": "Сейчас расскажу о компании голосом"},
                {"title": "Есть сайт", "text": "Зайди на мой сайт и собери знания"},
                {"title": "Заполню шаблон", "text": "Дай шаблон профиля компании"},
            ],
        }

    lines = [
        setup.get("message_ru") or "Продолжаем сетап офиса.",
        "Конкретные шаги:",
    ]
    if next_steps:
        for i, step in enumerate(next_steps[:3], 1):
            lines.append(f"{i}) {step.get('title')}: {step.get('hint')}")
    else:
        lines.append("Обязательные шаги закрыты. Можно проверять звонки и каналы.")
    lines.append("Голосом можно надиктовать следующий шаг в mic.")
    return {
        "reply": "\n".join(lines),
        "tool_calls": [{"tool": "hermes.guide.setup", "ok": True}],
        "suggested_actions": [
            {"title": "Сценарий", "text": "Предложи сценарий из базы знаний"},
            {"title": "Telegram", "text": "Как подключить Telegram-бота"},
            {"title": "Статус", "text": "Статус сетапа"},
        ],
    }


def llm_unavailable_reply(message: str) -> str:
    return (
        "Сейчас умный LLM на сервере недоступен (OpenAI с Cloud4Box режется по региону — "
        "нужен SOCKS моста СПБ→Минск→NL в OPENAI_HTTP_PROXY).\n"
        "Пока работаю короткими командами: «статус сетапа», «настрой телефон», "
        "«проверь здоровье», «баланс», «какие звонки».\n"
        f"Ваш запрос: «{message.strip()[:180]}» — уточните одной из команд выше, "
        "или дайте proxy моста, и я отвечу полноценно."
    )


def chip_actions_for_office(
    db: Session,
    ctx: TenantContext,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Bottom suggestion chips Hermes should attach after every useful reply.

    Priority:
    1) suggested_actions already produced by a tool this turn
    2) pending KB draft → confirm / enrich chips
    3) setup_status.next_steps → next onboarding chips
    4) safe defaults (status / health / channels)
    """
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        raw = tc.get("suggested_actions")
        if not isinstance(raw, list) or not raw:
            continue
        out: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            text = str(item.get("text") or item.get("prompt") or "").strip()
            if title and text:
                out.append({"title": title[:48], "text": text[:200]})
        if out:
            return out[:5]

    try:
        from app.services.office_loop import get_office_loop

        loop = get_office_loop(db, ctx) or {}
        draft = loop.get("kb_draft") if isinstance(loop, dict) else None
        if (
            isinstance(draft, dict)
            and str(draft.get("status") or "") == "draft"
            and str(draft.get("body") or "").strip()
        ):
            return [
                {"title": "Добавить в KB", "text": "Подтверди черновик базы знаний"},
                {"title": "Показать профиль", "text": "Покажи что нашёл в черновике"},
                {"title": "Уточнить цены", "text": "Цены и условия такие: "},
                {"title": "Добавить каналы", "text": "Вот ссылки на Telegram / Instagram / VK: "},
            ]
    except Exception:
        pass

    try:
        from app.services import hermes_ops

        status = hermes_ops.office_setup_status(db, ctx) or {}
        next_steps = status.get("next_steps") or []
        actions: list[dict[str, str]] = []
        for step in next_steps[:4]:
            if not isinstance(step, dict):
                continue
            sid = str(step.get("id") or step.get("check") or "").lower()
            title = str(step.get("title") or "Шаг").strip()
            hint = str(step.get("hint") or title).strip()
            if sid in {"kb", "knowledge", "kb_ready"}:
                actions.append(
                    {"title": "База знаний", "text": "Собери профиль компании с сайта"}
                )
            elif sid in {"phone", "telephony", "sip"}:
                actions.append(
                    {"title": "Телефон", "text": "Настрой телефон секретаря"}
                )
            elif sid in {"telegram", "max", "channels", "messenger"}:
                actions.append(
                    {"title": "Каналы", "text": "Что ещё настроить в каналах?"}
                )
            elif sid in {"mail", "email"}:
                actions.append(
                    {"title": "Почта", "text": "Подключи почту офиса"}
                )
            elif sid in {"calendar"}:
                actions.append(
                    {"title": "Календарь", "text": "Подключи календарь"}
                )
            elif sid in {"files", "drive"}:
                actions.append(
                    {"title": "Файлы", "text": "Подключи файлы / диск"}
                )
            elif sid in {"conference", "telemost"}:
                actions.append(
                    {"title": "Встречи", "text": "Подключи видеовстречи"}
                )
            elif sid in {"script", "scenario", "telephony_script"}:
                actions.append(
                    {
                        "title": "Сценарий",
                        "text": "Предложи сценарий из базы знаний",
                    }
                )
            else:
                actions.append(
                    {"title": title[:40], "text": (hint or title)[:120]}
                )
        if status.get("setup_complete") or not actions:
            actions = [
                {"title": "Статус", "text": "Статус сетапа"},
                {"title": "Здоровье", "text": "Проверь здоровье офиса"},
                {"title": "Каналы", "text": "Что ещё настроить в каналах?"},
                {"title": "База знаний", "text": "Покажи, что сейчас в базе знаний"},
            ]
        # de-dupe by title
        seen: set[str] = set()
        uniq: list[dict[str, str]] = []
        for a in actions:
            t = a["title"]
            if t in seen:
                continue
            seen.add(t)
            uniq.append(a)
        return uniq[:5]
    except Exception:
        return [
            {"title": "Статус", "text": "Статус сетапа"},
            {"title": "Здоровье", "text": "Проверь здоровье офиса"},
            {"title": "База знаний", "text": "Покажи, что сейчас в базе знаний"},
        ]
