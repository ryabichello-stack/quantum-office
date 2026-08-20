"""Industry outreach packs + shared legal footer for Quantum Labs.

Позиционирование (все отрасли):
- технологический партнёр, не посредник;
- клиент заключает прямые договоры с банками;
- помогаем согласовать сильные ставки по рынку + tech + сопровождение;
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

LEGAL_FOOTER_HTML = """
<hr style="border:none;border-top:1px solid #ddd;margin:1.5em 0 0.75em">
<div style="font-size:12px;line-height:1.45;color:#555">
  <p>Вы получили это письмо, потому что ваша компания указана в открытых
  источниках как организация, для которой могут быть актуальны сервисы
  платёжной инфраструктуры Quantum Labs (в т.ч. Quantum Payouts).</p>
  <p>ООО «Квантум Лабс» · <a href="https://quantumlabs.ru">quantumlabs.ru</a>
  · office@quantumlabs.ru</p>
  <p><a href="{unsub_url}" style="color:#c4470f">Отписаться от рассылки</a>
  · или напишите на <a href="mailto:{unsub}?subject=unsubscribe">{unsub}</a></p>
  <p>Обработка обращений — в соответствии с применимым законодательством РФ
  (в т.ч. 152-ФЗ). Письмо носит информационный характер и не является офертой.</p>
</div>
"""

_SIG = (
    "С уважением,\n"
    "команда Quantum Labs\n"
    "Quantum Labs / Quantum Payouts\n"
    "{website}{phone_line}"
)
_SIG_SHORT = "С уважением,\nкоманда Quantum Labs\n{website}{phone_line}"

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
    """Escape HTML, then apply **bold** → <strong>."""
    from html import escape

    parts: list[str] = []
    last = 0
    for m in _MD_BOLD.finditer(text or ""):
        parts.append(escape(text[last : m.start()]))
        parts.append(
            "<strong style='color:#0f1b24'>" + escape(m.group(1)) + "</strong>"
        )
        last = m.end()
    parts.append(escape(text[last:]))
    return "".join(parts)


def _html_from_plain(plain: str) -> str:
    blocks: list[str] = []
    for block in (plain or "").strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = [ln.rstrip() for ln in block.split("\n")]
        bullet_lines = [ln for ln in lines if ln.startswith("- ")]
        if bullet_lines and len(bullet_lines) == len([ln for ln in lines if ln.strip()]):
            items = "".join(
                f"<li style='margin:0.2em 0'>{_inline_md_to_html(ln[2:].strip())}</li>"
                for ln in bullet_lines
            )
            blocks.append(
                "<ul style='margin:0.55em 0 0.55em 1.15em;padding:0'>" + items + "</ul>"
            )
        else:
            inner = _inline_md_to_html(block).replace("\n", "<br>\n")
            blocks.append(f"<p style='margin:0 0 0.85em'>{inner}</p>")
    body = "\n".join(blocks) if blocks else "<p></p>"
    return (
        '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"></head>'
        '<body style="font-family:Manrope,Segoe UI,Helvetica,Arial,sans-serif;'
        "line-height:1.55;color:#1a1a1a;font-size:15px;max-width:640px;"
        'margin:0;padding:8px 4px">'
        f"{body}\n{{legal_html}}</body></html>"
    )


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
        "short": "Выплаты клиентам + прямые договоры с банками, лучшие ставки, tech-партнёр",
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
                    "Мы — **команда Quantum Labs**.\n\n"
                    "Вопрос короткий: **как у вас сейчас устроены выплаты клиентам** — "
                    "наличные, ручные переводы, банк «как получится»?\n\n"
                    "Мы строим **платёжную инфраструктуру для бизнеса**. Для ломбардов "
                    "флагманский сценарий — **выплаты на карты и по СБП** через Quantum Payouts: "
                    "личный кабинет, реестры, API, 1С / ваша учётная система.\n\n"
                    "**Важно:** клиент заключает **прямые договоры с банками**. "
                    "Мы **не посредник**. Мы технологический партнёр: помогаем "
                    "**согласовать сильные ставки по рынку**, подключить технологию "
                    "и сопровождаем дальше в работе.\n\n"
                    "Плюс при необходимости — приём платежей, эквайринг, "
                    "индивидуальные расчётные сценарии.\n\n"
                    "**15 минут** — сравним вашу схему с доступными вариантами "
                    "и скажем честно, есть ли эффект.\n\n"
                    f"{_SIG}"
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
                    f"{_SIG_SHORT}"
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
                    "помогаем **согласовать сильные ставки по рынку** под ваш профиль "
                    "и объём — при **прямом договоре клиента с банком**.\n\n"
                    "Что сравниваем:\n"
                    "- текущий способ выплат;\n"
                    "- объём и число операций;\n"
                    "- стоимость схемы;\n"
                    "- нужна ли интеграция с учётом.\n\n"
                    "Итог: **есть ли смысл что-то менять** — или нет. Без давления.\n\n"
                    "Хватит **ориентировочных цифр** в ответ на это письмо.\n\n"
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    "помощь со **ставками по рынку** и сопровождение.\n\n"
                    "Если вопрос не к вам — **подскажите коллегу**, кому корректнее написать.\n\n"
                    f"{_SIG}"
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
                    "Мы — **команда Quantum Labs**.\n\n"
                    "**Как у вас устроена выдача займа клиенту** — реестры, касса, банк-партнёр?\n\n"
                    "Мы строим **платёжную инфраструктуру**: выдача на **карты и СБП**, "
                    "API, статусы, сверка. Клиент заключает **прямые договоры с банками** — "
                    "мы **не посредник**, а технологический партнёр: "
                    "**ставки по рынку**, подключение, сопровождение.\n\n"
                    "**15 минут** — сравним вашу схему с вариантами под объёмы {company}.\n\n"
                    f"{_SIG}"
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
                    f"{_SIG_SHORT}"
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
                    "Как tech-партнёр поможем понять, можно ли **усилить ставки и процесс** "
                    "при прямом банковском договоре.\n\n"
                    "Хватит ориентировочных цифр в ответе.\n\n"
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG}"
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
                    "Мы — **команда Quantum Labs**.\n\n"
                    "При выкупе у физлиц узкое место часто одно: "
                    "**быстро и прозрачно выплатить продавцу**.\n\n"
                    "Quantum Payouts — **карты и СБП**, привязка к сделке, API, статусы. "
                    "Клиент работает по **прямому договору с банком**; мы — "
                    "**технологический партнёр**: помогаем со **ставками по рынку**, "
                    "подключением и сопровождением.\n\n"
                    "**15 минут** — сравним, как это ляжет на процесс {company}.\n\n"
                    f"{_SIG}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG}"
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
                    "Мы — **команда Quantum Labs**.\n\n"
                    "У гиг-сервисов боль обычно одна: **масштаб выплат** курьерам/водителям "
                    "без ручных реестров и сюрпризов по статусам.\n\n"
                    "Делаем **платёжную инфраструктуру**: СБП/карты, API, сверка. "
                    "Вы — в **прямом договоре с банком**; мы помогаем "
                    "**согласовать сильные ставки**, подключить tech и сопровождаем.\n\n"
                    "**15 минут** — сравним схему {company} с вариантами.\n\n"
                    f"{_SIG}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG}"
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
                    "Мы — **команда Quantum Labs**.\n\n"
                    "В пунктах приёма критично: **быстро отдать деньги физлицу** "
                    "и не потерять сверку по сети.\n\n"
                    "**Карты и СБП**, лимиты точек, статусы, API. "
                    "Договор с банком — **ваш прямой**; мы — tech-партнёр: "
                    "**ставки по рынку**, подключение, сопровождение.\n\n"
                    "**15 минут** — сравним схему {company}.\n\n"
                    f"{_SIG}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG_SHORT}"
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
                    f"{_SIG}"
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
    pack = get_pack(pack_id)
    if not pack:
        return None
    step1 = pack["steps"][0]
    return {
        "pack_id": pack["id"],
        "title": pack["title"],
        "short": pack.get("short") or "",
        "audience": pack.get("audience") or "",
        "subject": step1["subject"],
        "plain": step1["plain"],
        "html": step1["html"],
        "attach_presentation_default": bool(pack.get("attach_presentation_default")),
        "presentation": pack.get("presentation") or "quantum_payouts_presentation_small.pdf",
        "steps": [
            {
                "step": s["step"],
                "delay_days": s["delay_days"],
                "label": s["label"],
                "subject": s["subject"],
                "attach_presentation": bool(s.get("attach_presentation")),
            }
            for s in pack["steps"]
        ],
    }
