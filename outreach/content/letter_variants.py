"""Letter subject/body variants — anti-fingerprint for first-touch outreach.

7 subjects × 7 bodies = 49 combinations. Same meaning, different wording.
Selection is stable per recipient (hash of email) so resends stay consistent;
across the list it looks random.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

# ---------------------------------------------------------------------------
# Lombards / payouts — step-1 intro (meaning preserved)
# ---------------------------------------------------------------------------

SUBJECTS_LOMBARDS: list[str] = [
    "Выплаты на карту вашим клиентам и по СБП — без посредника",
    "Платёжная инфраструктура для ломбарда: карты, СБП, реестры",
    "Как ускорить выплаты клиентам без смены банка",
    "Прямые договоры с банками + tech для выплат на карту",
    "Выплаты клиентам ломбарда: меньше ручной работы, быстрее зачисление",
    "СБП и карты для вашей сети — сравним схему за 15 минут",
    "Минимальные ставки комиссии по рынку и прозрачный контур выплат",
]

BODIES_LOMBARDS: list[str] = [
    # 0 — baseline (current pack tone)
    (
        "{greeting}\n\n"
        "**Выплаты на карту вашим клиентам и по СБП — без лишней ручной работы**\n\n"
        "Quantum Labs помогает выстроить платёжную инфраструктуру для выплат "
        "на карту вашим клиентам: карты, СБП, реестры, API, статусы операций "
        "и сверка по сети.\n\n"
        "Что получает ваша команда\n\n"
        "- Выплаты на карту вашим клиентам и через СБП\n"
        "- Реестры, API и связка с 1С / вашей учётной системой\n"
        "- Прямые договоры с банками; Quantum Labs — технологический партнёр\n"
        "- Помогаем согласовать для партнёров **минимальные ставки комиссии по рынку**\n\n"
        "**За 15 минут сравним вашу текущую схему с вариантами под ваши объёмы.**\n\n"
        "Покажем, где можно убрать ручные операции и ускорить выплату клиенту.\n\n"
        "{signature}"
    ),
    # 1 — reorder: benefits first
    (
        "{greeting}\n\n"
        "Коротко по делу: как **ускорить выплаты клиентам** и снизить ручной труд.\n\n"
        "Мы подключаем платёжный контур под ломбард / сеть:\n"
        "- выплаты **на карту** и **по СБП**;\n"
        "- реестры, API, статусы и сверка;\n"
        "- связка с **1С** или вашей учётной системой;\n"
        "- **прямые договоры с банками** — Quantum Labs как tech-партнёр, не посредник;\n"
        "- помогаем выйти на **минимальные ставки комиссии по рынку** под ваш объём.\n\n"
        "Предлагаю **15 минут** — сравним вашу схему с вариантами без обязательств.\n\n"
        "{signature}"
    ),
    # 2 — problem → solution
    (
        "{greeting}\n\n"
        "Частый запрос от сетей: выплаты клиентам **тянутся** из‑за ручных операций "
        "и разрозненных каналов.\n\n"
        "Quantum Labs помогает собрать единую инфраструктуру:\n"
        "карты и СБП, реестры, API, статусы операций, сверка по точкам.\n\n"
        "Банк остаётся **вашим** (прямой договор). Мы — технологический партнёр: "
        "подключение, экономика, сопровождение. По ставкам ориентируемся на "
        "**минимум по рынку** для вашего профиля.\n\n"
        "Если удобно — за **четверть часа** разберём, где у вас узкое место.\n\n"
        "{signature}"
    ),
    # 3 — question-led
    (
        "{greeting}\n\n"
        "Подскажите: выплаты клиентам у вас сейчас в основном **на карту**, "
        "**по СБП** или смешанно?\n\n"
        "Мы как tech-партнёр помогаем ломбардам выстроить контур выплат "
        "без посредника: реестры, API, статусы, сверка, связка с учётом. "
        "Договоры с банками — **прямые**, за клиентом.\n\n"
        "По экономике помогаем согласовать **минимальные комиссии по рынку** "
        "под объём сети.\n\n"
        "Готовы коротко сравнить вашу текущую схему — **15 минут**, без давления.\n\n"
        "{signature}"
    ),
    # 4 — concrete outcome focus
    (
        "{greeting}\n\n"
        "**Цель простая:** клиент получает деньги быстрее, команда меньше "
        "делает вручную.\n\n"
        "Quantum Labs — платёжная инфраструктура для выплат на карту и СБП:\n"
        "- массовые операции по реестру;\n"
        "- API и статусы обратно в учёт;\n"
        "- централизация по сети точек;\n"
        "- прямой банковский договор + наш tech и сопровождение;\n"
        "- ставки — стремимся к **минимуму по рынку** для партнёров.\n\n"
        "Предлагаю короткий созвон: сравним «как сейчас» и «как может быть» "
        "под ваши объёмы.\n\n"
        "{signature}"
    ),
    # 5 — soft / peer tone
    (
        "{greeting}\n\n"
        "Пишу по теме выплат клиентам ломбарда — возможно, актуально для вашей сети.\n\n"
        "Мы не продаём «чужой тариф»: клиент работает с банком **напрямую**, "
        "а Quantum Labs закрывает технологию — карты, СБП, реестры, API, сверку. "
        "Параллельно помогаем согласовать **минимальные ставки комиссии по рынку**.\n\n"
        "Если тема в фокусе — удобно за **15 минут** пройтись по вашей схеме "
        "и показать варианты без обязательств.\n\n"
        "{signature}"
    ),
    # 6 — checklist style
    (
        "{greeting}\n\n"
        "Чек-лист, который обычно закрываем для ломбардов:\n\n"
        "☐ выплаты клиентам на карту и по СБП\n"
        "☐ реестры + API + статусы операций\n"
        "☐ связка с 1С / учётной системой\n"
        "☐ прямой договор с банком (мы — tech-партнёр)\n"
        "☐ экономика: минимальные ставки комиссии по рынку под объём\n\n"
        "Quantum Labs как раз про этот контур — без лишнего посредничества.\n\n"
        "**За 15 минут** сравним вашу текущую схему с вариантами под сеть.\n\n"
        "{signature}"
    ),
]

PACK_VARIANTS: dict[str, dict[str, list[str]]] = {
    "lombards": {"subjects": SUBJECTS_LOMBARDS, "bodies": BODIES_LOMBARDS},
    # Aliases / other industry packs can reuse lombards wording until dedicated sets exist
    "mfo": {"subjects": SUBJECTS_LOMBARDS, "bodies": BODIES_LOMBARDS},
}


def variants_enabled(settings: Any = None) -> bool:
    raw = ""
    if settings is not None and hasattr(settings, "get"):
        raw = str(settings.get("LETTER_VARIANTS_ENABLED", "") or "")
    if not raw:
        raw = os.getenv("LETTER_VARIANTS_ENABLED", "true")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _seed_int(*parts: str) -> int:
    blob = "|".join(p.strip().lower() for p in parts if p and str(p).strip())
    if not blob:
        blob = "default"
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def pick_indices(
    *,
    email: str = "",
    company_id: str = "",
    n_subjects: int = 7,
    n_bodies: int = 7,
) -> tuple[int, int]:
    """Stable 'random' indices: different companies → different pairs."""
    n_subjects = max(1, n_subjects)
    n_bodies = max(1, n_bodies)
    seed = _seed_int(email, company_id)
    return seed % n_subjects, (seed // n_subjects) % n_bodies


def resolve_pack_id(settings: Any = None, pack_id: str | None = None) -> str:
    pid = (pack_id or "").strip()
    if not pid and settings is not None and hasattr(settings, "get"):
        pid = str(settings.get("OUTREACH_SEQUENCE_PACK", "") or "").strip()
    if not pid:
        pid = (os.getenv("OUTREACH_SEQUENCE_PACK") or "lombards").strip()
    return pid or "lombards"


def pick_first_touch_variant(
    *,
    email: str = "",
    company_id: str = "",
    pack_id: str | None = None,
    settings: Any = None,
) -> dict[str, Any] | None:
    """Return subject + plain for first-touch, or None if variants disabled / missing."""
    if not variants_enabled(settings):
        return None
    pid = resolve_pack_id(settings, pack_id)
    bundle = PACK_VARIANTS.get(pid) or PACK_VARIANTS.get("lombards")
    if not bundle:
        return None
    subjects = bundle["subjects"]
    bodies = bundle["bodies"]
    si, bi = pick_indices(
        email=email,
        company_id=company_id,
        n_subjects=len(subjects),
        n_bodies=len(bodies),
    )
    return {
        "pack_id": pid,
        "subject_idx": si,
        "body_idx": bi,
        "combo": f"{si}:{bi}",
        "combinations": len(subjects) * len(bodies),
        "subject": subjects[si],
        "plain": bodies[bi],
        "html": "",  # render_cooperation builds HTML from plain
    }


def variant_stats() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pid, bundle in PACK_VARIANTS.items():
        ns, nb = len(bundle["subjects"]), len(bundle["bodies"])
        out[pid] = {"subjects": ns, "bodies": nb, "combinations": ns * nb}
    return out
