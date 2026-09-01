from fastapi import APIRouter

from app.api.v1 import admin, auth, health, leads, operator

router = APIRouter(prefix="/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(admin.router)
router.include_router(leads.router)
router.include_router(operator.router)
