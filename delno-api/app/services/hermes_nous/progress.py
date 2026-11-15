"""In-process tool progress for the cabinet stream.

Fast paths inside the API (KB draft from a site, web research, setup checks) call
tools through ``registry.run`` without a Hermes run, so the stream had nothing to
show but «Думаю над ответом». ``registry.run`` reports each tool here; the stream
sets a sink for the duration of one turn. No sink means no-op. Never secrets.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

Sink = Callable[[dict[str, Any]], None]

_sink: ContextVar[Sink | None] = ContextVar("delno_tool_progress_sink", default=None)


@contextlib.contextmanager
def progress_sink(sink: Sink) -> Iterator[None]:
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def _preview(params: dict[str, Any]) -> str | None:
    url = params.get("url")
    if isinstance(url, str) and url.strip():
        host = urlparse(url.strip()).netloc or url.strip()
        return host[:120]
    query = params.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()[:120]
    return None


def report_tool(name: str, phase: str, params: dict[str, Any] | None = None) -> None:
    sink = _sink.get()
    if sink is None or not name:
        return
    event: dict[str, Any] = {"phase": phase, "tool": str(name)[:120]}
    if phase == "tool":
        preview = _preview(params or {})
        if preview:
            event["preview"] = preview
    try:
        sink(event)
    except Exception:  # noqa: BLE001 — progress must never break a tool
        pass
