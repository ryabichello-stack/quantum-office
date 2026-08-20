"""Industry outreach packs + shared legal footer for Quantum Labs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# ---------------------------------------------------------------------------
# Legal / compliance block (always appended if missing)
# ---------------------------------------------------------------------------

LEGAL_FOOTER_PLAIN = """
---
Вы получили это письмо, потому что ваша компания указана в открытых
источниках как организация, для которой могут быть актуальны сервисы
массовых выплат и платёжных сценариев Quantum Labs (Quantum Payouts).

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
  источчниках как организация, для которой могут быть актуальны сервисы
  массовых выплат и платёжных сценариев Quantum Labs (Quantum Payouts).</p>
  <p>ООО «Квантум Лабс» · <a href="https://quantumlabs.ru">quantumlabs.ru</a>
  · office@quantumlabs.ru</p>
  <p><a href="{unsub_url}" style="color:#c4470f">Отписаться от рассылки</a>
  · или напишите на <a href="mailto:{unsub}?subject=unsubscribe">{unsub}</a></p>
  <p>Обработка обращений — в соответствии с применимым законодательством РФ
  (в т.ч. 152-ФЗ). Письмо носит информационный характер и не является офертой.</p>
</div>
"""


def ensure_legal_footer(plain: str, html: str) -> tuple[str, str]:
    """Append legal + unsub block if the template doesn't already include it."""
    p = plain or ""
    h = html or ""
    if "{unsub_url}" not in p and "Отписаться" not in p:
        p = p.rstrip() + "\n" + LEGAL_FOOTER_PLAIN
    elif "152-ФЗ" not in p and "ООО" not in p:
        # Has unsub but thin — still append legal identity once
        p = p.rstrip() + "\n" + LEGAL_FOOTER_PLAIN
    if "{unsub_url}" not in h and "Отписаться" not in h:
        h = h.rstrip() + "\n" + LEGAL_FOOTER_HTML
    elif "152-ФЗ" not in h:
        h = h.rstrip() + "\n" + LEGAL_FOOTER_HTML
    return p, h


def _html_from_plain(plain: str) -> str:
    """Simple HTML wrapper for pack bodies (paragraphs)."""
    from html import escape

    parts = []
    for block in (plain or "").strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        parts.append("<p>" + escape(block).replace("\n", "<br>\n") + "</p>")
    body = "\n".join(parts) if parts else "<p></p>"
    return (
        '<!DOCTYPE html><html lang="ru"><body style="font-family:Manrope,Segoe UI,sans-serif;'
        'line-height:1.5;color:#1a1a1a;font-size:15px">'
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
        "short": "Безнал выдача займов и возврат разницы клиентам",
        "audience": "сети и точки ломбардов",
        "attach_presentation_default": True,
        "presentation": "presentations/lombards.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Безналичная выдача займов в сети {company}",
                attach_presentation=True,
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Мы в Quantum Labs (сервис Quantum Payouts) автоматизируем выплаты "
                    "физлицам напрямую со счёта компании — по карте и СБП, с API, "
                    "филиальными лимитами и банковскими статусами.\n\n"
                    "Для ломбардов рассматриваем сценарий: после оформления залогового "
                    "билета клиент может выбрать безналичную выдачу, а головной офис "
                    "получает единую сверку по всем точкам. Наличные при этом остаются "
                    "доступными.\n\n"
                    "Подскажите, рассматриваете ли снижение кассовой нагрузки или "
                    "дополнительный способ выдачи клиентам? Готовы показать схему на 15 минут.\n\n"
                    "С уважением,\nкоманда Quantum Labs\n{website}{phone_line}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="value",
                subject="Re: Безналичная выдача займов в сети {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Добавлю практический смысл: каждая выплата привязывается к номеру "
                    "договора, проходит контроль получателя и лимита точки, а статус банка "
                    "возвращается в учётную систему.\n\n"
                    "Можно пилотировать безнал на нескольких отделениях без замены "
                    "действующего ПО. Также закрываем сценарий возврата клиенту "
                    "положительной разницы после реализации залога.\n\n"
                    "Кому корректнее направить схему — операционному директору, "
                    "казначейству или ИТ?\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
            _step(
                step=3,
                delay_days=7,
                label="close",
                subject="Закрываю вопрос по выплатам для {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Закрою тему, чтобы не перегружать письмами.\n\n"
                    "Если появится задача по безналичной выдаче займов, возврату разницы "
                    "после реализации залога или централизованным выплатам сети — "
                    "пришлю схему интеграции и чек-лист пилота.\n\n"
                    "Можно просто ответить «схема» — отправлю материалы без созвона.\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
        ],
    },
    "mfo": {
        "id": "mfo",
        "title": "МФО",
        "short": "Выдача микрозаймов физлицам через банк-партнёр",
        "audience": "микрофинансовые организации",
        "attach_presentation_default": True,
        "presentation": "presentations/mfo.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выдача займов физлицам без кассовой нагрузки — {company}",
                attach_presentation=True,
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Quantum Payouts (Quantum Labs) — массовые выплаты физлицам: СБП и карты, "
                    "контроль получателя, антидубли, статусы банка и API под ваш контур.\n\n"
                    "Для МФО это сценарий выдачи займа клиенту безналично с прозрачной "
                    "сверкой и снижением операционных рисков на кассе/реестрах.\n\n"
                    "Актуально ли обсудить пилот на 15 минут под ваш процесс выдачи?\n\n"
                    "С уважением,\nQuantum Labs\n{website}{phone_line}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="value",
                subject="Re: Выдача займов физлицам — {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Коротко по ценности: единый канал выплат, лимиты и роли, "
                    "возврат статусов в вашу систему, возможность мультибанковского "
                    "маршрута при необходимости.\n\n"
                    "Можем прислать схему «заявка → проверка → выплата → статус» "
                    "без созвона — ответьте «схема».\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
            _step(
                step=3,
                delay_days=7,
                label="close",
                subject="Закрываю тему выплат для {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Не буду больше беспокоить по этой теме.\n\n"
                    "Если позже понадобится автоматизация выдач или возвратов физлицам — "
                    "напишите, вернёмся с материалами под МФО.\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
        ],
    },
    "trade_in": {
        "id": "trade_in",
        "title": "Trade-in / выкуп",
        "short": "Выплаты продавцам-физлицам при выкупе авто и товаров",
        "audience": "trade-in, автовыкуп, выкуп техники и товаров",
        "attach_presentation_default": True,
        "presentation": "presentations/trade_in.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Выплаты продавцам при выкупе — {company}",
                attach_presentation=True,
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "При выкупе у физлиц (авто, техника, другие товары) часто узкое место — "
                    "быстрая и контролируемая выплата продавцу.\n\n"
                    "Quantum Payouts даёт выплаты на карту/СБП со счёта компании, привязку "
                    "к сделке, лимиты точек и статусы банка в вашу систему.\n\n"
                    "Имеет смысл за 15 минут проверить, как это ляжет на ваш процесс "
                    "оценки и расчёта?\n\n"
                    "С уважением,\nQuantum Labs\n{website}{phone_line}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="value",
                subject="Re: Выплаты продавцам при выкупе — {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "На практике это убирает «ручные» реестры и ускоряет выдачу денег "
                    "продавцу после согласования сделки — с аудитом по каждой выплате.\n\n"
                    "Можем показать и сценарии приёма средств / сплитования, если у вас "
                    "несколько юрлиц или партнёров в цепочке.\n\n"
                    "Кому лучше направить одностраничную схему?\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
            _step(
                step=3,
                delay_days=7,
                label="close",
                subject="Закрываю вопрос по выплатам выкупа — {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Закрываю тему, чтобы не мешать.\n\n"
                    "Если появится задача ускорить выплаты продавцам или централизовать "
                    "расчёты сети — ответьте «схема», пришлю материалы.\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
        ],
    },
    "gig": {
        "id": "gig",
        "title": "Гиг / курьеры / такси",
        "short": "Массовые выплаты самозанятым и исполнителям",
        "audience": "платформы гиг-экономики, курьерские и такси-сервисы",
        "attach_presentation_default": True,
        "presentation": "presentations/gig.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Массовые выплаты исполнителям — {company}",
                attach_presentation=True,
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Для сервисов с большим числом исполнителей (курьеры, водители, "
                    "самозанятые) Quantum Payouts закрывает регулярные выплаты: СБП/карты, "
                    "контроль получателя, статусы и API.\n\n"
                    "Можем усилить контур чеками НПД и прозрачной сверкой фонда выплат.\n\n"
                    "Актуально ли коротко обсудить ваш текущий процесс выплат?\n\n"
                    "С уважением,\nQuantum Labs\n{website}{phone_line}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="value",
                subject="Re: Массовые выплаты исполнителям — {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Типовой эффект пилота: меньше ручных реестров, быстрее деньги "
                    "исполнителю, единый журнал статусов для поддержки и финансов.\n\n"
                    "Готовы прислать схему под ваш стек — ответьте «схема».\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
            _step(
                step=3,
                delay_days=7,
                label="close",
                subject="Закрываю тему выплат для {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Не буду больше писать по этой теме.\n\n"
                    "Если позже понадобится масштабировать выплаты исполнителям — "
                    "мы на связи.\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
        ],
    },
    "scrap": {
        "id": "scrap",
        "title": "Вторсырьё / металлолом",
        "short": "Выплаты физлицам в пунктах приёма",
        "audience": "пункты приёма лома и вторсырья",
        "attach_presentation_default": True,
        "presentation": "presentations/scrap.pdf",
        "steps": [
            _step(
                step=1,
                delay_days=0,
                label="intro",
                subject="Безнал расчёт с физлицами в пунктах приёма — {company}",
                attach_presentation=True,
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "В пунктах приёма лома и вторсырья часто нужна быстрая выплата "
                    "физлицу с контролем и сверкой по точкам.\n\n"
                    "Quantum Payouts — выплаты на карту/СБП со счёта компании, лимиты "
                    "филиалов, статусы банка и API под ваш учёт.\n\n"
                    "Интересно ли посмотреть схему для сети пунктов на 15 минут?\n\n"
                    "С уважением,\nQuantum Labs\n{website}{phone_line}"
                ),
            ),
            _step(
                step=2,
                delay_days=3,
                label="value",
                subject="Re: Безнал расчёт в пунктах приёма — {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Плюс к скорости выплаты — единый контроль кассы/лимитов и меньше "
                    "ошибок при ручных реестрах между точками.\n\n"
                    "Можем также обсудить приём средств и более сложные платёжные "
                    "сценарии под вашу модель.\n\n"
                    "Кому направить краткую схему?\n\n"
                    "С уважением,\nQuantum Labs"
                ),
            ),
            _step(
                step=3,
                delay_days=7,
                label="close",
                subject="Закрываю вопрос по выплатам — {company}",
                plain=(
                    "Здравствуйте, {name}!\n\n"
                    "Закрываю тему. Если появится задача по безналичным выплатам "
                    "сдатчикам — ответьте «схема», пришлю материалы.\n\n"
                    "С уважением,\nQuantum Labs"
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
        "scrap_metal": "scrap",
        "metal": "scrap",
        "taxi": "gig",
        "couriers": "gig",
    }
    pid = aliases.get(pid, pid)
    pack = PACKS.get(pid)
    return deepcopy(pack) if pack else None


def pack_campaign_templates(pack_id: str) -> dict[str, Any] | None:
    """Subject + plain/html for step 1 (campaign letter editor)."""
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
