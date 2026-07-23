"""Knowledge store: multi-file Markdown corpus + topic catalog + search."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

CONTENT_DIR = Path(
    os.getenv("KNOWLEDGE_CONTENT_DIR", str(Path(__file__).resolve().parent / "content"))
).expanduser()
# Prefer live AVA path on prod when present (docx→md build still updates it).
AVA_KNOWLEDGE_MD = Path(
    os.getenv(
        "KNOWLEDGE_QUANTUM_LABS_PATH",
        "/root/ava/config/knowledge/quantum_labs.md",
    )
).expanduser()
MAX_CHARS_DEFAULT = int(os.getenv("KNOWLEDGE_MAX_CHARS", "4500") or "4500")


@dataclass
class Section:
    id: str
    title: str
    level: int
    text: str
    source: str


@dataclass
class Topic:
    id: str
    title: str
    aliases: list[str] = field(default_factory=list)
    match: list[str] = field(default_factory=list)


def _slug(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\wа-яё0-9]+", "-", s, flags=re.I)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "section")[:80]


def _norm(text: str) -> str:
    s = (text or "").lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s


class KnowledgeStore:
    def __init__(self, content_dir: Optional[Path] = None) -> None:
        self.content_dir = Path(content_dir or CONTENT_DIR)
        self.topics: list[Topic] = []
        self.sections: list[Section] = []
        self._full_text: str = ""
        self.reload()

    def reload(self) -> None:
        self.topics = self._load_topics()
        self.sections = []
        chunks: list[str] = []

        md_paths: list[Path] = []
        if AVA_KNOWLEDGE_MD.is_file():
            md_paths.append(AVA_KNOWLEDGE_MD)
        bundled = self.content_dir / "quantum_labs.md"
        if bundled.is_file() and bundled.resolve() not in {p.resolve() for p in md_paths}:
            # Use bundled only if AVA path missing; if both exist prefer AVA, skip duplicate.
            if not md_paths:
                md_paths.append(bundled)

        seen_files: set[str] = set()
        existing_titles: set[str] = set()

        def _ingest(path: Path, *, allow_partial_overlap: bool = False) -> None:
            key = str(path.resolve())
            if key in seen_files:
                return
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("cannot read %s: %s", path, exc)
                return
            parsed = self._parse_sections(text, source=path.name)
            titles = [_norm(s.title) for s in parsed if s.title and s.title != "intro"]
            if titles and existing_titles and not allow_partial_overlap:
                shared = [t for t in titles if t in existing_titles]
                overlap = len(shared) / len(titles)
                # Substantial shared headings (avoid skipping tiny generic overlaps)
                shared_substantial = [t for t in shared if len(t) >= 12]
                if overlap >= 0.4 or len(shared_substantial) >= 2:
                    logger.warning(
                        "skip duplicate knowledge file %s "
                        "(overlap=%.0f%% shared_substantial=%s)",
                        path.name,
                        overlap * 100,
                        len(shared_substantial),
                    )
                    seen_files.add(key)
                    return
            seen_files.add(key)
            chunks.append(text)
            self.sections.extend(parsed)
            existing_titles.update(titles)

        for path in md_paths:
            _ingest(path, allow_partial_overlap=True)

        # Extra topic files under content/topics/*.md (must not duplicate main corpus)
        topics_dir = self.content_dir / "topics"
        if topics_dir.is_dir():
            for path in sorted(topics_dir.glob("*.md")):
                _ingest(path, allow_partial_overlap=False)

        self._full_text = "\n\n".join(chunks).strip()
        logger.info(
            "knowledge loaded topics=%s sections=%s chars=%s sources=%s",
            len(self.topics),
            len(self.sections),
            len(self._full_text),
            len(seen_files),
        )

    def _load_topics(self) -> list[Topic]:
        path = self.content_dir / "index.yaml"
        if not path.is_file():
            return []
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.error("index.yaml parse error: %s", exc)
            return []
        out: list[Topic] = []
        for item in raw.get("topics") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            out.append(
                Topic(
                    id=str(item["id"]).strip(),
                    title=str(item.get("title") or item["id"]).strip(),
                    aliases=[str(a).strip() for a in (item.get("aliases") or []) if str(a).strip()],
                    match=[str(m).strip() for m in (item.get("match") or []) if str(m).strip()],
                )
            )
        return out

    def _parse_sections(self, text: str, *, source: str) -> list[Section]:
        sections: list[Section] = []
        current_lines: list[str] = []
        current_title = "intro"
        current_level = 1
        used_ids: dict[str, int] = {}

        def flush() -> None:
            nonlocal current_lines, current_title, current_level
            body = "\n".join(current_lines).strip()
            if not body:
                return
            base = _slug(current_title)
            n = used_ids.get(base, 0)
            used_ids[base] = n + 1
            sid = base if n == 0 else f"{base}-{n+1}"
            sections.append(
                Section(
                    id=sid,
                    title=current_title,
                    level=current_level,
                    text=body,
                    source=source,
                )
            )
            current_lines = []

        for line in text.splitlines():
            m = re.match(r"^(#{1,3})\s+(.*)$", line)
            if m:
                flush()
                current_level = len(m.group(1))
                current_title = m.group(2).strip() or "section"
                current_lines = [line]
            else:
                current_lines.append(line)
        flush()
        return sections

    def status(self) -> dict[str, Any]:
        return {
            "content_dir": str(self.content_dir),
            "ava_md_present": AVA_KNOWLEDGE_MD.is_file(),
            "ava_md_path": str(AVA_KNOWLEDGE_MD),
            "topics": len(self.topics),
            "sections": len(self.sections),
            "chars": len(self._full_text),
            "ready": bool(self._full_text),
        }

    def list_topics(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t.id,
                "title": t.title,
                "aliases": t.aliases,
            }
            for t in self.topics
        ]

    def resolve_topics(self, topic_or_query: str) -> list[Topic]:
        """Return all catalog topics matching the query (best first)."""
        q = _norm(topic_or_query)
        if not q:
            return []
        scored: list[tuple[int, Topic]] = []
        for t in self.topics:
            score = 0
            if q == _norm(t.id) or q == _norm(t.title):
                score += 100
            for alias in t.aliases:
                an = _norm(alias)
                if not an:
                    continue
                if q == an:
                    score += 80
                elif an in q:
                    score += 40 + len(an)
                elif q in an and len(q) >= 4:
                    score += 15
            if score:
                scored.append((score, t))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored]

    def resolve_topic(self, topic_or_query: str) -> Optional[Topic]:
        hits = self.resolve_topics(topic_or_query)
        return hits[0] if hits else None

    def get_section(self, section_id: str) -> Optional[Section]:
        sid = (section_id or "").strip().lower()
        if not sid:
            return None
        for sec in self.sections:
            if sec.id == sid or _slug(sec.title) == sid:
                return sec
        # substring title match
        for sec in self.sections:
            if sid in _norm(sec.title) or sid in sec.id:
                return sec
        return None

    def sections_for_topic(self, topic: Topic) -> list[Section]:
        hits: list[Section] = []
        seen: set[str] = set()
        for pattern in topic.match:
            pn = _norm(pattern)
            if not pn:
                continue
            for sec in self.sections:
                if sec.id in seen:
                    continue
                if pn in _norm(sec.title) or pn in _norm(sec.text[:200]):
                    hits.append(sec)
                    seen.add(sec.id)
        return hits

    def search(
        self,
        *,
        topic: str = "",
        topic_id: str = "",
        limit: int = 4,
        max_chars: int = MAX_CHARS_DEFAULT,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit or 4), 8))
        max_chars = max(500, min(int(max_chars or MAX_CHARS_DEFAULT), 12000))
        query = (topic or "").strip()
        tid = (topic_id or "").strip()

        if not self._full_text:
            text = (
                "База знаний временно недоступна. "
                "Кратко: Quantum Payouts — массовые безналичные выплаты физлицам (СБП/карты). "
                "Предложи встречу или уточни вопрос."
            )
            return {
                "ok": True,
                "topic": query or tid,
                "topic_id": tid or None,
                "text": text,
                "chars": len(text),
                "matches": [],
                "source": "fallback",
            }

        chosen_list: list[Topic] = []
        if tid:
            exact = next((t for t in self.topics if t.id == tid), None)
            if exact:
                chosen_list = [exact]
        if not chosen_list and query:
            chosen_list = self.resolve_topics(query)[:3]
        chosen = chosen_list[0] if chosen_list else None

        matched_sections: list[Section] = []
        for t in chosen_list:
            matched_sections.extend(self.sections_for_topic(t))

        # Keyword score across all sections (also when topic resolved — to enrich)
        keywords = [w for w in re.split(r"[\s,;.!?/]+", _norm(query)) if len(w) >= 2]
        scored: list[tuple[float, Section]] = []
        for sec in self.sections:
            low = _norm(sec.text)
            heading = _norm(sec.title)
            score = 0.0
            for kw in keywords:
                score += low.count(kw)
                if kw in heading:
                    score += 5
            if query and _norm(query) in low:
                score += 10
            if any(m in heading for m in ("вопрос", "ответ", "faq", "частые")):
                score += 1.5
            for t in chosen_list:
                if any(_norm(m) in heading for m in t.match if m):
                    score += 6
                    break
            if score > 0:
                density = score / max(1.0, len(sec.text) / 800)
                scored.append((score + density, sec))
        scored.sort(key=lambda x: -x[0])

        # Merge: topic matches first, then keyword hits
        ordered: list[Section] = []
        seen: set[str] = set()
        for sec in matched_sections + [s for _, s in scored]:
            if sec.id in seen:
                continue
            seen.add(sec.id)
            ordered.append(sec)
            if len(ordered) >= limit:
                break

        if not ordered:
            # empty query → overview-ish head of corpus
            if not query and not tid:
                text = self._full_text[:max_chars]
                return {
                    "ok": True,
                    "topic": "",
                    "topic_id": None,
                    "text": text,
                    "chars": len(text),
                    "matches": [],
                    "source": "full_prefix",
                }
            # line fallback
            hits = [
                ln
                for ln in self._full_text.splitlines()
                if any(kw in ln.lower().replace("ё", "е") for kw in keywords)
            ]
            blob = "\n".join(hits[:50]).strip() or self._full_text[:max_chars]
            text = blob[:max_chars]
            return {
                "ok": True,
                "topic": query or tid,
                "topic_id": chosen.id if chosen else None,
                "text": text,
                "chars": len(text),
                "matches": [],
                "source": "line_fallback",
            }

        parts = [sec.text for sec in ordered]
        text = "\n\n".join(parts)[:max_chars]
        matches = [
            {
                "id": sec.id,
                "title": sec.title,
                "source": sec.source,
                "chars": len(sec.text),
            }
            for sec in ordered
        ]
        return {
            "ok": True,
            "topic": query or (chosen.title if chosen else tid),
            "topic_id": chosen.id if chosen else None,
            "topic_ids": [t.id for t in chosen_list],
            "text": text,
            "chars": len(text),
            "matches": matches,
            "source": "sections",
        }


store = KnowledgeStore()
