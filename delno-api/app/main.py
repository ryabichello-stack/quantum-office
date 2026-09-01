from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.db import Base, engine
from app.operator.tools import register_builtin_tools
from app.scripts.seed import seed_demo_tenant


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 — register ORM tables for create_all

    Base.metadata.create_all(bind=engine)
    seed_demo_tenant()
    register_builtin_tools()
    yield


app = FastAPI(title="DELNO API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router)


@app.get("/health")
def health_root() -> dict:
    return {"ok": True, "service": "delno-api"}
