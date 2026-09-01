from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_tenant_context_auth
from app.core.db import get_db
from app.core.security import create_access_token, verify_password
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.events import emit_event
from app.services.usage import record_usage

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
    token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, role=user.role)
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="auth.login",
        category="operational",
        payload={"user_id": str(user.id), "role": user.role},
    )
    record_usage(db, tenant_id=tenant.id, metric="auth.login", quantity=1)
    db.commit()
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserResponse:
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        tenant_id=str(user.tenant_id),
        tenant_slug=tenant.slug,
    )
