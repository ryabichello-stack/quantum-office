from unittest.mock import MagicMock, patch

from app.api.v1.public import get_published_cms_page


def test_get_published_cms_faq_page():
    mock_page = MagicMock()
    mock_page.slug = "faq"
    mock_page.title = "FAQ"
    mock_page.locale = "ru"
    mock_page.status = "published"
    mock_page.blocks = {"sections": [{"q": "Что такое DELNO?", "a": "ИИ-сотрудник."}]}
    mock_page.published_at = None

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.one_or_none.return_value = mock_page

    result = get_published_cms_page("faq", db=mock_db, locale="ru")
    assert result["slug"] == "faq"
    assert result["blocks"]["sections"][0]["q"] == "Что такое DELNO?"
