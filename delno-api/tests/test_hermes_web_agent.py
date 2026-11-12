"""Hermes cabinet: web research preference + search HTML parse."""

from __future__ import annotations

from app.operator.agent import _wants_web_research
from app.services.web_browser import _parse_ddg_html


def test_wants_web_research_markers():
    assert _wants_web_research("Сходи в интернет и найди про выплаты физлицам")
    assert _wants_web_research("Погугли актуальные правила")
    assert not _wants_web_research("Покажи статус SIP")
    assert not _wants_web_research("Что у нас в базе знаний про компанию?")


def test_parse_ddg_html_result_a():
    html = """
    <div class="result results_links">
      <a rel="nofollow" class="result__a" href="https://example.com/a">Title A</a>
    </div>
    <div class="result results_links">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb">Title B</a>
    </div>
    """
    items = _parse_ddg_html(html, limit=5)
    assert len(items) == 2
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["title"] == "Title A"
    assert items[1]["url"] == "https://example.com/b"
