"""
Sentinel Memory Store — 持久化记忆
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path


class MemoryStore:
    """SQLite持久化记忆 — 告警历史、攻击模式、环境知识"""

    def __init__(self, db_path: str = "~/.sentinel/sentinel.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source_ip TEXT,
                    destination TEXT,
                    details TEXT,
                    ai_analysis TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER,
                    path TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (alert_id) REFERENCES alerts(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS threat_intel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicator TEXT NOT NULL,
                    type TEXT NOT NULL,
                    reputation TEXT,
                    source TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def save_alert(self, alert: dict) -> int:
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                """INSERT INTO alerts (timestamp, type, severity, source_ip, destination, details)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (alert["timestamp"], alert["type"], alert["severity"],
                 alert.get("source_ip"), alert.get("destination"),
                 json.dumps(alert.get("details", {})))
            )
            conn.commit()
            return cursor.lastrowid

    def get_alerts(self, limit: int = 50, severity: str = None) -> list:
        with sqlite3.connect(str(self.db_path)) as conn:
            if severity:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE severity=? ORDER BY timestamp DESC LIMIT ?",
                    (severity, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [dict(zip([c[0] for c in rows[0].__class__], row)) for row in rows] if rows else []

    def get_stats(self) -> dict:
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            open_count = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE status='open'"
            ).fetchone()[0]
            critical = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE severity='critical' AND status='open'"
            ).fetchone()[0]
        return {"total": total, "open": open_count, "critical_open": critical}
