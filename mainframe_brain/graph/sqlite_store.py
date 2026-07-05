"""SQLite backend for the Mainframe Brain graph store."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .schema import SCHEMA_VERSION, Edge, EdgeType, Node, NodeType
from .store import GraphStore

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    codebase_id TEXT NOT NULL,
    content_hash TEXT,
    last_verified TEXT,
    parse_confidence REAL,
    properties TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT,
    dst TEXT,
    type TEXT,
    properties TEXT,
    created_at TEXT,
    PRIMARY KEY (src, dst, type)
);
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS node_history (
    id TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    codebase_id TEXT NOT NULL,
    content_hash TEXT,
    last_verified TEXT,
    parse_confidence REAL,
    properties TEXT,
    created_at TEXT,
    updated_at TEXT,
    op TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_content_hash ON nodes(content_hash);
CREATE INDEX IF NOT EXISTS idx_nodes_codebase_id ON nodes(codebase_id);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_node(row: sqlite3.Row) -> Node:
    return Node(
        id=row["id"],
        type=NodeType(row["type"]),
        name=row["name"],
        codebase_id=row["codebase_id"],
        content_hash=row["content_hash"] or "",
        last_verified=row["last_verified"] or "",
        parse_confidence=row["parse_confidence"] if row["parse_confidence"] is not None else 1.0,
        properties=json.loads(row["properties"]) if row["properties"] else {},
    )


def _row_to_edge(row: sqlite3.Row) -> Edge:
    return Edge(
        src=row["src"],
        dst=row["dst"],
        type=EdgeType(row["type"]),
        properties=json.loads(row["properties"]) if row["properties"] else {},
    )


class SQLiteGraphStore(GraphStore):
    def __init__(self, path: str, codebase_id: str = "default") -> None:
        self.path = path
        self.codebase_id = codebase_id
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA_DDL)
            self._conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SCHEMA_VERSION,),
            )
            self._conn.commit()

    def add_node(self, node: Node) -> None:
        props_json = json.dumps(node.properties, default=str, sort_keys=True)
        now = _now()
        op = "update" if self.get_node(node.id) is not None else "add"
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO nodes (id, type, name, codebase_id, content_hash,
                                    last_verified, parse_confidence, properties,
                                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type=excluded.type,
                    name=excluded.name,
                    codebase_id=excluded.codebase_id,
                    content_hash=excluded.content_hash,
                    last_verified=excluded.last_verified,
                    parse_confidence=excluded.parse_confidence,
                    properties=excluded.properties,
                    updated_at=excluded.updated_at
                """,
                (
                    node.id,
                    node.type.value,
                    node.name,
                    node.codebase_id,
                    node.content_hash,
                    node.last_verified,
                    node.parse_confidence,
                    props_json,
                    now,
                    now,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO node_history (id, type, name, codebase_id, content_hash,
                                           last_verified, parse_confidence, properties,
                                           created_at, updated_at, op, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.type.value,
                    node.name,
                    node.codebase_id,
                    node.content_hash,
                    node.last_verified,
                    node.parse_confidence,
                    props_json,
                    now,
                    now,
                    op,
                    now,
                ),
            )
            self._conn.commit()

    def add_edge(self, edge: Edge) -> None:
        props_json = json.dumps(edge.properties, default=str, sort_keys=True)
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO edges (src, dst, type, properties, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (edge.src, edge.dst, edge.type.value, props_json, _now()),
            )
            self._conn.commit()

    def get_node(self, node_id: str) -> Node | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return _row_to_node(row) if row else None

    def all_nodes(self) -> list[Node]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM nodes").fetchall()
        return [_row_to_node(r) for r in rows]

    def all_edges(self) -> list[Edge]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM edges").fetchall()
        return [_row_to_edge(r) for r in rows]

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[Node]:
        with self._lock:
            if edge_type is not None:
                cur = self._conn.execute(
                    """
                    SELECT n.* FROM nodes n
                    JOIN edges e ON e.dst = n.id
                    WHERE e.src = ? AND e.type = ?
                    """,
                    (node_id, edge_type),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT n.* FROM nodes n
                    JOIN edges e ON e.dst = n.id
                    WHERE e.src = ?
                    """,
                    (node_id,),
                )
            rows = cur.fetchall()
        return [_row_to_node(r) for r in rows]

    def query(self, cypher_or_sql: str) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(cypher_or_sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        out: list[dict] = []
        for r in rows:
            d = {}
            for col, val in zip(cols, r, strict=False):
                if col == "properties" and isinstance(val, str) and val:
                    try:
                        d[col] = json.loads(val)
                    except (json.JSONDecodeError, ValueError):
                        d[col] = val
                else:
                    d[col] = val
            out.append(d)
        return out

    def diff_against(self, other: GraphStore) -> dict[str, list[str]]:
        self_ids = {n.id: n.content_hash for n in self.all_nodes()}
        other_ids = {n.id: n.content_hash for n in other.all_nodes()}
        added = sorted(set(self_ids) - set(other_ids))
        removed = sorted(set(other_ids) - set(self_ids))
        changed = sorted(
            nid for nid in (set(self_ids) & set(other_ids)) if self_ids[nid] != other_ids[nid]
        )
        return {"added": added, "removed": removed, "changed": changed}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


__all__ = ["SQLiteGraphStore"]