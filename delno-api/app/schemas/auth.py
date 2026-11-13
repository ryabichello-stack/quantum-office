from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    company_name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")
    inn: str | None = Field(default=None, max_length=14)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    tenant_slug: str
    tenant_name: str
    public_key: str
    user_id: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str
    tenant_slug: str
