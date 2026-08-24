"""Letter subject/body variants — anti-fingerprint for first-touch outreach.

7 subjects × 7 bodies = 49 combinations. Same meaning, different wording.
Selection is stable per recipient (hash of email) so resends stay consistent;
across the list it looks random.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
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
    "lombards": {"subjects": list(SUBJECTS_LOMBARDS), "bodies": list(BODIES_LOMBARDS)},
    "mfo": {"subjects": list(SUBJECTS_LOMBARDS), "bodies": list(BODIES_LOMBARDS)},
}

TARGET_N = 7


def _variants_dir() -> Path:
    from core.paths import DATA_DIR

    return Path(DATA_DIR) / "letter_variants"


def _pack_path(pack_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", (pack_id or "lombards").strip()) or "lombards"
    return _variants_dir() / f"{safe}.json"


def _builtin_bundle(pack_id: str) -> dict[str, list[str]]:
    base = PACK_VARIANTS.get(pack_id) or PACK_VARIANTS["lombards"]
    return {
        "subjects": list(base["subjects"]),
        "bodies": list(base["bodies"]),
    }


def load_bundle(pack_id: str) -> dict[str, Any]:
    """Load editable variants (DATA_DIR override) or builtin defaults."""
    pid = (pack_id or "lombards").strip() or "lombards"
    path = _pack_path(pid)
    source = "builtin"
    subjects: list[str] = []
    bodies: list[str] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            subjects = [str(s).strip() for s in (raw.get("subjects") or []) if str(s).strip()]
            bodies = [str(b).strip() for b in (raw.get("bodies") or []) if str(b).strip()]
            source = "data_dir"
        except (OSError, json.JSONDecodeError):
            subjects, bodies = [], []
    if len(subjects) < 1 or len(bodies) < 1:
        builtin = _builtin_bundle(pid)
        subjects = builtin["subjects"]
        bodies = builtin["bodies"]
        source = "builtin"
    return {
        "pack_id": pid,
        "subjects": subjects[:12],
        "bodies": bodies[:12],
        "source": source,
        "path": str(path),
        "combinations": len(subjects) * len(bodies),
    }


def save_bundle(pack_id: str, *, subjects: list[str], bodies: list[str]) -> dict[str, Any]:
    """Persist variants to DATA_DIR (survives deploy of code defaults)."""
    pid = (pack_id or "lombards").strip() or "lombards"
    subs = [str(s).strip() for s in subjects if str(s).strip()][:12]
    bods = [str(b).strip() for b in bodies if str(b).strip()][:12]
    if len(subs) < 1 or len(bods) < 1:
        raise ValueError("need_at_least_one_subject_and_body")
    for i, b in enumerate(bods):
        if "{greeting}" not in b:
            bods[i] = "{greeting}\n\n" + b
        if "{signature}" not in b:
            bods[i] = bods[i].rstrip() + "\n\n{signature}"
    path = _pack_path(pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pack_id": pid, "subjects": subs, "bodies": bods}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_bundle(pid)


def reset_bundle(pack_id: str) -> dict[str, Any]:
    path = _pack_path(pack_id)
    if path.is_file():
        path.unlink()
    return load_bundle(pack_id)


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
    bundle = load_bundle(pid)
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
        "html": "",
        "source": bundle.get("source"),
    }


def variant_stats() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pid in sorted(set(list(PACK_VARIANTS.keys()) + ["lombards"])):
        b = load_bundle(pid)
        out[pid] = {
            "subjects": len(b["subjects"]),
            "bodies": len(b["bodies"]),
            "combinations": b["combinations"],
            "source": b["source"],
        }
    return out
