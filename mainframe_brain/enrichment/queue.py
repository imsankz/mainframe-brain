"""Resumable enrichment queue backed by the store's SQLite connection.

On crash+restart, only pending and in_progress items are retried — done items
are skipped. The queue is populated by the CLI enrich command before the
enrichment loop runs.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS enrichment_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_hash TEXT NOT NULL,
    unit_kind TEXT NOT NULL,
    unit_name TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    codebase_id TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'in_progress', 'done')),
    risk_score REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    completed_at TEXT
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnrichmentQueue:
    """Resumable work queue for enrichment items stored in the brain's SQLite DB."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.execute(_CREATE_TABLE)
        conn.commit()

    # ------------------------------------------------------------------
    #  Core operations
    # ------------------------------------------------------------------

    def add(
        self,
        unit_hash: str,
        unit_kind: str,
        unit_name: str,
        source_node_id: str,
        codebase_id: str = "default",
        risk_score: float = 0.0,
    ) -> int:
        """Insert a new item into the queue. Returns the row id."""
        cur = self._conn.execute(
            """INSERT INTO enrichment_queue
               (unit_hash, unit_kind, unit_name, source_node_id, codebase_id,
                status, risk_score, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (unit_hash, unit_kind, unit_name, source_node_id, codebase_id,
             risk_score, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid) if cur.lastrowid else 0

    def next_pending(self) -> dict | None:
        """Atomically claim the next pending item and mark it in_progress.

        Returns a dict with keys matching the table columns, or None if the
        queue is exhausted.
        """
        row = self._conn.execute(
            """SELECT id, unit_hash, unit_kind, unit_name, source_node_id,
                      codebase_id, status, risk_score, created_at, completed_at
               FROM enrichment_queue
               WHERE status = 'pending'
               ORDER BY risk_score DESC, id ASC
               LIMIT 1"""
        ).fetchone()

        if row is None:
            return None

        self._conn.execute(
            "UPDATE enrichment_queue SET status = 'in_progress' WHERE id = ?",
            (row["id"],),
        )
        self._conn.commit()
        return dict(row)

    def mark_done(self, item_id: int) -> None:
        """Mark a queue item as successfully completed."""
        self._conn.execute(
            """UPDATE enrichment_queue
               SET status = 'done', completed_at = ?
               WHERE id = ?""",
            (_now(), item_id),
        )
        self._conn.commit()

    def mark_failed(self, item_id: int) -> None:
        """Reset an item back to pending so it will be retried."""
        self._conn.execute(
            "UPDATE enrichment_queue SET status = 'pending' WHERE id = ?",
            (item_id,),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    #  Progress / introspection
    # ------------------------------------------------------------------

    def progress(self) -> dict[str, int]:
        """Return {total, pending, in_progress, done} counts."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM enrichment_queue GROUP BY status"
        ).fetchall()
        counts: dict[str, int] = {"total": 0, "pending": 0, "in_progress": 0, "done": 0}
        for r in rows:
            counts[r["status"]] = r["cnt"]
            counts["total"] += r["cnt"]
        return counts

    def reset_in_progress(self) -> int:
        """Reset any in_progress items back to pending (crash recovery).

        Returns the number of items reset.
        """
        cur = self._conn.execute(
            "UPDATE enrichment_queue SET status = 'pending' WHERE status = 'in_progress'",
        )
        self._conn.commit()
        return cur.rowcount

    def total_remaining(self) -> int:
        """Number of items not yet done."""
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM enrichment_queue WHERE status != 'done'"
        ).fetchone()
        return row["cnt"] if row else 0


__all__ = ["EnrichmentQueue"]
