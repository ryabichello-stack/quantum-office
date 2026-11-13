"""Autonomous person lookup helpers: name variants, transliteration, multi-source."""

from __future__ import annotations

import re
from typing import Iterable

# Simplified Russian → Latin (passport-ish / email style)
_CYR_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_DIMINUTIVES: dict[str, list[str]] = {
    "юля": ["юлия", "юлию", "yuliya", "yulia", "julia", "julie"],
    "юлия": ["юля", "yuliya", "yulia", "julia"],
    "саша": ["александр", "александра", "alexander", "alexandra", "alex"],
    "саня": ["александр", "александра"],
    "маша": ["мария", "maria", "marie"],
    "мария": ["маша", "maria"],
    "катя": ["екатерина", "ekaterina", "catherine"],
    "екатерина": ["катя", "ekaterina"],
    "настя": ["анастасия", "anastasia"],
    "даша": ["дарья", "daria", "darya"],
    "оля": ["ольга", "olga"],
    "ольга": ["оля", "olga"],
    "леша": ["алексей", "alexey", "aleksey"],
    "лёша": ["алексей", "alexey"],
    "дима": ["дмитрий", "dmitry", "dmitriy"],
    "дмитрий": ["дима", "dmitry"],
    "коля": ["николай", "nikolay", "nicholas"],
    "ваня": ["иван", "ivan"],
    "иван": ["ваня", "ivan"],
    "петя": ["петр", "пётр", "peter", "petr"],
    "сережа": ["сергей", "sergey"],
    "серёжа": ["сергей", "sergey"],
    "таня": ["татьяна", "tatyana", "tatiana"],
    "ира": ["ирина", "irina"],
    "ирина": ["ира", "irina"],
    "надя": ["надежда", "nadezhda"],
    "витя": ["виктор", "victor", "viktor"],
    "виктор": ["витя", "victor", "viktor"],
    "денис": ["denis", "dennis"],
    "миша": ["михаил", "mikhail", "michael"],
    "михаил": ["миша", "mikhail"],
}


def transliterate_ru(text: str) -> str:
    out: list[str] = []
    for ch in (text or "").lower():
        if ch in _CYR_TO_LAT:
            out.append(_CYR_TO_LAT[ch])
        else:
            out.append(ch)
    return "".join(out)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def person_query_variants(query: str) -> list[str]:
    """Expand a person query into search variants (no user prompting)."""
    q = _normalize_spaces(query)
    if not q:
        return []

    variants: list[str] = [q]
    lower = q.lower()
    variants.append(lower)
    variants.append(transliterate_ru(lower))

    # ё → е
    if "ё" in lower:
        variants.append(lower.replace("ё", "е"))
        variants.append(transliterate_ru(lower.replace("ё", "е")))

    tokens = [t for t in re.split(r"[\s,;]+", lower) if t]
    # last name only / first only
    variants.extend(tokens)
    variants.extend(transliterate_ru(t) for t in tokens)

    # diminutives on first token
    if tokens:
        first = tokens[0]
        for alt in _DIMINUTIVES.get(first, []):
            rest = tokens[1:]
            variants.append(" ".join([alt, *rest]).strip())
            variants.append(alt)
            variants.append(transliterate_ru(alt))
            if rest:
                variants.append(transliterate_ru(" ".join([alt, *rest])))

        # Юля Парцуф → Yuliya Partsuf
        if len(tokens) >= 2:
            first_alts = [first, *_DIMINUTIVES.get(first, []), transliterate_ru(first)]
            last = tokens[-1]
            last_alts = [last, transliterate_ru(last)]
            for f in first_alts:
                for l in last_alts:
                    variants.append(f"{f} {l}")
                    variants.append(l)  # surname

    # email-local style: ypartsuf from yuliya partsuf
    latin_tokens = [transliterate_ru(t) for t in tokens if transliterate_ru(t).isalpha()]
    if len(latin_tokens) >= 2:
        variants.append(latin_tokens[0][0] + latin_tokens[-1])  # ypartsuf
        variants.append(latin_tokens[-1] + latin_tokens[0][0])
        variants.append("".join(latin_tokens))

    # unique preserve order, drop very short
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = _normalize_spaces(v).strip(".,;:\"'")
        if len(v) < 2:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out[:40]


def extract_emails(text: str) -> list[str]:
    found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    return sorted({e.lower() for e in found})


def extract_phones(text: str) -> list[str]:
    found = re.findall(
        r"(?:\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
        text or "",
    )
    return sorted({re.sub(r"\s+", " ", p.strip()) for p in found})


def normalize_email(raw: str) -> str | None:
    raw = (raw or "").strip().lower()
    if not raw:
        return None
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw)
    return m.group(0).lower() if m else None


def score_contact_match(query: str, contact: dict) -> int:
    """Higher is better."""
    q = (query or "").lower()
    variants = {v.lower() for v in person_query_variants(q)}
    name = str(contact.get("display_name") or "").lower()
    emails = " ".join(contact.get("emails") or []).lower()
    company = str(contact.get("company_name") or "").lower()
    phones = " ".join(contact.get("phones") or [])
    blob = f"{name} {emails} {company}"
    score = 0
    for v in variants:
        if v and v in blob:
            score += 10 if len(v) > 3 else 4
        if v and v in name:
            score += 8
    for em in contact.get("emails") or []:
        local = em.split("@")[0].lower()
        for v in variants:
            if v and (v in local or local in v):
                score += 12
    # Prefer human FIO / phone-rich cards
    if re.search(r"[а-яё]", name):
        score += 40
    if " " in name.strip():
        score += 15
    if phones:
        score += 10
    if "@" in name or "<" in name or '"' in name:
        score -= 80
    return score
