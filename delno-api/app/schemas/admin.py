from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
    owner_email: str | None = None
    owner_password: str | None = Field(default=None, min_length=6, max_length=128)
    legal_inn: str | None = Field(default=None, max_length=14)


class TenantResponse(BaseModel):
    id: str
    slug: str
    name: str
    is_active: bool

    @classmethod
    def from_orm_tenant(cls, tenant) -> "TenantResponse":
        return cls(
            id=str(tenant.id),
            slug=tenant.slug,
            name=tenant.name,
            is_active=tenant.is_active,
        )
