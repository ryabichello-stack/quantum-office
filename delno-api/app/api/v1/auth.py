from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, get_tenant_context_auth
from app.core.db import get_db
from app.core.security import create_access_token, verify_password
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, TokenResponse, UserResponse
from app.services.onboarding import register_tenant
from app.services.events import emit_event
from app.services.usage import record_usage

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        emit_event(
            db,
            tenant_id=user.tenant_id if user else None,
            event_type="auth.failed",
            category="operational",
            source="auth.login",
            payload={
                "email": body.email.lower(),
                "reason": "invalid_credentials",
            },
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).one()
    token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, role=user.role)
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="auth.login",
        category="operational",
        source="auth.login",
        payload={"user_id": str(user.id), "role": user.role},
    )
    record_usage(db, tenant_id=tenant.id, metric="auth.login", quantity=1)
    db.commit()
    return TokenResponse(access_token=token)


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """P2.1 — self-service: company + owner → tenant + JWT."""
    try:
        tenant, user, _meta = register_tenant(
            db,
            email=body.email,
            password=body.password,
            company_name=body.company_name,
            slug=body.slug,
            inn=body.inn,
        )
    except ValueError as exc:
        if str(exc) == "email_taken":
            raise HTTPException(status_code=409, detail="Email already registered") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = create_access_token(subject=str(user.id), tenant_id=user.tenant_id, role=user.role)
    record_usage(db, tenant_id=tenant.id, metric="auth.register", quantity=1)
    db.commit()
    return RegisterResponse(
        access_token=token,
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        public_key=tenant.public_key,
        user_id=str(user.id),
    )


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
