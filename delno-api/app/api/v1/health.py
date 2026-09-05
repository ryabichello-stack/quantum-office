from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_v1() -> dict:
    return {"ok": True, "service": "delno-api", "version": "0.1.0"}
