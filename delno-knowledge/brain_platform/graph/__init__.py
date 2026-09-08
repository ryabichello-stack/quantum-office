"""Knowledge graph (Postgres tables / SQLite stubs) — G1+G2."""

from brain_platform.graph.rebuild import rebuild_graph_from_corpus
from brain_platform.graph.store import GraphStore

__all__ = ["GraphStore", "rebuild_graph_from_corpus"]
