"""Graph storage interface. Backends are swappable — SQLite now, Kùzu/Neo4j later."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .schema import SCHEMA_VERSION, Edge, Node


class GraphStore(ABC):
    """Abstract graph store. Implementations must be additive-with-history."""

    schema_version: str = SCHEMA_VERSION

    @abstractmethod
    def add_node(self, node: Node) -> None: ...

    @abstractmethod
    def add_edge(self, edge: Edge) -> None: ...

    def add_nodes(self, nodes: Iterable[Node]) -> None:
        for n in nodes:
            self.add_node(n)

    def add_edges(self, edges: Iterable[Edge]) -> None:
        for e in edges:
            self.add_edge(e)

    @abstractmethod
    def get_node(self, node_id: str) -> Node | None: ...

    @abstractmethod
    def all_nodes(self) -> list[Node]: ...

    @abstractmethod
    def all_edges(self) -> list[Edge]: ...

    @abstractmethod
    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[Node]: ...

    @abstractmethod
    def predecessors(self, node_id: str, edge_type: str | None = None) -> list[Node]:
        """Return nodes that have an edge *to* ``node_id`` (incoming neighbors)."""

    @abstractmethod
    def query(self, cypher_or_sql: str) -> list[dict]: ...

    @abstractmethod
    def diff_against(self, other: GraphStore) -> dict[str, list[str]]:
        """Return {added, removed, changed} node ids vs another store/run."""

    @abstractmethod
    def close(self) -> None: ...


def make_node_id(node_type: str, codebase_id: str, name: str) -> str:
    return f"{node_type}:{codebase_id}:{name}"


__all__ = ["GraphStore", "make_node_id"]