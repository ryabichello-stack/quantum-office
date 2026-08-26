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
    "Подключение массовых выплат клиентам — карты и СБП",
    "Массовые выплаты: условия по комиссии и удобное подключение",
    "Если уже выплачиваете клиентам — можно согласовать условия выгоднее",
    "Массовые выплаты через банки-партнёры (около 105 банков)",
    "Выплаты клиентам на карту и СБП — подключение услуги",
    "Массовые выплаты: в вашем банке или в банке-партнёре",
    "Quantum Labs: массовые выплаты клиентам под ваши объёмы",
]

BODIES_LOMBARDS: list[str] = [
    # 0 — baseline: что предлагаем прямо
    (
        "{greeting}\n\n"
        "**Предлагаем подключить услугу массовых выплат вашим клиентам**\n\n"
        "Речь о выплатах **на карты** и **по СБП**: разово и массово по реестру.\n\n"
        "Даже если вы уже выплачиваете — часто можно согласовать **более выгодные условия**. "
        "Ориентир по комиссии: примерно **от 1,5% до 0,4%** при больших объёмах "
        "(точная ставка — индивидуально под ваш оборот).\n\n"
        "Как это устроено\n\n"
        "- Работаем примерно со **105 банками** страны\n"
        "- Условия можно согласовать **в вашем банке** или в **другом банке-партнёре**\n"
        "- Подключение: **интеграция в вашу систему** или работа через **наш личный кабинет**\n"
        "- Quantum Labs — технологический партнёр: договор с банком остаётся **вашим**\n\n"
        "**Если интересно — ответьте на письмо или нажмите кнопку ниже.** "
        "Согласуем условия под ваши объёмы, без обязательств.\n\n"
        "{signature}"
    ),
    # 1 — short / direct
    (
        "{greeting}\n\n"
        "Коротко: **подключаем массовые выплаты клиентам** на карту и по СБП.\n\n"
        "Если выплаты уже есть — поможем понять, можно ли сделать **дешевле и удобнее**. "
        "Ориентир ставки: **~1,5% … ~0,4%** при крупных объёмах (не прайс, а вилка для разговора).\n\n"
        "- около **105 банков**-партнёров;\n"
        "- условия в **вашем** или **другом** банке;\n"
        "- интеграция в учёт **или** личный кабинет.\n\n"
        "Интересно сравнить? Напишите «да» или оставьте контакт для звонка — "
        "подберём вариант под объём.\n\n"
        "{signature}"
    ),
    # 2 — already paying angle
    (
        "{greeting}\n\n"
        "Многие сети уже выплачивают клиентам — и всё равно имеет смысл **сверить условия**.\n\n"
        "Quantum Labs предлагает **подключение массовых выплат** (карты + СБП) "
        "и помощь в согласовании более выгодной комиссии. "
        "Ориентир: **от полутора процентов до ~0,4%** на больших объёмах.\n\n"
        "Банковский контур — из пула **~105 банков**: можно остаться в текущем банке "
        "или рассмотреть партнёра. Технически — встройка в вашу систему "
        "либо кабинет Quantum Labs.\n\n"
        "Если тема актуальна — ответьте одним словом или нажмите «Перезвонить».\n\n"
        "{signature}"
    ),
    # 3 — question-led
    (
        "{greeting}\n\n"
        "Подскажите: вы сейчас **выплачиваете клиентам** на карту / по СБП "
        "или пока вручную / через банк без массового контура?\n\n"
        "Мы предлагаем **услугу массовых выплат**: подключение, сопровождение "
        "и согласование условий. Ориентир по комиссии — **1,5% → 0,4%** "
        "в зависимости от объёма (цифры для ориентира, не оферта).\n\n"
        "Работаем с **ведущими банками** (порядка 105). "
        "Можно улучшить условия **в вашем банке** или перейти на контур партнёра. "
        "Учёт — через API/интеграцию или через **личный кабинет**.\n\n"
        "Готовы коротко обсудить? Ответьте на письмо — подстроимся под ваш процесс.\n\n"
        "{signature}"
    ),
    # 4 — outcome focus
    (
        "{greeting}\n\n"
        "**Что предлагаем:** подключить **массовые выплаты** вашим клиентам "
        "на карты и по СБП — с понятной экономикой и удобной технологией.\n\n"
        "Зачем это вам\n\n"
        "- быстрее и проще платить клиентам массово;\n"
        "- часто — **ниже комиссия** (ориентир **1,5% … 0,4%** при больших объёмах);\n"
        "- выбор банка из **~105** партнёров;\n"
        "- интеграция в вашу систему **или** работа в нашем ЛК.\n\n"
        "Договор с банком — **прямой**, за вашей компанией. "
        "Мы — tech-партнёр по подключению и сопровождению.\n\n"
        "Если интересно — дайте знать, согласуем условия под ваш оборот.\n\n"
        "{signature}"
    ),
    # 5 — soft peer
    (
        "{greeting}\n\n"
        "Пишу по делу: **массовые выплаты клиентам** (карты и СБП).\n\n"
        "Не продаём «чужой тариф внагрузку». Помогаем **подключить услугу** "
        "и согласовать условия — в вашем банке или в банке-партнёре "
        "из пула около **105 банков**. "
        "По ставке обычно смотрим вилку **примерно от 1,5% до 0,4%** "
        "в зависимости от объёма.\n\n"
        "Технически можно встроиться в вашу учётную систему "
        "или вести выплаты через наш личный кабинет.\n\n"
        "Если тема в фокусе — ответьте или нажмите кнопку ниже, "
        "обсудим без давления.\n\n"
        "{signature}"
    ),
    # 6 — checklist
    (
        "{greeting}\n\n"
        "Чек-лист предложения Quantum Labs для ломбарда:\n\n"
        "☐ **массовые выплаты** клиентам на карту и по СБП\n"
        "☐ более выгодные условия, если выплаты уже есть "
        "(ориентир комиссии **~1,5% … ~0,4%** при больших объёмах)\n"
        "☐ банк: ваш текущий **или** партнёр из **~105 банков**\n"
        "☐ подключение: интеграция в систему **или** личный кабинет\n"
        "☐ мы — технологический партнёр, не посредник-«перекуп»\n\n"
        "Если хотя бы два пункта откликаются — напишите, "
        "согласуем условия под ваши объёмы.\n\n"
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
