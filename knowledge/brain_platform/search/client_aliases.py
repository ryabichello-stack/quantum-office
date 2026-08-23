"""Client name aliases + fuzzy match for search query expansion.

Users write «НордСервис-СПб», «Норд-Сервис СПб», «нордсервис», with typos, etc.
This module maps those spellings to a canonical name + INN so FTS/hybrid recall works.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class ClientAlias:
    canonical: str
    inn: str
    aliases: tuple[str, ...]
    # Compact keys used for matching after normalize_compact()
    keys: tuple[str, ...]


# Keep this list curated; promote new merchants here when onboarding.
CLIENTS: tuple[ClientAlias, ...] = (
    ClientAlias(
        canonical='ООО «НордСервис-СПб»',
        inn="7816718222",
        aliases=(
            "НордСервис-СПб",
            "НордСервис СПб",
            "Норд-Сервис-СПб",
            "Норд-Сервис СПб",
            "Норд Сервис СПб",
            "Норд Сервис-СПб",
            "НордСервисСПб",
            "Нордсервис",
            "Норд-сервис",
            "Норд сервис",
            "NordService",
            "Nord Service",
            "NordService SPb",
            "Nord Service Spb",
            "NordServis",
            "Nordservice-SPb",
        ),
        keys=(
            "нордсервисспб",
            "нордсервис",
            "nordservice",
            "nordservis",
            "nordserviceспб",
            "nordservisspb",
            "nordservice spb".replace(" ", ""),
        ),
    ),
    ClientAlias(
        canonical='ООО «Новые технологии демонтажа» (НТД)',
        inn="7814754000",
        aliases=(
            "НТД",
            "Новые технологии демонтажа",
            "Новые Технологии Демонтажа",
            "ООО НТД",
            "NTD",
        ),
        keys=("нтд", "новыетехнологиидемонтажа", "ntd"),
    ),
    ClientAlias(
        canonical='ООО «Демолишн»',
        inn="7804558359",
        aliases=(
            "Демолишн",
            "Demolishn",
            "Demolition",
            "Демолишен",
            "Демолишн СПб",
        ),
        keys=("демолишн", "demolishn", "demolition", "демолишен"),
    ),
)


def normalize_compact(text: str) -> str:
    """Lowercase, ё→е, strip punctuation/spaces/hyphens → alnum only."""
    s = (text or "").lower().replace("ё", "е")
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[^a-z0-9а-я]+", "", s, flags=re.I)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def match_clients(query: str, *, min_key_len: int = 6) -> list[ClientAlias]:
    """Return clients mentioned in the query (exact compact / fuzzy)."""
    compact = normalize_compact(query)
    if len(compact) < 3:
        return []

    found: list[ClientAlias] = []
    seen: set[str] = set()

    for client in CLIENTS:
        hit = False
        # INN exact
        if client.inn and client.inn in (query or ""):
            hit = True
        # Compact substring either way
        if not hit:
            for key in client.keys:
                if len(key) < 3:
                    continue
                if key in compact or (len(compact) >= min_key_len and compact in key):
                    hit = True
                    break
        # Fuzzy against keys (typos: нордсервес, nordservis)
        if not hit:
            # Prefer longest contiguous alpha token(s) around nord/demo/ntd
            candidates = {compact}
            # Also try sliding windows of key lengths
            for key in client.keys:
                if len(key) < min_key_len:
                    continue
                if abs(len(compact) - len(key)) > 4 and len(compact) > len(key) + 6:
                    # Compare best window inside compact
                    best = 0.0
                    for i in range(0, max(1, len(compact) - len(key) + 1)):
                        window = compact[i : i + len(key)]
                        best = max(best, _similarity(window, key))
                    if best >= 0.86:
                        hit = True
                        break
                else:
                    if _similarity(compact, key) >= 0.86:
                        hit = True
                        break
                    # Prefix-ish for short queries like «нордсервес»
                    if len(compact) >= min_key_len and (
                        _similarity(compact, key[: len(compact)]) >= 0.88
                        or _similarity(compact[: len(key)], key) >= 0.88
                    ):
                        hit = True
                        break
        if hit and client.inn not in seen:
            seen.add(client.inn)
            found.append(client)
    return found


def expand_client_aliases(query: str) -> list[str]:
    """Query variants to inject into hybrid search."""
    q = re.sub(r"\s+", " ", (query or "").strip())
    if not q:
        return []
    out: list[str] = [q]
    for client in match_clients(q):
        out.append(client.canonical)
        out.append(client.inn)
        out.append(f"{client.canonical} {client.inn}")
        # Prefer spaced + hyphen forms that match indexed «НордСервис-СПб»
        for alias in client.aliases:
            out.append(alias)
            out.append(f"{alias} {client.inn}")
        # Compact canonical without punctuation for FTS OR tokens
        out.append(normalize_compact(client.canonical))
    # Dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        v = v.strip()
        if len(v) < 2:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(v)
    return uniq[:24]
