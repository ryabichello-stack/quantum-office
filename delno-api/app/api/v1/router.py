from fastapi import APIRouter

from app.api.v1 import admin, admin_cms, auth, channels, health, leads, operator, public, tenant, webhooks

router = APIRouter(prefix="/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(public.router)
router.include_router(webhooks.router)
router.include_router(admin.router)
router.include_router(admin_cms.router)
router.include_router(tenant.router)
router.include_router(channels.router)
router.include_router(leads.router)
router.include_router(operator.router)
