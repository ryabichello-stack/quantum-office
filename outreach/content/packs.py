"""Industry outreach packs + shared legal footer for Quantum Labs.

Позиционирование (все отрасли):
- технологический партнёр, не посредник;
- клиент заключает прямые договоры с банками;
- помогаем согласовать для партнёров минимальные ставки комиссии по рынку + tech + сопровождение;
- продающий текст с хуками и **жирными** акцентами.

Ломбарды: каркас playbook (5 касаний, дни 0/3/6/10/15).
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

LEGAL_FOOTER_PLAIN = """
---
Вы получили это письмо, потому что ваша компания указана в открытых
источниках как организация, для которой могут быть актуальны сервисы
платёжной инфраструктуры Quantum Labs (в т.ч. Quantum Payouts).

ООО «Квантум Лабс» · quantumlabs.ru · office@quantumlabs.ru
Если письмо вам неинтересно или вы не хотите получать подобные сообщения —
нажмите «Отписаться»: {unsub_url}
Либо ответьте «стоп» / напишите на {unsub} с темой unsubscribe.

Обработка обращений: в соответствии с применимым законодательством РФ
(в т.ч. 152-ФЗ). Это коммерческое предложение, не оферта.
"""

# HTML legal row — canonical card footer (from email_chrome)
from content.email_chrome import LEGAL_FOOTER_HTML as LEGAL_FOOTER_HTML  # noqa: E402

# Packs end with {signature}; text comes from OUTREACH_SIGNATURE in Campaign UI.

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def strip_md_bold(text: str) -> str:
    return _MD_BOLD.sub(r"\1", text or "")


def ensure_legal_footer(plain: str, html: str) -> tuple[str, str]:
    p = plain or ""
    h = html or ""
    if "{unsub_url}" not in p and "Отписаться" not in p:
        p = p.rstrip() + "\n" + LEGAL_FOOTER_PLAIN
    elif "152-ФЗ" not in p and "ООО" not in p:
        p = p.rstrip() + "\n" + LEGAL_FOOTER_PLAIN
    if "{unsub_url}" not in h and "Отписаться" not in h:
        h = h.rstrip() + "\n" + LEGAL_FOOTER_HTML
    elif "152-ФЗ" not in h:
        h = h.rstrip() + "\n" + LEGAL_FOOTER_HTML
    return p, h


def _inline_md_to_html(text: str) -> str:
    """Escape HTML, then apply **bold** → canonical strong."""
    from content.email_chrome import inline_md_to_html

    return inline_md_to_html(text)


_ALL_BOLD = re.compile(r"^\*\*(.+)\*\*$", re.DOTALL)


def _all_bold_text(block: str) -> str | None:
    m = _ALL_BOLD.match((block or "").strip())
    return m.group(1).strip() if m else None


def _html_from_plain(plain: str) -> str:
    """Build letter body in canonical layout.

    Structure (matches quantum-labs-outreach.html):
    1. Greeting on the white card.
    2. Optional ``**headline**`` → H1 on the white card.
    3. Lead paragraphs on the white card.
    4. Optional title line + ``-`` bullets → soft benefits panel.
    5. Optional ``**CTA title**`` + muted lead on the white card.
    6. Button CTA is injected later into ``{callback_cta}``.
    """
    from content.email_chrome import (
        FONT,
        INK_BODY,
        INK_HEAD,
        INK_MUTED,
        benefits_box_html,
        soft_panel_html,
        wrap_letter_html,
    )

    def _para(text: str, *, last: bool = False, size: int = 16, color: str = INK_BODY) -> str:
        inner = _inline_md_to_html(text).replace("\n", "<br>\n")
        margin = "0" if last else "0 0 18px"
        return (
            f'<p style="margin:{margin};font-size:{size}px;line-height:{size + 8}px;'
            f'color:{color};font-family:{FONT};">{inner}</p>'
        )

    def _h1(text: str) -> str:
        return (
            f'<h1 style="margin:0 0 16px;font-size:25px;line-height:32px;'
            f'letter-spacing:-.4px;color:{INK_HEAD};font-family:{FONT};font-weight:700;">'
            f"{_inline_md_to_html(text)}</h1>"
        )

    def _cta_title(text: str) -> str:
        return (
            f'<p style="margin:24px 0 8px;font-size:17px;line-height:25px;font-weight:700;'
            f'color:{INK_HEAD};font-family:{FONT};">{_inline_md_to_html(text)}</p>'
        )

    def _flush_prose(buf: list[str], *, soft: bool = False) -> str:
        if not buf:
            return ""
        parts = [_para(t, last=(i == len(buf) - 1)) for i, t in enumerate(buf)]
        joined = "\n".join(parts)
        return soft_panel_html(joined) if soft else joined

    greeting_html = ""
    out: list[str] = []
    lead_buf: list[str] = []
    after_benefits = False
    saw_greeting = False
    saw_headline = False
    pending_benefits_title: str | None = None

    blocks = [b.strip() for b in (plain or "").strip().split("\n\n") if b.strip()]

    for bi, block in enumerate(blocks):
        if block in ("{signature}", "{logo_header}", "{callback_cta}", "{legal_html}"):
            continue
        lines = [ln.rstrip() for ln in block.split("\n")]
        non_empty = [ln for ln in lines if ln.strip()]
        bullet_lines = [ln for ln in lines if ln.startswith("- ")]
        is_bullets = bool(bullet_lines) and len(bullet_lines) == len(non_empty)
        bold_only = _all_bold_text(block)

        # Title line immediately before a bullet block
        if (
            not is_bullets
            and pending_benefits_title is None
            and bi + 1 < len(blocks)
        ):
            nxt = blocks[bi + 1]
            nxt_lines = [ln.rstrip() for ln in nxt.split("\n") if ln.strip()]
            nxt_bullets = [ln for ln in nxt_lines if ln.startswith("- ")]
            if nxt_bullets and len(nxt_bullets) == len(nxt_lines) and not bold_only:
                pending_benefits_title = block
                continue

        if is_bullets:
            flushed = _flush_prose(lead_buf, soft=False)
            if flushed:
                out.append(flushed)
            lead_buf = []
            title = pending_benefits_title or "Что получает ваша команда"
            pending_benefits_title = None
            out.append(
                benefits_box_html(
                    title=title,
                    items=[ln[2:].strip() for ln in bullet_lines],
                )
            )
            after_benefits = True
            continue

        if not saw_greeting:
            greeting_html = _para(block)
            saw_greeting = True
            continue

        if bold_only and not saw_headline and not after_benefits:
            flushed = _flush_prose(lead_buf, soft=False)
            if flushed:
                out.append(flushed)
            lead_buf = []
            out.append(_h1(bold_only))
            saw_headline = True
            continue

        if bold_only and after_benefits:
            flushed = _flush_prose(lead_buf, soft=False)
            if flushed:
                out.append(flushed)
            lead_buf = []
            out.append(_cta_title(bold_only))
            continue

        if after_benefits and not bold_only and not lead_buf and out and "font-size:17px" in out[-1]:
            # First paragraph after CTA title → muted lead (canonical)
            out.append(
                _para(block, size=15, color=INK_MUTED)
            )
            continue

        lead_buf.append(block)

    flushed = _flush_prose(lead_buf, soft=False)
    if flushed:
        out.append(flushed)

    body = (greeting_html + "\n" + "\n".join(out)).strip() if (greeting_html or out) else "<p></p>"
    return wrap_letter_html(body)


def wrap_letter_html(inner: str) -> str:
    from content.email_chrome import wrap_letter_html as _wrap

    return _wrap(inner)


def ensure_letter_chrome(html: str) -> str:
    """If a saved Campaign template is a flat body, wrap it in the canonical shell."""
    from content.email_chrome import PAGE_BG, has_canonical_chrome, wrap_letter_html

    raw = (html or "").strip()
    if not raw:
        return raw
    if has_canonical_chrome(raw) or PAGE_BG in raw:
        return raw
    # legacy warm shells
    if "background:#ebe6de" in raw or "background:#f3f1ec" in raw:
        # Re-extract body and re-wrap into canonical
        pass

    lower = raw.lower()
    start = lower.find("<body")
    if start >= 0:
        gt = raw.find(">", start)
        end = lower.rfind("</body>")
        if gt >= 0 and end > gt:
            inner = raw[gt + 1 : end].strip()
        else:
            inner = raw
    elif raw.lstrip().lower().startswith("<!doctype") or raw.lstrip().lower().startswith(
        "<html"
    ):
        # Full document without our tokens — extract main content if possible
        # Fall through to body-less extract of everything between first/last meaningful tags
        return raw if "{logo_header}" in raw and "{signature}" in raw else raw
    else:
        inner = raw

    # Strip old chrome fragments / placeholders that the new shell provides as rows
    for tok in ("{logo_header}", "{signature}", "{legal_html}", "{callback_cta}"):
        inner = inner.replace(tok, "")
    # Soften old strong colors
    inner = inner.replace("style='color:#0f1b24'", "style='font-weight:700;color:#142a4a'")
    inner = inner.replace('style="color:#0f1b24"', 'style="font-weight:700;color:#142a4a"')
    inner = inner.replace("margin:0 0 0.85em", "margin:0 0 18px")
    inner = inner.replace("margin:0 0 1.05em", "margin:0 0 18px")
    return wrap_letter_html(inner.strip())

def _step(
    *,
    step: int,
    delay_days: int,
    label: str,
    subject: str,
    plain: str,
    attach_presentation: bool = False,
) -> dict[str, Any]:
    html = _html_from_plain(plain).replace("{legal_html}", LEGAL_FOOTER_HTML)
    # Store plain with ** for editor preview of intent; sender strips via render
    plain_full = plain.rstrip() + "\n" + LEGAL_FOOTER_PLAIN
    return {
        "step": step,
        "delay_days": delay_days,
        "label": label,
        "subject": subject,
        "plain": plain_full,
        "html": html,
        "attach_presentation": attach_presentation,
    }


# ---------------------------------------------------------------------------
# Packs
# ---------------------------------------------------------------------------

PACKS: dict[str, dict[str, Any]] = {
    "lombards": {
        "id": "lombards",
        "title": "Ломбарды",
        "short": "Выплаты клиентам + прямые договоры с банками, минимальные ставки комиссии, tech-партнёр",
        "audience": "ломбарды и ломбардные сети",
        "attach_presentation_default": True,
        "presentation": "presentations/lombards.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выплаты клиентам ломбарда на карты и по СБП — без посредника",
                attach_presentation=True,
                plain=(
                    "{greeting}\n\n"
                    "**Выплаты клиентам ломбарда на карты и СБП — без лишней ручной работы**\n\n"
                    "Quantum Labs помогает выстроить платёжную инфраструктуру для выплат клиентам: "
                    "карты, СБП, реестры, API, статусы операций и сверка по сети.\n\n"
                    "Что получает ваша команда\n\n"
                    "- Выплаты на карты и через СБП\n"
                    "- Реестры, API и связка с 1С / вашей учётной системой\n"
                    "- Прямые договоры с банками; Quantum Labs — технологический партнёр\n"
                    "- Помогаем согласовать для партнёров **минимальные ставки комиссии по рынку**\n\n"
                    "**За 15 минут сравним вашу текущую схему с вариантами под ваши объёмы.**\n\n"
                    "Покажем, где можно убрать ручные операции и ускорить выдачу клиенту.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="scenarios",
                subject="Как выглядит выплата клиенту ломбарда «из вашей системы»",
                plain=(
                    "{greeting}\n\n"
                    "Продолжу без воды — **конкретный сценарий для ломбарда**:\n\n"
                    "- выплата клиенту **на карту** или **по СБП**;\n"
                    "- массовые операции **по реестру**;\n"
                    "- выплата **прямо из учётной системы**;\n"
                    "- **статусы**, сверка, централизация по сети.\n\n"
                    "Типовой путь:\n\n"
                    "**сделка → способ получения → выплата из вашей системы → "
                    "деньги клиенту → статус обратно в учёт.**\n\n"
                    "Банк при этом — **ваш прямой договор**. Мы помогаем подобрать "
                    "контур и **согласовать экономику под ваши объёмы**, "
                    "а не «продаём чужой тариф внагрузку».\n\n"
                    "Напишите **ориентировочный объём выплат в месяц** — "
                    "вернёмся с вариантами по делу.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=3,
                delay_days=6,
                label="economics",
                subject="Сравним вашу экономику выплат — без обязательств менять банк",
                plain=(
                    "{greeting}\n\n"
                    "Самый честный вход: **не ломать работающую схему**, а сначала **сравнить**.\n\n"
                    "Мы работаем с **ведущими банками страны** и как технологический партнёр "
                    "помогаем **согласовать минимальные ставки комиссии по рынку** под ваш профиль "
                    "и объём — при **прямом договоре клиента с банком**.\n\n"
                    "Что сравниваем:\n"
                    "- текущий способ выплат;\n"
                    "- объём и число операций;\n"
                    "- стоимость схемы;\n"
                    "- нужна ли интеграция с учётом.\n\n"
                    "Итог: **есть ли смысл что-то менять** — или нет. Без давления.\n\n"
                    "Хватит **ориентировочных цифр** в ответ на это письмо.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=4,
                delay_days=10,
                label="broader",
                subject="Если выплаты «не сейчас»: весь платёжный контур Quantum Labs",
                plain=(
                    "{greeting}\n\n"
                    "Если **выплаты** сейчас не в приоритете — оставлю карту шире.\n\n"
                    "**Quantum Labs = платёжная инфраструктура**, а не один сервис. "
                    "Quantum Payouts — часть контура.\n\n"
                    "Также:\n"
                    "- приём платежей и **эквайринг**;\n"
                    "- **API** и автоматизация сверки;\n"
                    "- платёжный слой под ваш продукт;\n"
                    "- специальные расчётные сценарии.\n\n"
                    "Снова: **прямые договоры с банками**, мы — tech-партнёр "
                    "по подключению, ставкам и сопровождению.\n\n"
                    "Есть задача, которую банк/провайдер решает **дорого или вручную**? "
                    "Опишите одним абзацем — предложим архитектуру.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=5,
                delay_days=15,
                label="close",
                subject="Закрываю тему — остаюсь на связи по платежам",
                plain=(
                    "{greeting}\n\n"
                    "Закрываю переписку, чтобы **не быть навязчивым**.\n\n"
                    "Когда всплывут **выплаты клиентам, СБП, эквайринг или интеграция** — "
                    "Quantum Labs рядом: **tech-партнёр**, прямые банковские договоры, "
                    "помощь с **минимальными ставками комиссии по рынку** и сопровождение.\n\n"
                    "Если вопрос не к вам — **подскажите коллегу**, кому корректнее написать.\n\n"
                    "{signature}"
                ),
            ),
        ],
    },
    "mfo": {
        "id": "mfo",
        "title": "МФО",
        "short": "Выдача займов на карты/СБП: прямой банк + tech-партнёр Quantum",
        "audience": "микрофинансовые организации",
        "attach_presentation_default": True,
        "presentation": "presentations/mfo.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выдача займов на карты и СБП — прямой банк, мы tech-партнёр",
                attach_presentation=True,
                plain=(
                    "{greeting}\n\n"
                    "**Выдача займов на карты и СБП — без лишней ручной работы**\n\n"
                    "Quantum Labs помогает выстроить платёжную инфраструктуру для выдач: "
                    "карты, СБП, API, статусы операций и сверка.\n\n"
                    "Что получает ваша команда\n\n"
                    "- Выдачи на карты и через СБП\n"
                    "- Единый API: статусы и сверка операций\n"
                    "- Прямые договоры с банками; Quantum Labs — технологический партнёр\n"
                    "- Помогаем согласовать для партнёров **минимальные ставки комиссии по рынку**\n\n"
                    "**За 15 минут сравним вашу текущую схему с вариантами под ваши объёмы.**\n\n"
                    "Покажем, где можно сократить ручные операции и ускорить выдачу.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="scenarios",
                subject="Выдача МФО «из вашей системы»: карта, СБП, статусы",
                plain=(
                    "{greeting}\n\n"
                    "Сценарий, который обычно заходит МФО:\n\n"
                    "**заявка одобрена → выплата из вашей системы → деньги клиенту → "
                    "статус банка обратно в учёт.**\n\n"
                    "Плюс реестры, антидубли, роли. Банк — **ваш прямой договор**; "
                    "мы помогаем **согласовать экономику** и встроить технологию.\n\n"
                    "Пришлите **объём выдач в месяц** — ответим вариантами.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=3,
                delay_days=6,
                label="economics",
                subject="Сравнить стоимость выдач — без обязательства менять схему",
                plain=(
                    "{greeting}\n\n"
                    "Сначала **сравнение**, не «внедрение любой ценой».\n\n"
                    "Сверим способ, объём, стоимость, нужен ли API. "
                    "Как tech-партнёр поможем понять, можно ли **снизить комиссию до минимальных ставок по рынку** "
                    "и усилить процесс "
                    "при прямом банковском договоре.\n\n"
                    "Хватит ориентировочных цифр в ответе.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=4,
                delay_days=10,
                label="broader",
                subject="Шире выдач: платёжный контур Quantum Labs для МФО",
                plain=(
                    "{greeting}\n\n"
                    "Если выдача не в фокусе — закрываем и **приём, эквайринг, API, "
                    "специальные сценарии**. Снова: **прямой банк**, мы — инфраструктура "
                    "и сопровождение.\n\n"
                    "Опишите задачу {company} — предложим архитектуру.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=5,
                delay_days=15,
                label="close",
                subject="Закрываю тему по выплатам МФО",
                plain=(
                    "{greeting}\n\n"
                    "Закрываю тему. Когда всплывут **выдачи, СБП или банковский контур** — "
                    "на связи. Подскажете коллегу, если вопрос не ваш?\n\n"
                    "{signature}"
                ),
            ),
        ],
    },
    "trade_in": {
        "id": "trade_in",
        "title": "Trade-in / выкуп",
        "short": "Выплаты продавцам: прямой банк + tech Quantum Labs",
        "audience": "trade-in, автовыкуп, выкуп техники и товаров",
        "attach_presentation_default": True,
        "presentation": "presentations/trade_in.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выплата продавцу при выкупе — быстро, на карту/СБП, без посредника",
                attach_presentation=True,
                plain=(
                    "{greeting}\n\n"
                    "**Выплата продавцу при выкупе — быстро, на карту и СБП**\n\n"
                    "Quantum Labs помогает выстроить платёжную инфраструктуру для выплат "
                    "физлицам при trade-in и выкупе: карты, СБП, привязка к сделке, API и статусы.\n\n"
                    "Что получает ваша команда\n\n"
                    "- Выплаты продавцу на карты и через СБП\n"
                    "- Привязка к сделке, статусы и сверка операций\n"
                    "- Прямые договоры с банками; Quantum Labs — технологический партнёр\n"
                    "- Помогаем согласовать для партнёров **минимальные ставки комиссии по рынку**\n\n"
                    "**За 15 минут сравним, как это ляжет на процесс {company}.**\n\n"
                    "Покажем, где ускорить выплату продавцу и убрать ручные операции.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="scenarios",
                subject="Сценарий: оценка → выплата продавцу → статус в сделку",
                plain=(
                    "{greeting}\n\n"
                    "**Оценка согласована → выплата из вашей системы → деньги продавцу → "
                    "статус в сделку.**\n\n"
                    "Реестры, лимиты точек, сеть — закрываем. Банк ваш; экономика — "
                    "подбираем вместе под объём.\n\n"
                    "Напишите **месячный объём выплат** — вернёмся предметно.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=3,
                delay_days=6,
                label="economics",
                subject="Сравнить стоимость выплат продавцам?",
                plain=(
                    "{greeting}\n\n"
                    "Сравним текущую стоимость и процесс — **без обязательства менять банк**. "
                    "Как tech-партнёр подскажем, где можно **усилить ставки и скорость**.\n\n"
                    "Достаточно ориентировочных цифр.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=4,
                delay_days=10,
                label="broader",
                subject="Выкуп + приём/эквайринг/сплит — один tech-партнёр",
                plain=(
                    "{greeting}\n\n"
                    "Если выплата продавцам «не сейчас» — можем закрыть "
                    "**приём, эквайринг, сплитование, API** под несколько юрлиц. "
                    "Прямые банковские договоры + наша технология.\n\n"
                    "Опишите сценарий {company}.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=5,
                delay_days=15,
                label="close",
                subject="Закрываю тему по выплатам выкупа",
                plain=(
                    "{greeting}\n\n"
                    "Закрываю переписку. Когда выплаты при выкупе станут актуальны — "
                    "на связи. Подскажете коллегу?\n\n"
                    "{signature}"
                ),
            ),
        ],
    },
    "gig": {
        "id": "gig",
        "title": "Гиг / курьеры / такси",
        "short": "Выплаты исполнителям: прямой банк + инфраструктура Quantum",
        "audience": "платформы гиг-экономики, курьерские и такси-сервисы",
        "attach_presentation_default": True,
        "presentation": "presentations/gig.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выплаты исполнителям на карты и СБП — tech-партнёр, не посредник",
                attach_presentation=True,
                plain=(
                    "{greeting}\n\n"
                    "**Выплаты исполнителям на карты и СБП — без ручных реестров**\n\n"
                    "Quantum Labs помогает выстроить платёжную инфраструктуру для гиг-сервисов: "
                    "масштаб выплат курьерам и водителям, СБП/карты, API, статусы и сверка.\n\n"
                    "Что получает ваша команда\n\n"
                    "- Регулярные выплаты на карты и через СБП\n"
                    "- Фонд выплат, API и статусы для поддержки и финансов\n"
                    "- Прямые договоры с банками; Quantum Labs — технологический партнёр\n"
                    "- Помогаем согласовать для партнёров **минимальные ставки комиссии по рынку**\n\n"
                    "**За 15 минут сравним схему {company} с вариантами под ваши объёмы.**\n\n"
                    "Покажем, где снять ручные операции и ускорить выплаты исполнителям.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="scenarios",
                subject="Фонд выплат исполнителям: реестр, API, статусы",
                plain=(
                    "{greeting}\n\n"
                    "Типовой контур:\n"
                    "- регулярные **СБП / карта**;\n"
                    "- **реестр фонда**;\n"
                    "- статусы для поддержки и финансов;\n"
                    "- **API из вашей системы**.\n\n"
                    "Пришлите ориентир по **объёму фонда в месяц** — разберём варианты.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=3,
                delay_days=6,
                label="economics",
                subject="Сравнить экономику выплат исполнителям?",
                plain=(
                    "{greeting}\n\n"
                    "Сравним стоимость и процесс **без обязательства менять**. "
                    "Подскажем, где рынок позволяет **усилить ставки** "
                    "при прямом банковском договоре.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=4,
                delay_days=10,
                label="broader",
                subject="Платёжный слой под ваш продукт — Quantum Labs",
                plain=(
                    "{greeting}\n\n"
                    "Шире выплат: **приём, эквайринг, платёжный слой**, автоматизация. "
                    "Прямой банк + наша технология.\n\n"
                    "Опишите задачу — предложим архитектуру.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=5,
                delay_days=15,
                label="close",
                subject="Закрываю тему по выплатам исполнителям",
                plain=(
                    "{greeting}\n\n"
                    "Закрываю тему. Когда масштабирование выплат станет актуальным — "
                    "на связи. Подскажете коллегу?\n\n"
                    "{signature}"
                ),
            ),
        ],
    },
    "scrap": {
        "id": "scrap",
        "title": "Вторсырьё / металлолом",
        "short": "Выплаты сдатчикам: прямой банк + сверка сети с Quantum",
        "audience": "пункты приёма лома и вторсырья",
        "attach_presentation_default": True,
        "presentation": "presentations/scrap.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выплата сдатчику на карту/СБП — быстро, по точкам, без посредника",
                attach_presentation=True,
                plain=(
                    "{greeting}\n\n"
                    "**Выплата сдатчику на карту и СБП — быстро, по точкам**\n\n"
                    "Quantum Labs помогает выстроить платёжную инфраструктуру для пунктов приёма: "
                    "быстро отдать деньги физлицу, лимиты точек, статусы, API и сверка по сети.\n\n"
                    "Что получает ваша команда\n\n"
                    "- Выплаты сдатчику на карты и через СБП\n"
                    "- Лимиты точек, статусы и единый контур сети\n"
                    "- Прямые договоры с банками; Quantum Labs — технологический партнёр\n"
                    "- Помогаем согласовать для партнёров **минимальные ставки комиссии по рынку**\n\n"
                    "**За 15 минут сравним схему {company} с вариантами под ваши объёмы.**\n\n"
                    "Покажем, где ускорить расчёт со сдатчиком и не потерять сверку.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="scenarios",
                subject="Приём → выплата сдатчику → статус в учёт",
                plain=(
                    "{greeting}\n\n"
                    "**Приём оформлен → выплата из системы → деньги сдатчику → статус в учёт.**\n\n"
                    "Лимиты, роли, единый контур сети. Напишите **объём выплат в месяц** — "
                    "вернёмся с вариантами.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=3,
                delay_days=6,
                label="economics",
                subject="Сравнить стоимость расчётов со сдатчиками?",
                plain=(
                    "{greeting}\n\n"
                    "Сравним способ и стоимость — скажем, есть ли смысл усиливать "
                    "**ставки и автоматизацию** при прямом банковском договоре.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=4,
                delay_days=10,
                label="broader",
                subject="Сеть пунктов: выплаты + приём/эквайринг с Quantum Labs",
                plain=(
                    "{greeting}\n\n"
                    "Можем закрыть не только выплаты сдатчикам, но и **приём/эквайринг** "
                    "и более сложные сценарии сети. Прямой банк + наша технология.\n\n"
                    "{signature}"
                ),
            ),
            _step(
                step=5,
                delay_days=15,
                label="close",
                subject="Закрываю тему по выплатам сдатчикам",
                plain=(
                    "{greeting}\n\n"
                    "Закрываю переписку. Когда безнал и сверка сети понадобятся — "
                    "на связи. Подскажете коллегу?\n\n"
                    "{signature}"
                ),
            ),
        ],
    },
}


def list_packs() -> list[dict[str, Any]]:
    out = []
    for p in PACKS.values():
        out.append(
            {
                "id": p["id"],
                "title": p["title"],
                "short": p["short"],
                "audience": p["audience"],
                "steps": len(p["steps"]),
                "attach_presentation_default": bool(p.get("attach_presentation_default")),
                "presentation": p.get("presentation") or "quantum_payouts_presentation_small.pdf",
            }
        )
    return out


def get_pack(pack_id: str) -> dict[str, Any] | None:
    pid = (pack_id or "").strip().lower().replace("-", "_")
    aliases = {
        "trade-in": "trade_in",
        "lombard": "lombards",
        "ломбарды": "lombards",
        "pawnshop": "lombards",
        "pawnshops": "lombards",
        "scrap_metal": "scrap",
        "metal": "scrap",
        "taxi": "gig",
        "couriers": "gig",
    }
    pid = aliases.get(pid, pid)
    pack = PACKS.get(pid)
    return deepcopy(pack) if pack else None


def pack_campaign_templates(pack_id: str) -> dict[str, Any] | None:
    """Backward-compatible step-1 campaign payload (no draft overlay)."""
    from content.pack_drafts import pack_letters_payload

    pack = get_pack(pack_id)
    if not pack:
        return None
    return pack_letters_payload(pack)
