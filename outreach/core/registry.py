"""Lightweight module registry — each feature plugs in independently."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from fastapi import FastAPI


class OutreachModule(Protocol):
    name: str
    version: str

    def init_db(self) -> None: ...

    def register_routes(self, router: Any) -> None: ...

    def on_startup(self, ctx: "AppContext") -> None: ...

    def on_shutdown(self) -> None: ...

    def health(self) -> dict[str, Any]: ...


@dataclass
class AppContext:
    settings: Any
    outbox: Any
    bitrix_factory: Callable[[], Any]
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleInfo:
    name: str
    version: str
    enabled: bool = True
    health: dict[str, Any] = field(default_factory=dict)


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: list[OutreachModule] = []

    def register(self, module: OutreachModule) -> None:
        names = {m.name for m in self._modules}
        if module.name in names:
            raise ValueError(f"module already registered: {module.name}")
        self._modules.append(module)

    @property
    def modules(self) -> list[OutreachModule]:
        return list(self._modules)

    def init_all(self) -> None:
        for m in self._modules:
            m.init_db()

    def startup_all(self, ctx: AppContext) -> None:
        for m in self._modules:
            m.on_startup(ctx)

    def shutdown_all(self) -> None:
        for m in reversed(self._modules):
            m.on_shutdown()

    def mount_routes(
        self,
        app: "FastAPI",
        *,
        prefix: str = "/api/modules",
        dependencies: list[Any] | None = None,
    ) -> None:
        from fastapi import APIRouter

        deps = dependencies or []
        for m in self._modules:
            router = APIRouter(prefix=f"{prefix}/{m.name}", tags=[m.name], dependencies=deps)
            m.register_routes(router)
            app.include_router(router)

    def catalog(self) -> list[dict[str, Any]]:
        out = []
        for m in self._modules:
            try:
                health = m.health()
            except Exception as exc:  # noqa: BLE001
                health = {"ok": False, "error": str(exc)[:200]}
            out.append(
                {
                    "name": m.name,
                    "version": m.version,
                    "health": health,
                }
            )
        return out
