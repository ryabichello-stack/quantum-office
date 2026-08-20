"""Outreach email templates (cooperation / industry packs)."""

from __future__ import annotations

from html import escape

from content.packs import LEGAL_FOOTER_HTML, LEGAL_FOOTER_PLAIN, ensure_legal_footer


DEFAULT_PLAIN = """Здравствуйте, {name}!

Мы в Quantum Labs развиваем Quantum Payouts — сервис массовых выплат физлицам
(карта и СБП), а также платёжные сценарии: приём, выплаты, сплитование, удержание
и другие финансовые инструменты под ваш процесс.

Если тема автоматизации расчётов с физлицами для вас актуальна — ответьте на это
письмо, подберём короткое знакомство на 15 минут.

Сайт: {website}{phone_line}

С уважением,
команда {company}
""" + LEGAL_FOOTER_PLAIN

DEFAULT_HTML = """<!DOCTYPE html>
<html lang="ru">
<body style="font-family: Manrope, Segoe UI, sans-serif; line-height: 1.5; color: #1a1a1a; font-size: 15px;">
  <p>Здравствуйте, {name}!</p>
  <p>Мы в <strong>{company}</strong> развиваем <strong>Quantum Payouts</strong> —
  сервис массовых выплат физлицам (карта и СБП), а также платёжные сценарии:
  приём, выплаты, сплитование, удержание и другие финансовые инструменты под ваш процесс.</p>
  <p>Если тема автоматизации расчётов с физлицами для вас актуальна — ответьте на это
  письмо, подберём короткое знакомство на 15 минут.</p>
  <p>Сайт: <a href="{website}">{website}</a></p>
  {phone_html}
  <p>С уважением,<br>команда {company}</p>
""" + LEGAL_FOOTER_HTML + """
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
    plain_src, html_src = ensure_legal_footer(plain_src, html_src)

    mapping_plain = {
        "name": name,
        "company": company,
        "website": site,
        "unsub": unsub,
        "unsub_url": unsub_url,
        "phone": phone_s,
        "phone_line": phone_line,
        "phone_html": phone_html,
    }
    mapping_html = {
        "name": escape(name),
        "company": escape(company),
        "website": escape(site),
        "unsub": escape(unsub),
        "unsub_url": escape(unsub_url),
        "phone": escape(phone_s),
        "phone_line": escape(phone_line),
        "phone_html": phone_html,
    }
    plain = _safe_format(plain_src, mapping_plain)
    html = _safe_format(html_src, mapping_html)
    return plain, html
