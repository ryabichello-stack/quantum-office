from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.tenant import router
from app.core.auth import get_tenant_context_auth
from app.core.db import Base, get_db
from app.core.tenant import TenantContext
from app.models.tenant import Tenant


def test_file_routes_keep_two_companies_separate(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.tenant_files.tenants_root", lambda: tmp_path)
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    a = Tenant(slug="files-api-a", name="A", settings={}, is_active=True)
    b = Tenant(slug="files-api-b", name="B", settings={}, is_active=True)
    db.add_all([a, b])
    db.commit()
    current = {"tenant": a}
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_tenant_context_auth] = lambda: TenantContext(
        tenant_id=current["tenant"].id, tenant_slug=current["tenant"].slug, role="tenant_owner"
    )
    client = TestClient(app)

    folder = client.post("/v1/tenant/folders", json={"name": "Предложения"})
    assert folder.status_code == 200
    folder_id = folder.json()["folder"]["id"]
    upload = client.post("/v1/tenant/files", data={"folder_id": folder_id}, files={"file": ("offer.txt", b"offer", "text/plain")})
    assert upload.status_code == 200
    file_id = upload.json()["file"]["id"]
    assert client.get("/v1/tenant/files").json()["items"][0]["folder_id"] == folder_id
    assert client.get(f"/v1/tenant/files/{file_id}").content == b"offer"

    current["tenant"] = b
    assert client.get("/v1/tenant/files").json() == {"items": [], "folders": []}
    assert client.get(f"/v1/tenant/files/{file_id}").status_code == 404
    assert client.delete(f"/v1/tenant/files/{file_id}").status_code == 404
    assert client.post("/v1/tenant/files", data={"folder_id": folder_id}, files={"file": ("x.txt", b"x", "text/plain")}).status_code == 400

    current["tenant"] = a
    assert client.delete(f"/v1/tenant/folders/{folder_id}").status_code == 400
    assert client.patch(f"/v1/tenant/files/{file_id}", json={"folder_id": None}).status_code == 200
    assert client.delete(f"/v1/tenant/folders/{folder_id}").status_code == 200
    assert client.delete(f"/v1/tenant/files/{file_id}").status_code == 200
    assert client.get("/v1/tenant/files").json() == {"items": [], "folders": []}
