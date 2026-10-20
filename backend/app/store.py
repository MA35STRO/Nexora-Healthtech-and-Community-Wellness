"""SQLite persistence. Stores events, incidents and small health records — never video frames."""
import json
import sqlite3
import threading
from typing import Any, Optional

from .models import Event, Incident

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  t REAL NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL,
  source TEXT NOT NULL, incident_id INTEGER
);
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (          -- vitals, doses, wellness check-ins, activity summaries
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, t REAL NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_kind_t ON records (kind, t);
"""


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    # ---------- events & incidents ----------
    def add_event(self, e: Event) -> Event:
        with self.lock, self.db:
            cur = self.db.execute(
                "INSERT INTO events (t, kind, message, source, incident_id) VALUES (?,?,?,?,?)",
                (e.t, e.kind, e.message, e.source, e.incident_id))
            e.id = cur.lastrowid
        return e

    def recent_events(self, limit: int = 100, since: float = 0) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id, t, kind, message, source, incident_id FROM events WHERE t >= ? ORDER BY id DESC LIMIT ?",
                (since, limit)).fetchall()
        return [dict(zip(("id", "t", "kind", "message", "source", "incident_id"), r)) for r in rows]

    def save_incident(self, inc: Incident):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO incidents (id, data) VALUES (?, ?)",
                            (inc.id, json.dumps(inc.dict())))

    def recent_incidents(self, limit: int = 30) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT data FROM incidents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def max_incident_id(self) -> int:
        with self.lock:
            return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM incidents").fetchone()[0]

    # ---------- key/value (settings, med schedule, learned baselines) ----------
    def kv_get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute("SELECT data FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def kv_set(self, key: str, value: Any):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO kv (key, data) VALUES (?, ?)", (key, json.dumps(value)))

    # ---------- time-series records ----------
    def add_record(self, kind: str, t: float, data: dict) -> int:
        with self.lock, self.db:
            return self.db.execute("INSERT INTO records (kind, t, data) VALUES (?,?,?)",
                                   (kind, t, json.dumps(data))).lastrowid

    def add_records(self, rows: list[tuple[str, float, dict]]):
        with self.lock, self.db:
            self.db.executemany("INSERT INTO records (kind, t, data) VALUES (?,?,?)",
                                [(k, t, json.dumps(d)) for k, t, d in rows])

    def records(self, kind: str, since: float = 0, until: Optional[float] = None, limit: int = 5000) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT t, data FROM records WHERE kind = ? AND t >= ? AND t <= ? ORDER BY t DESC LIMIT ?",
                (kind, since, until if until is not None else 1e12, limit)).fetchall()
        return [{"t": t, **json.loads(d)} for t, d in reversed(rows)]

    def prune(self, kind: str, before: float):
        with self.lock, self.db:
            self.db.execute("DELETE FROM records WHERE kind = ? AND t < ?", (kind, before))

    def clear(self):
        with self.lock, self.db:
            for table in ("events", "incidents", "kv", "records"):
                self.db.execute(f"DELETE FROM {table}")
