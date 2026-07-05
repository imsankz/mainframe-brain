"""Narration cache — persists per-content-hash LLM narrations in the brain's DB.

The cache key is the POST-redaction content hash, so the cache is keyed to
exactly the text the LLM saw. Adding a new redaction rule does NOT force
every paragraph to re-narrate — the meaning never changed, only the scrubbed
surface did.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class NarrationCache:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS narration_cache (
                content_hash TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                human_verified INTEGER NOT NULL DEFAULT 0,
                stale INTEGER NOT NULL DEFAULT 0
            )"""
        )
        self._conn.commit()

    def get(self, content_hash: str) -> dict | None:
        row = self._conn.execute(
            "SELECT payload, stale FROM narration_cache WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        payload["stale"] = bool(row[1])
        return payload

    def put(self, content_hash: str, payload: dict, human_verified: bool = False) -> None:
        self._conn.execute(
            """INSERT INTO narration_cache (content_hash, payload, created_at, human_verified, stale)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(content_hash) DO UPDATE SET
                   payload=excluded.payload,
                   created_at=excluded.created_at,
                   human_verified=excluded.human_verified,
                   stale=0""",
            (content_hash, json.dumps(payload), _now(), int(human_verified)),
        )
        self._conn.commit()

    def mark_verified(self, content_hash: str, verified: bool = True) -> None:
        self._conn.execute(
            "UPDATE narration_cache SET human_verified = ? WHERE content_hash = ?",
            (int(verified), content_hash),
        )
        self._conn.commit()

    def mark_stale(self, content_hash: str, stale: bool = True) -> None:
        self._conn.execute(
            "UPDATE narration_cache SET stale = ? WHERE content_hash = ?",
            (int(stale), content_hash),
        )
        self._conn.commit()

    def is_stale(self, content_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT stale FROM narration_cache WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return bool(row and row[0])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["NarrationCache"]