from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_platform_admin
from app.core.db import get_db
from app.models.cms import CmsPage, CmsRevision
from app.models.user import User
from app.services.events import emit_event

router = APIRouter(prefix="/admin/cms", tags=["admin-cms"])


class CmsPageCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    locale: str = Field(default="ru", max_length=8)
    blocks: dict = Field(default_factory=dict)


class CmsPageUpdate(BaseModel):
    title: str | None = None
    blocks: dict | None = None


class CmsPageResponse(BaseModel):
    id: str
    slug: str
    title: str
    locale: str
    status: str
    blocks: dict

    @classmethod
    def from_page(cls, page: CmsPage) -> "CmsPageResponse":
        return cls(
            id=str(page.id),
            slug=page.slug,
            title=page.title,
            locale=page.locale,
            status=page.status,
            blocks=page.blocks or {},
        )


@router.get("/pages", response_model=list[CmsPageResponse])
def list_cms_pages(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> list[CmsPageResponse]:
    pages = (
        db.query(CmsPage)
        .filter(CmsPage.tenant_id.is_(None))
        .order_by(CmsPage.slug)
        .all()
    )
    return [CmsPageResponse.from_page(p) for p in pages]


@router.post("/pages", response_model=CmsPageResponse, status_code=201)
def create_cms_page(
    body: CmsPageCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> CmsPageResponse:
    exists = (
        db.query(CmsPage)
        .filter(CmsPage.slug == body.slug, CmsPage.locale == body.locale, CmsPage.tenant_id.is_(None))
        .one_or_none()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Page already exists")

    page = CmsPage(
        slug=body.slug,
        title=body.title,
        locale=body.locale,
        blocks=body.blocks,
        status="draft",
    )
    db.add(page)
    db.flush()
    db.add(CmsRevision(page_id=page.id, blocks=body.blocks, note="create", created_by=admin.id))
    emit_event(
        db,
        event_type="cms.page.created",
        category="domain",
        source="admin.cms",
        payload={"slug": page.slug},
    )
    db.commit()
    db.refresh(page)
    return CmsPageResponse.from_page(page)


@router.patch("/pages/{page_id}", response_model=CmsPageResponse)
def update_cms_page(
    page_id: UUID,
    body: CmsPageUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> CmsPageResponse:
    page = db.query(CmsPage).filter(CmsPage.id == page_id, CmsPage.tenant_id.is_(None)).one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if body.title is not None:
        page.title = body.title
    if body.blocks is not None:
        page.blocks = body.blocks
        db.add(CmsRevision(page_id=page.id, blocks=body.blocks, note="update", created_by=admin.id))
    db.commit()
    db.refresh(page)
    return CmsPageResponse.from_page(page)


@router.post("/pages/{page_id}/publish", response_model=CmsPageResponse)
def publish_cms_page(
    page_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> CmsPageResponse:
    page = db.query(CmsPage).filter(CmsPage.id == page_id, CmsPage.tenant_id.is_(None)).one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    page.status = "published"
    page.published_at = datetime.now(timezone.utc)
    emit_event(
        db,
        event_type="cms.page.published",
        category="domain",
        source="admin.cms",
        payload={"slug": page.slug},
    )
    db.commit()
    db.refresh(page)
    return CmsPageResponse.from_page(page)
