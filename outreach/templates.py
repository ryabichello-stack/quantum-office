"""Outreach email templates (cooperation / сотрудничество)."""

from __future__ import annotations

from html import escape


DEFAULT_PLAIN = """Здравствуйте, {name}!

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
  <p>Здравствуйте, {name}!</p>
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
    name = (contact_name or "коллега").strip() or "коллега"
    company = company_name.strip() or "Quantum Labs"
    site = website.strip() or "https://quantumlabs.ru"
    unsub = unsubscribe_mailto.strip() or "office@quantumlabs.ru"
    unsub_url = (unsubscribe_url or "").strip() or f"mailto:{unsub}?subject=unsubscribe"
    phone_s = phone.strip()
    phone_line = f"\nТелефон: {phone_s}" if phone_s else ""
    phone_html = f"<p>Телефон: {escape(phone_s)}</p>" if phone_s else ""

    plain_src = (plain_template or "").strip() or DEFAULT_PLAIN
    html_src = (html_template or "").strip() or DEFAULT_HTML

    plain = _safe_format(
        plain_src,
        {
            "name": name,
            "company": company,
            "website": site,
            "unsub": unsub,
            "unsub_url": unsub_url,
            "phone": phone_s,
            "phone_line": phone_line,
            "phone_html": phone_html,
        },
    )
    html = _safe_format(
        html_src,
        {
            "name": escape(name),
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
