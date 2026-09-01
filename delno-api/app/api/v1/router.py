from fastapi import APIRouter

from app.api.v1 import health, leads, operator

router = APIRouter(prefix="/v1")
router.include_router(health.router)
router.include_router(leads.router)
router.include_router(operator.router)
