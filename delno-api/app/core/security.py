from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

# Known placeholders must never sign or verify tokens.
_JWT_PLACEHOLDERS = frozenset(
    {
        "",
        "change-me",
        "change-me-in-production",
        "change-me-long-random",
        "dev-secret",
        "changeme",
        "changeme123",
    }
)


def jwt_signing_key() -> str:
    secret = (get_settings().jwt_secret or "").strip()
    if secret.lower() in _JWT_PLACEHOLDERS or secret.lower().startswith("change-me"):
        raise RuntimeError(
            "JWT_SECRET is unset or a placeholder; refusing to sign or verify tokens"
        )
    return secret


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(*, subject: str, tenant_id: UUID, role: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, jwt_signing_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, jwt_signing_key(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc
