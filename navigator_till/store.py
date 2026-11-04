"""Persisted sessions: one SQLite table, one JSON document per session, so the desk survives a
restart. Path from NT_DB (default ./navigator-till.db, gitignored). The two dataclasses a session
holds (pricing.Quote, agent.Request) are encoded with dataclasses.asdict and rebuilt on read.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from .agent import Request
from .pricing import Quote

DEFAULT_PATH = "navigator-till.db"
KINDS = {"quote": Quote, "request": Request}          # state key -> dataclass to rebuild


def encode(state: dict) -> str:
    out = {k: (asdict(v) if is_dataclass(v) else v) for k, v in state.items()}
    return json.dumps(out, ensure_ascii=False)


def decode(text: str) -> dict:
    st = json.loads(text)
    for key, cls in KINDS.items():
        if isinstance(st.get(key), dict):
            st[key] = cls(**st[key])
    st["log"] = [tuple(x) for x in st.get("log", [])]
    return st


class Store:
    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = str(path or os.environ.get("NT_DB") or DEFAULT_PATH)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, data TEXT NOT NULL, "
                      "updated_at TEXT NOT NULL)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def get(self, sid: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM sessions WHERE sid = ?", (sid,)).fetchone()
        return decode(row[0]) if row else None

    def put(self, sid: str, state: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn() as c:
            c.execute("INSERT INTO sessions (sid, data, updated_at) VALUES (?, ?, ?) "
                      "ON CONFLICT(sid) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                      (sid, encode(state), now))

    def delete(self, sid: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE sid = ?", (sid,))

    def items(self) -> list[tuple[str, dict]]:
        with self._conn() as c:
            rows = c.execute("SELECT sid, data FROM sessions ORDER BY updated_at").fetchall()
        return [(sid, decode(d)) for sid, d in rows]

    def find(self, key: str, value) -> list[tuple[str, dict]]:
        """Sessions whose state[key] == value (scanned in Python; the table is desk-sized)."""
        return [(sid, st) for sid, st in self.items() if st.get(key) == value]
