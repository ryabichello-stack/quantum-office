from fastapi import APIRouter

from app.api.v1 import (
    admin,
    admin_cms,
    auth,
    billing,
    channels,
    connectors,
    health,
    leads,
    mcp,
    operator,
    phones,
    public,
    credentials,
    telephony,
    tenant,
    webhooks,
)

router = APIRouter(prefix="/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(public.router)
router.include_router(webhooks.router)
router.include_router(admin.router)
router.include_router(admin_cms.router)
router.include_router(tenant.router)
router.include_router(channels.router)
router.include_router(billing.router)
router.include_router(phones.router)
router.include_router(credentials.router)
router.include_router(telephony.router)
router.include_router(connectors.router)
router.include_router(mcp.router)
router.include_router(mcp.hermes_router)
router.include_router(leads.router)
router.include_router(operator.router)
