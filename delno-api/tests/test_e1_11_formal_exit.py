"""E1.11 formal exit — admin CMS draft → publish → public read (FAQ chain)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.admin_cms import CmsPageCreate, create_cms_page, publish_cms_page
from app.api.v1.public import get_published_cms_page


def test_e1_11_draft_page_not_visible_publicly():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    with pytest.raises(HTTPException) as exc:
        get_published_cms_page("new-faq", db=db, locale="ru")

    assert exc.value.status_code == 404


def test_e1_11_create_publish_public_cms_chain():
    page_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    admin = MagicMock()
    admin.id = admin_id

    page = MagicMock()
    page.id = page_id
    page.slug = "exit-faq"
    page.title = "Exit FAQ"
    page.locale = "ru"
    page.blocks = {"sections": [{"q": "Test Q?", "a": "Test A."}]}
    page.status = "draft"
    page.published_at = None
    page.tenant_id = None

    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.side_effect = [
        None,  # create: slug not exists
        page,  # publish: page found
    ]
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()

    body = CmsPageCreate(slug="exit-faq", title="Exit FAQ", blocks=page.blocks)

    with patch("app.api.v1.admin_cms.emit_event") as mock_emit:
        created = create_cms_page(body, db=db, admin=admin)

    assert created.slug == "exit-faq"
    assert created.status == "draft"
    assert mock_emit.call_args.kwargs["event_type"] == "cms.page.created"
    assert mock_emit.call_args.kwargs["source"] == "admin.cms"

    page.status = "published"
    page.published_at = datetime.now(timezone.utc)

    with patch("app.api.v1.admin_cms.emit_event") as mock_publish_emit:
        published = publish_cms_page(page_id, db=db, admin=admin)

    assert published.status == "published"
    mock_publish_emit.assert_called_once()
    assert mock_publish_emit.call_args.kwargs["event_type"] == "cms.page.published"

    db.query.return_value.filter.return_value.one_or_none.side_effect = None
    db.query.return_value.filter.return_value.one_or_none.return_value = page
    public = get_published_cms_page("exit-faq", db=db, locale="ru")
    assert public["slug"] == "exit-faq"
    assert public["blocks"]["sections"][0]["a"] == "Test A."
