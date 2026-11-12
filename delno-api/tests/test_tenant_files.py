"""F0 — tenant file path isolation."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services.tenant_files import (
    TenantFileError,
    object_key,
    residency_status,
    resolve_tenant_path,
    tenant_prefix,
)


def test_resolve_happy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    tid = uuid.uuid4()
    path = resolve_tenant_path(tid, zone="uploads", relative="a/b.md", create_parents=True)
    assert path.is_relative_to(tmp_path / str(tid) / "uploads")
    assert path.name == "b.md"
    get_settings.cache_clear()


def test_reject_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    tid = uuid.uuid4()
    with pytest.raises(TenantFileError) as exc:
        resolve_tenant_path(tid, zone="uploads", relative="../other/x")
    assert exc.value.code == "path_traversal"
    get_settings.cache_clear()


def test_reject_bad_zone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(TenantFileError) as exc:
        resolve_tenant_path(uuid.uuid4(), zone="../../etc", relative="passwd")
    assert exc.value.code == "invalid_zone"
    get_settings.cache_clear()


def test_object_key_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    tid = uuid.uuid4()
    key = object_key(tid, zone="knowledge", name="profile.md")
    assert key == f"t/{tid}/knowledge/profile.md"
    assert str(tenant_prefix(tid)).endswith(str(tid))
    get_settings.cache_clear()


def test_residency_ru_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_FILES_REGION", "ru-central1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    st = residency_status()
    assert st["ok"] is True
    assert "РФ" in st["message_ru"] or "обезлич" in st["message_ru"]
    get_settings.cache_clear()
