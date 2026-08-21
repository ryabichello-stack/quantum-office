"""Outreach email templates (cooperation / сотрудничество)."""

from __future__ import annotations

from html import escape

_WEAK_NAMES = frozenset(
    {
        "",
        "коллега",
        "тест",
        "test",
        "you",
        "unknown",
        "клиент",
        "contact",
        "name",
        "user",
        "руководитель",
    }
)
_COMPANY_MARKERS = (
    "ооо",
    "оао",
    "зао",
    "пао",
    "ао ",
    " ао",
    "ип ",
    "общество с ограничен",
    "ломбард ",
    " ltd",
    "llc",
    "inc.",
)


def _looks_like_company(name: str) -> bool:
    low = f" {name.lower()} "
    if any(m in low for m in _COMPANY_MARKERS):
        return True
    letters = [c for c in name if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.85:
        return True
    return False


def resolve_greeting(contact_name: str | None) -> tuple[str, str]:
    """Return (greeting_line, display_name). Prefer Имя + Отчество."""
    from geo_schedule import _looks_like_patronymic, split_russian_fio

    raw = (contact_name or "").strip()
    if (
        not raw
        or raw.lower() in _WEAK_NAMES
        or "@" in raw
        or len(raw) < 2
        or _looks_like_company(raw)
    ):
        return "Уважаемый руководитель, добрый день!", "руководитель"

    parts = raw.replace(",", " ").split()
    if len(parts) == 2 and all(p[:1].isupper() for p in parts if p):
        if _looks_like_patronymic(parts[1]):
            greet = f"{parts[0]} {parts[1]}"
            return f"{greet}, добрый день!", greet

    fio = split_russian_fio(raw)
    if fio.greeting:
        return f"{fio.greeting}, добрый день!", fio.greeting
    return f"{raw}, добрый день!", raw


DEFAULT_PLAIN = """{greeting}

Меня зовут команда {company}. Пишем по поводу возможного сотрудничества:
AI-секретарь для телефонии, автоматизация записи и follow-up по заявкам.

Если тема актуальна — ответьте на это письмо, подберём короткое знакомство.

Сайт: {website}{phone_line}

С уважением,
{company}

---
Отписаться: {unsub_url}
Или mailto:{unsub}?subject=unsubscribe
"""

DEFAULT_HTML = """<!DOCTYPE html>
<html lang="ru">
<body style="font-family: Georgia, 'Times New Roman', serif; line-height: 1.5; color: #1a1a1a;">
  <p>{greeting}</p>
  <p>Меня зовут команда <strong>{company}</strong>. Пишем по поводу возможного
  сотрудничества: AI-секретарь для телефонии, автоматизация записи и follow-up по заявкам.</p>
  <p>Если тема актуальна — ответьте на это письмо, подберём короткое знакомство.</p>
  <p>Сайт: <a href="{website}">{website}</a></p>
  {phone_html}
  <p>С уважением,<br>{company}</p>
  <hr>
  <p style="font-size: 12px; color: #555;">
    <a href="{unsub_url}">Отписаться</a>
    · <a href="mailto:{unsub}?subject=unsubscribe">mailto</a>
  </p>
</body>
</html>
"""


def _safe_format(template: str, mapping: dict[str, str]) -> str:
    class _Map(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(_Map(**mapping))


def render_cooperation(
    *,
    contact_name: str,
    company_name: str,
    website: str,
    phone: str,
    unsubscribe_mailto: str,
    unsubscribe_url: str | None = None,
    plain_template: str | None = None,
    html_template: str | None = None,
) -> tuple[str, str]:
    greeting, name = resolve_greeting(contact_name)
    company = company_name.strip() or "Quantum Labs"
    site = website.strip() or "https://quantumlabs.ru"
    unsub = unsubscribe_mailto.strip() or "office@quantumlabs.ru"
    unsub_url = (unsubscribe_url or "").strip() or f"mailto:{unsub}?subject=unsubscribe"
    phone_s = phone.strip()
    phone_line = f"\nТелефон: {phone_s}" if phone_s else ""
    phone_html = f"<p>Телефон: {escape(phone_s)}</p>" if phone_s else ""

    plain_src = (plain_template or "").strip() or DEFAULT_PLAIN
    html_src = (html_template or "").strip() or DEFAULT_HTML

    mapping = {
        "name": name,
        "greeting": greeting,
        "company": company,
        "website": site,
        "unsub": unsub,
        "unsub_url": unsub_url,
        "phone": phone_s,
        "phone_line": phone_line,
        "phone_html": phone_html,
    }
    plain = _safe_format(plain_src, mapping)
    html = _safe_format(
        html_src,
        {
            **mapping,
            "name": escape(name),
            "greeting": escape(greeting),
            "company": escape(company),
            "website": escape(site),
            "unsub": escape(unsub),
            "unsub_url": escape(unsub_url),
            "phone": escape(phone_s),
            "phone_line": escape(phone_line),
            "phone_html": phone_html,
        },
    )
    return plain, html
