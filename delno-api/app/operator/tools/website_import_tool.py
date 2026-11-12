"""Hermes: import company website into tenant KB + propose connector setup."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import hermes_ops
from app.services.instant_demo import import_website_to_tenant
from app.services.onboarding_website import extract_url_from_message


class OfficeImportWebsiteTool:
    name = "office.import_website"
    description = (
        "Fetch a company website, put structured text into the tenant knowledge base, "
        "and return next steps to finish office connectors (mail, telegram, phone, …)."
    )
    # Explicit owner request ("зайди на сайт…") is consent; run immediately.
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Website URL or domain, e.g. https://quantumpayouts.ru",
            },
            "message": {
                "type": "string",
                "description": "Optional free text that may contain the URL",
            },
        },
        "required": [],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        raw = str(params.get("url") or params.get("message") or "").strip()
        url = extract_url_from_message(raw) or (raw if raw.startswith("http") else None)
        if not url and raw and "." in raw and " " not in raw:
            url = raw
        if not url:
            return ToolResult(ok=False, message="Нужен URL сайта, например https://quantumpayouts.ru")

        try:
            result = import_website_to_tenant(
                db,
                ctx,
                website_url=url,
                source="hermes.import_website",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, message=f"Не удалось скачать сайт: {exc}")

        if not result.get("ok"):
            return ToolResult(ok=False, data=result, message="Импорт сайта не удался")

        setup = hermes_ops.office_setup_status(db, ctx)
        next_steps = setup.get("next_steps") or []
        suggested = _suggested_actions(next_steps)
        title = result.get("title") or "сайт"
        samples = result.get("sample_questions") or []

        lines = [
            f"Зашёл на {result.get('url')} и положил материалы «{title}» в базу знаний.",
            "Дальше предлагаю донастроить кабинет по шагам:",
        ]
        if next_steps:
            for i, step in enumerate(next_steps[:4], 1):
                lines.append(f"{i}) {step.get('title')}: {step.get('hint')}")
        else:
            lines.append("Обязательный сетап уже закрыт — можно проверить каналы и здоровье офиса.")
        if samples:
            lines.append("Примеры вопросов по сайту: " + "; ".join(str(s) for s in samples[:3]))
        lines.append("Нажмите чип действия ниже или напишите следующий шаг.")

        return ToolResult(
            ok=True,
            data={
                **result,
                "setup": setup,
                "suggested_actions": suggested,
            },
            message="\n".join(lines),
        )


def _suggested_actions(next_steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for step in next_steps[:4]:
        check = str(step.get("check") or "")
        title = str(step.get("title") or "Шаг")
        if check == "phone":
            actions.append({"title": "Телефон", "text": "Настрой телефон секретаря"})
        elif check in {"telegram", "max", "channels"}:
            actions.append({"title": "Каналы", "text": "Что ещё настроить в каналах?"})
        elif check in {"mail", "calendar", "files", "conference", "connectors"}:
            actions.append({"title": title[:40], "text": f"Покажи статус коннекторов и что подключить дальше"})
        elif check == "kb":
            actions.append({"title": "База знаний", "text": "Покажи, что сейчас в базе знаний"})
        else:
            hint = str(step.get("hint") or title)
            actions.append({"title": title[:40], "text": hint[:120]})
    if not actions:
        actions = [
            {"title": "Здоровье", "text": "Проверь здоровье офиса"},
            {"title": "Сетап", "text": "Что ещё настроить в офисе?"},
            {"title": "База знаний", "text": "Покажи, что сейчас в базе знаний"},
        ]
    # always offer health after import
    if not any(a["title"] == "Здоровье" for a in actions):
        actions.append({"title": "Здоровье", "text": "Проверь здоровье офиса"})
    return actions[:5]
