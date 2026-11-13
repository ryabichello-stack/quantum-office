"""Compose per-call greeting/script from structured sales-task fields."""

from __future__ import annotations

from typing import Any


DEFAULT_TOOLS = [
    "get_company_knowledge",
    "check_calendar",
    "create_calendar_event",
    "create_conference",
    "send_welcome_email",
    "hangup_call",
]


def build_task_prompt(args: dict[str, Any]) -> dict[str, Any]:
    """Build greeting + playbook for an outbound sales/LPR task."""
    company = (args.get("company") or "").strip()
    contact_name = (args.get("contact_name") or "").strip()
    goal = (args.get("goal") or "найти ЛПР и договориться о консультации").strip()
    product = (args.get("product") or "решения Quantum Labs по массовым выплатам").strip()
    notes = (args.get("notes") or "").strip()
    language = (args.get("language") or "ru").strip().lower()
    find_lpr = bool(args.get("find_lpr", True))
    book_meeting = bool(args.get("book_meeting", True))
    extra_script = (args.get("script") or "").strip()
    greeting_override = (args.get("greeting") or "").strip()

    who = contact_name or ("руководителю" if language.startswith("ru") else "the decision maker")
    co = f" компании {company}" if company else ""

    if greeting_override:
        greeting = greeting_override
    elif language.startswith("ru"):
        greeting = (
            f"Здравствуйте{', ' + contact_name if contact_name else ''}! "
            f"Меня зовут Ава, компания Quantum Labs. "
            f"{'Подскажите, пожалуйста, как лучше связаться с лицом, принимающим решения по выплатам и финансам?' if find_lpr else 'Удобно ли сейчас коротко поговорить?'}"
        )
    else:
        greeting = (
            f"Hello{', ' + contact_name if contact_name else ''}! "
            f"This is Ava from Quantum Labs. "
            f"{'Could you connect me with the decision maker for payouts/finance?' if find_lpr else 'Is this a good time for a short call?'}"
        )

    if extra_script:
        script = extra_script
    elif language.startswith("ru"):
        steps = [
            f"Ты — телефонный агент Quantum Labs. Звонишь {who}{co}.",
            f"Продукт/тема: {product}.",
            f"Цель звонка: {goal}.",
            "",
            "Правила:",
            "1) Представься коротко, уточни удобство разговора.",
        ]
        if find_lpr:
            steps.append(
                "2) Если собеседник не ЛПР — вежливо выясни ФИО/роль ЛПР, "
                "когда перезвонить, добавочный; попроси соединить."
            )
            n = 3
        else:
            n = 2
        steps.append(
            f"{n}) Квалифицируй интерес: есть ли массовые выплаты, банк/расчётный счёт, боль по скорости/комиссии."
        )
        n += 1
        steps.append(f"{n}) Кратко объясни ценность Quantum Labs без воды; не выдумывай факты — при необходимости вызови get_company_knowledge.")
        n += 1
        if book_meeting:
            steps.append(
                f"{n}) При интересе предложи консультацию: check_calendar → create_calendar_event → "
                "create_conference → send_welcome_email. Если слота нет — договорись о перезвоне."
            )
            n += 1
        steps.append(f"{n}) Зафиксируй итог (интересно / не интересно / перезвонить / ЛПР найден). Заверши hangup_call.")
        if notes:
            steps.extend(["", "Контекст от менеджера:", notes])
        script = "\n".join(steps)
    else:
        script = (
            f"You are Quantum Labs phone agent calling {who}{(' at ' + company) if company else ''}.\n"
            f"Product: {product}. Goal: {goal}.\n"
            "Find the decision maker if needed, qualify interest, offer a consultation "
            "(calendar + conference + welcome email), then hang up. Do not invent facts.\n"
            + (f"Manager notes:\n{notes}\n" if notes else "")
        )

    tools = args.get("tools")
    if not isinstance(tools, list) or not tools:
        tools = list(DEFAULT_TOOLS)
    use_knowledge = bool(args.get("use_knowledge", True))

    return {
        "greeting": greeting,
        "script": script,
        "tools": [str(t) for t in tools],
        "use_knowledge": use_knowledge,
        "company": company,
        "contact_name": contact_name,
        "goal": goal,
    }
