"""Letter subject/body variants — anti-fingerprint for first-touch outreach.

7 subjects × 7 bodies = 49 combinations. Same meaning, different wording.
Selection is stable per recipient (hash of email) so resends stay consistent;
across the list it looks random.

Lombards positioning (cold): optional card/SBP beside cash — not «mass payouts»
and not «replace cash». Top-5 bank partners. Soft CTA: узнать условия.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lombards — step-1 intro (optionality framing)
# ---------------------------------------------------------------------------

SUBJECTS_LOMBARDS: list[str] = [
    "Выдавайте займы клиентам сразу на карту или по СБП",
    "Карта и СБП рядом с наличными — без смены вашей схемы",
    "Клиент сам выбирает: наличные, карта или СБП",
    "Узнать условия выдачи на карту / СБП под ваш объём",
    "Ещё один способ выдачи: на карту или по СБП практически сразу",
    "Подключение выдачи на карту и СБП — на нашей стороне",
    "Официальные партнёры банков из топ-5: условия под ваш ломбард",
]

_CORE_HOWTO = (
    "Как это устроено\n\n"
    "- Клиент выбирает: наличные, карта или СБП\n"
    "- При безналичном варианте деньги поступают практически сразу\n"
    "- Работать можно через личный кабинет, реестр или вашу учётную систему\n"
    "- Статус выплаты возвращается в систему для контроля и сверки\n"
    "- Деньги идут напрямую через банк, не проходя через Quantum Payouts\n\n"
)

BODIES_LOMBARDS: list[str] = [
    # 0 — baseline (canonical)
    (
        "{greeting}\n\n"
        "**Выдавайте займы клиентам сразу на карту или по СБП**\n\n"
        "Добавьте к привычной выдаче наличными ещё один удобный способ "
        "получения денег — на карту или по СБП практически сразу после "
        "оформления сделки.\n\n"
        "Менять существующую схему не нужно: клиент сам выбирает, "
        "как ему удобнее получить деньги.\n\n"
        f"{_CORE_HOWTO}"
        "Мы — официальные партнёры банков из топ-5 РФ и помогаем "
        "с подключением и согласованием условий.\n\n"
        "Комиссия зависит от банка и объёма выплат — "
        "ориентировочно от 1,5% до 0,4%.\n\n"
        "Необязательно что-либо менять в текущей работе — можно сначала "
        "просто посмотреть, какие условия доступны именно для вашего ломбарда.\n\n"
        "{signature}"
    ),
    # 1 — short / direct
    (
        "{greeting}\n\n"
        "Коротко: можно **добавить выдачу на карту или по СБП** рядом "
        "с привычными наличными — без замены текущей схемы.\n\n"
        "Клиент сам выбирает способ. При безнале деньги приходят "
        "практически сразу. Подключение и согласование условий — "
        "на нашей стороне.\n\n"
        "Мы — официальные партнёры банков из топ-5 РФ. "
        "Ориентир комиссии: **от 1,5% до 0,4%** в зависимости от объёма.\n\n"
        "Хотите узнать условия под ваш объём? Ответьте на письмо "
        "или нажмите кнопку ниже — точный объём не нужен.\n\n"
        "{signature}"
    ),
    # 2 — softener first
    (
        "{greeting}\n\n"
        "**Менять существующую схему не нужно.**\n\n"
        "Речь не о замене наличных, а о ещё одном способе выдачи: "
        "на карту или по СБП практически сразу после сделки.\n\n"
        f"{_CORE_HOWTO}"
        "Официальные партнёры банков из топ-5 РФ. Комиссия — ориентировочно "
        "от 1,5% до 0,4%.\n\n"
        "Можно сначала просто посмотреть условия под ваш ломбард — "
        "без обязательств что-то менять.\n\n"
        "{signature}"
    ),
    # 3 — question-led
    (
        "{greeting}\n\n"
        "Подскажите: клиенты сейчас получают деньги **только наличными** "
        "или уже есть выдача на карту / по СБП?\n\n"
        "Мы помогаем добавить безналичный способ рядом с привычным: "
        "клиент выбирает сам, деньги при безнале приходят практически сразу, "
        "подключение — на нашей стороне.\n\n"
        "Партнёры банков из топ-5 РФ. Ориентир комиссии: **1,5% → 0,4%** "
        "в зависимости от объёма.\n\n"
        "Если интересно — достаточно примерного объёма или короткого "
        "«да, давайте посмотрим условия».\n\n"
        "{signature}"
    ),
    # 4 — how it works focus
    (
        "{greeting}\n\n"
        "**Как клиент получает деньги на карту или по СБП**\n\n"
        "Сделка оформлена → клиент выбирает наличные, карту или СБП → "
        "при безнале деньги уходят практически сразу → статус возвращается "
        "в вашу систему.\n\n"
        "Работать можно через личный кабинет, реестр или учёт. "
        "Деньги идут напрямую через банк, не через Quantum Payouts.\n\n"
        "Мы — официальные партнёры банков из топ-5 РФ и берём на себя "
        "подключение и согласование условий. Комиссия ориентировочно "
        "от 1,5% до 0,4%.\n\n"
        "Можно сначала узнать условия под ваш объём — без смены текущей работы.\n\n"
        "{signature}"
    ),
    # 5 — soft peer
    (
        "{greeting}\n\n"
        "Пишу по делу: **выдача займов на карту и по СБП** как дополнительный "
        "способ рядом с наличными.\n\n"
        "Мы не предлагаем отказаться от кассы и не спорим с вашей моделью. "
        "Задача проще — понять, какие условия доступны именно под ваш объём.\n\n"
        "Подключение на нашей стороне. Партнёры банков из топ-5. "
        "Ориентир ставки: примерно **от 1,5% до 0,4%**.\n\n"
        "Если тема в фокусе — ответьте или нажмите «Узнать условия».\n\n"
        "{signature}"
    ),
    # 6 — checklist
    (
        "{greeting}\n\n"
        "Чек-лист предложения Quantum Labs для ломбарда:\n\n"
        "☐ выдача на карту / СБП **рядом** с наличными, без замены схемы\n"
        "☐ клиент сам выбирает способ получения\n"
        "☐ при безнале деньги — практически сразу\n"
        "☐ подключение и согласование условий — на нашей стороне\n"
        "☐ официальные партнёры банков из топ-5 РФ\n"
        "☐ комиссия ориентировочно **от 1,5% до 0,4%**\n\n"
        "Если хотя бы два пункта откликаются — можно сначала просто "
        "узнать условия под ваш объём.\n\n"
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
    return load_bundle(pid)


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
