"""E1.9 — per-tenant vault paths."""

from pathlib import Path

from brain_platform.vault_paths import resolve_vault_path, tenant_vault_root, vault_root


def test_tenant_vault_root_isolated():
    root = tenant_vault_root("acme-corp")
    assert root.name == "acme-corp"
    assert root.parent == vault_root()


def test_resolve_vault_path_without_existing_dir(monkeypatch):
    monkeypatch.setenv("BRAIN_VAULT_ROOT", "/nonexistent/vault-root")
    resolved = resolve_vault_path("acme")
    assert str(resolved).endswith("/acme") or str(resolved).endswith("acme")
