from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.db import Base, engine
from app.operator.tools import register_builtin_tools
from app.scripts.seed import seed_demo_tenant


def _cors_kwargs() -> dict:
    settings = get_settings()
    origins_raw = (settings.cors_allow_origins or "").strip()
    if origins_raw:
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
        return {
            "allow_origins": origins,
            "allow_credentials": settings.cors_allow_credentials,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    return {
        "allow_origin_regex": (
            r"https://([a-z0-9-]+\.)?dlno\.ru"
            r"|https://a\.47z\.ru"
            r"|http://localhost(:\d+)?"
            r"|http://127\.0\.0\.1(:\d+)?"
        ),
        "allow_credentials": False,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 — register ORM tables for create_all

    Base.metadata.create_all(bind=engine)
    seed_demo_tenant()
    register_builtin_tools()
    yield


app = FastAPI(title="DELNO API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, **_cors_kwargs())
app.include_router(v1_router)


@app.get("/health")
def health_root() -> dict:
    return {"ok": True, "service": "delno-api"}
