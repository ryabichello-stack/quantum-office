"""Knowledge store: skip topic files that duplicate the main corpus."""

from __future__ import annotations

import os
from pathlib import Path

import store as store_mod


def test_skips_duplicate_topic_file(tmp_path: Path, monkeypatch):
    content = tmp_path / "content"
    topics = content / "topics"
    topics.mkdir(parents=True)
    (content / "index.yaml").write_text("topics: []\n", encoding="utf-8")
    (content / "quantum_labs.md").write_text(
        "# Main\n\n"
        "## 1. Быстрый профиль продукта\n\nalpha\n\n"
        "## 1. Резюме для руководителя\n\nlombard summary\n\n"
        "## Рынок ломбардов и коммерческая привлекательность\n\nmarket\n",
        encoding="utf-8",
    )
    (topics / "pawnshops.md").write_text(
        "# Dup\n\n"
        "## 1. Быстрый профиль продукта\n\nalpha copy\n\n"
        "## 1. Резюме для руководителя\n\nlombard\n\n"
        "## Рынок ломбардов и коммерческая привлекательность\n\nmarket2\n",
        encoding="utf-8",
    )
    (topics / "extra.md").write_text(
        "# Extra\n\n## Brand new topic XYZ uniquely\n\nhello\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("KNOWLEDGE_CONTENT_DIR", str(content))
    monkeypatch.setenv("KNOWLEDGE_QUANTUM_LABS_PATH", str(tmp_path / "missing.md"))
    # Re-bind module-level paths after env change
    store_mod.CONTENT_DIR = content
    store_mod.AVA_KNOWLEDGE_MD = tmp_path / "missing.md"

    ks = store_mod.KnowledgeStore(content_dir=content)
    sources = {s.source for s in ks.sections}
    titles = [s.title for s in ks.sections]
    assert "quantum_labs.md" in sources
    assert "extra.md" in sources
    assert "pawnshops.md" not in sources
    assert any("Brand new topic XYZ" in t for t in titles)
    assert titles.count("1. Резюме для руководителя") == 1
