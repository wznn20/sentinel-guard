from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    agent_id TEXT DEFAULT 'main',
                    channel TEXT DEFAULT 'cli',
                    user_id TEXT DEFAULT 'user',
                    account_id TEXT DEFAULT 'default',
                    peer_id TEXT DEFAULT '*',
                    permission TEXT DEFAULT 'dangerous',
                    sandbox_profile TEXT DEFAULT 'default',
                    workspace TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    summarized_until_turn_id INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    channel TEXT DEFAULT 'cli',
                    skill TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    score REAL DEFAULT 0.0,
                    source_turn_id INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    start_turn_id INTEGER DEFAULT 0,
                    end_turn_id INTEGER DEFAULT 0,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skills (
                    name TEXT PRIMARY KEY,
                    trigger_terms TEXT NOT NULL,
                    description TEXT NOT NULL,
                    path TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    note TEXT DEFAULT '',
                    result_json TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    decided_at TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS tool_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_tool_grants (
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, tool_name)
                );
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    source_session_id TEXT DEFAULT '',
                    source_turn_id INTEGER,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_board (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT NOT NULL DEFAULT 'medium',
                    owner TEXT NOT NULL DEFAULT 'main',
                    parent_task_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS delegations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    parent_task_id INTEGER NOT NULL,
                    child_task_id INTEGER,
                    child_session_id TEXT DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'worker',
                    status TEXT NOT NULL DEFAULT 'pending',
                    note TEXT DEFAULT '',
                    result_json TEXT DEFAULT '{}',
                    started_at TEXT DEFAULT '',
                    completed_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "sessions", "agent_id", "TEXT DEFAULT 'main'")
            self._ensure_column(conn, "sessions", "channel", "TEXT DEFAULT 'cli'")
            self._ensure_column(conn, "sessions", "user_id", "TEXT DEFAULT 'user'")
            self._ensure_column(conn, "sessions", "account_id", "TEXT DEFAULT 'default'")
            self._ensure_column(conn, "sessions", "peer_id", "TEXT DEFAULT '*'")
            self._ensure_column(conn, "sessions", "permission", "TEXT DEFAULT 'dangerous'")
            self._ensure_column(conn, "sessions", "sandbox_profile", "TEXT DEFAULT 'default'")
            self._ensure_column(conn, "sessions", "workspace", "TEXT DEFAULT ''")
            self._ensure_column(conn, "sessions", "summary", "TEXT DEFAULT ''")
            self._ensure_column(
                conn, "sessions", "summarized_until_turn_id", "INTEGER DEFAULT 0"
            )
            self._ensure_column(conn, "approvals", "result_json", "TEXT DEFAULT ''")
            self._ensure_column(conn, "tool_runs", "metadata_json", "TEXT DEFAULT '{}'")
            self._ensure_column(conn, "delegations", "result_json", "TEXT DEFAULT '{}'")
            self._ensure_column(conn, "delegations", "started_at", "TEXT DEFAULT ''")
            self._ensure_column(conn, "delegations", "completed_at", "TEXT DEFAULT ''")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {row["name"] for row in rows}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def ensure_session(self, session_id: str, title: str | None = None, route: dict | None = None) -> None:
        route = route or {}
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE sessions
                    SET title=COALESCE(?, title),
                        agent_id=?,
                        channel=?,
                        user_id=?,
                        account_id=?,
                        peer_id=?,
                        permission=?,
                        sandbox_profile=?,
                        workspace=?,
                        updated_at=?
                    WHERE session_id=?
                    """,
                    (
                        title,
                        route.get("agent_id", "main"),
                        route.get("channel", "cli"),
                        route.get("user", "user"),
                        route.get("account", "default"),
                        route.get("peer", "*"),
                        route.get("permission", "dangerous"),
                        route.get("sandbox_profile", "default"),
                        route.get("workspace", ""),
                        now,
                        session_id,
                    ),
                )
                return

            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, title, agent_id, channel, user_id, account_id, peer_id,
                    permission, sandbox_profile, workspace, summary, summarized_until_turn_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, ?, ?)
                """,
                (
                    session_id,
                    title or session_id[:8],
                    route.get("agent_id", "main"),
                    route.get("channel", "cli"),
                    route.get("user", "user"),
                    route.get("account", "default"),
                    route.get("peer", "*"),
                    route.get("permission", "dangerous"),
                    route.get("sandbox_profile", "default"),
                    route.get("workspace", ""),
                    now,
                    now,
                ),
            )

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        channel: str = "cli",
        skill: str = "",
    ) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO turns (session_id, role, content, channel, skill, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, channel, skill, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE session_id=?",
                (now, session_id),
            )
            return int(cur.lastrowid)

    def list_turns(self, session_id: str, limit: int = 12) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, channel, skill, created_at
                FROM turns
                WHERE session_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def search_transcripts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, id AS turn_id, role, content, channel, skill, created_at
                FROM turns
                WHERE lower(content) LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_turns(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM turns WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def session_tree(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id) or {}
        nodes: list[dict[str, Any]] = []
        if session:
            nodes.append(
                {
                    "id": f"session:{session_id}",
                    "parent_id": None,
                    "kind": "root",
                    "title": session.get("title", session_id),
                    "content": json.dumps(
                        {
                            "agent_id": session.get("agent_id"),
                            "channel": session.get("channel"),
                            "permission": session.get("permission"),
                            "workspace": session.get("workspace"),
                        },
                        ensure_ascii=False,
                    ),
                    "score": 1.0,
                    "created_at": session.get("created_at", ""),
                }
            )

        with self._connect() as conn:
            summaries = conn.execute(
                """
                SELECT id, content, start_turn_id, end_turn_id, created_at
                FROM session_summaries
                WHERE session_id=?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            facts = conn.execute(
                """
                SELECT id, kind, title, content, score, source_turn_id, created_at
                FROM memory_items
                WHERE session_id=?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            turns = conn.execute(
                """
                SELECT id, role, content, skill, created_at
                FROM turns
                WHERE session_id=?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            tasks = conn.execute(
                """
                SELECT id, title, details, status, priority, owner, parent_task_id, created_at
                FROM task_board
                WHERE session_id=?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()

        for row in summaries:
            nodes.append(
                {
                    "id": f"summary:{row['id']}",
                    "parent_id": f"session:{session_id}",
                    "kind": "summary",
                    "title": f"turns {row['start_turn_id']}..{row['end_turn_id']}",
                    "content": row["content"],
                    "score": 0.95,
                    "created_at": row["created_at"],
                }
            )
        for row in facts:
            nodes.append(
                {
                    "id": f"memory:{row['id']}",
                    "parent_id": f"session:{session_id}",
                    "kind": row["kind"],
                    "title": row["title"],
                    "content": row["content"],
                    "score": row["score"],
                    "created_at": row["created_at"],
                }
            )
        for row in turns:
            nodes.append(
                {
                    "id": f"turn:{row['id']}",
                    "parent_id": f"session:{session_id}",
                    "kind": "turn",
                    "title": f"{row['role']}: {row['content'][:40]}",
                    "content": row["content"],
                    "score": 0.4,
                    "created_at": row["created_at"],
                }
            )
        for row in tasks:
            nodes.append(
                {
                    "id": f"task:{row['id']}",
                    "parent_id": f"session:{session_id}",
                    "kind": "task",
                    "title": f"{row['status']} [{row['owner']}] {row['title']}",
                    "content": row["details"],
                    "score": 0.9,
                    "created_at": row["created_at"],
                }
            )

        return {"session_id": session_id, "nodes": nodes}

    def search_sessions(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{query.lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, agent_id, channel, permission, summary, updated_at
                FROM sessions
                WHERE lower(session_id) LIKE ? OR lower(title) LIKE ? OR lower(summary) LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def recall_global(self, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        params: list[Any] = []
        clause = ""
        if query.strip():
            like = f"%{query.lower()}%"
            clause = """
                WHERE lower(title) LIKE ? OR lower(content) LIKE ?
            """
            params.extend([like, like])
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT session_id, kind, title, content, score, created_at
                FROM memory_items
                {clause}
                ORDER BY score DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def global_digest(self, limit: int = 10) -> dict[str, Any]:
        with self._connect() as conn:
            recent_sessions = conn.execute(
                """
                SELECT session_id, title, agent_id, channel, summary, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            top_memory = conn.execute(
                """
                SELECT session_id, kind, title, content, score, created_at
                FROM memory_items
                ORDER BY score DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            top_profile = conn.execute(
                """
                SELECT key, value, source_session_id, source_turn_id, updated_at
                FROM user_profile
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            top_tasks = conn.execute(
                """
                SELECT session_id, title, status, priority, owner, updated_at
                FROM task_board
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {
            "recent_sessions": [dict(row) for row in recent_sessions],
            "top_memory": [dict(row) for row in top_memory],
            "user_profile": [dict(row) for row in top_profile],
            "tasks": [dict(row) for row in top_tasks],
        }

    def session_digest(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id) or {}
        with self._connect() as conn:
            turn_count = conn.execute(
                "SELECT COUNT(*) AS n FROM turns WHERE session_id=?",
                (session_id,),
            ).fetchone()["n"]
            memory_count = conn.execute(
                "SELECT COUNT(*) AS n FROM memory_items WHERE session_id=?",
                (session_id,),
            ).fetchone()["n"]
            summary_count = conn.execute(
                "SELECT COUNT(*) AS n FROM session_summaries WHERE session_id=?",
                (session_id,),
            ).fetchone()["n"]
            skill_rows = conn.execute(
                """
                SELECT skill, COUNT(*) AS n
                FROM turns
                WHERE session_id=? AND skill != ''
                GROUP BY skill
                ORDER BY n DESC, skill ASC
                """,
                (session_id,),
            ).fetchall()
        return {
            "session_id": session_id,
            "title": session.get("title"),
            "agent_id": session.get("agent_id"),
            "channel": session.get("channel"),
            "permission": session.get("permission"),
            "workspace": session.get("workspace"),
            "summary": session.get("summary", ""),
            "turn_count": int(turn_count),
            "memory_count": int(memory_count),
            "summary_count": int(summary_count),
            "skills": [dict(row) for row in skill_rows],
            "updated_at": session.get("updated_at"),
        }

    def upsert_profile(
        self,
        key: str,
        value: str,
        source_session_id: str,
        source_turn_id: int | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profile (key, value, source_session_id, source_turn_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    source_session_id=excluded.source_session_id,
                    source_turn_id=excluded.source_turn_id,
                    updated_at=excluded.updated_at
                """,
                (
                    key,
                    value,
                    source_session_id,
                    source_turn_id,
                    datetime.utcnow().isoformat(),
                ),
            )

    def profile(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, source_session_id, source_turn_id, updated_at
                FROM user_profile
                ORDER BY key ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_task(
        self,
        session_id: str,
        title: str,
        details: str = "",
        status: str = "pending",
        priority: str = "medium",
        owner: str = "main",
        parent_task_id: int | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO task_board (
                    session_id, title, details, status, priority, owner, parent_task_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    title,
                    details,
                    status,
                    priority,
                    owner,
                    parent_task_id,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def update_task(
        self,
        task_id: int,
        *,
        status: str | None = None,
        owner: str | None = None,
        details: str | None = None,
        title: str | None = None,
        priority: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status=?")
            values.append(status)
        if owner is not None:
            fields.append("owner=?")
            values.append(owner)
        if details is not None:
            fields.append("details=?")
            values.append(details)
        if title is not None:
            fields.append("title=?")
            values.append(title)
        if priority is not None:
            fields.append("priority=?")
            values.append(priority)
        fields.append("updated_at=?")
        values.append(datetime.utcnow().isoformat())
        values.append(task_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE task_board SET {', '.join(fields)} WHERE id=?",
                values,
            )

    def list_tasks(self, session_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id=?")
            params.append(session_id)
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, session_id, title, details, status, priority, owner, parent_task_id, created_at, updated_at
                FROM task_board
                {where}
                ORDER BY updated_at DESC, id DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, session_id, title, details, status, priority, owner, parent_task_id, created_at, updated_at
                FROM task_board
                WHERE id=?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    def child_tasks(self, parent_task_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, title, details, status, priority, owner, parent_task_id, created_at, updated_at
                FROM task_board
                WHERE parent_task_id=?
                ORDER BY id ASC
                """,
                (parent_task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delegate_task(
        self,
        session_id: str,
        parent_task_id: int,
        child_task_id: int | None,
        child_session_id: str = "",
        role: str = "worker",
        status: str = "pending",
        note: str = "",
    ) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO delegations (
                    session_id, parent_task_id, child_task_id, child_session_id, role, status, note, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    parent_task_id,
                    child_task_id,
                    child_session_id,
                    role,
                    status,
                    note,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def update_delegation(self, delegation_id: int, status: str, note: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE delegations
                SET status=?, note=?, updated_at=?
                WHERE id=?
                """,
                (status, note, datetime.utcnow().isoformat(), delegation_id),
            )

    def update_delegation_result(
        self,
        delegation_id: int,
        status: str,
        result: dict[str, Any] | None = None,
        note: str = "",
        started: bool = False,
        completed: bool = False,
    ) -> None:
        now = datetime.utcnow().isoformat()
        fields = ["status=?", "note=?", "result_json=?", "updated_at=?"]
        values: list[Any] = [status, note, json.dumps(result or {}, ensure_ascii=False), now]
        if started:
            fields.append("started_at=?")
            values.append(now)
        if completed:
            fields.append("completed_at=?")
            values.append(now)
        values.append(delegation_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE delegations SET {', '.join(fields)} WHERE id=?",
                values,
            )

    def list_delegations(self, session_id: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if session_id is not None:
            where = "WHERE session_id=?"
            params.append(session_id)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, session_id, parent_task_id, child_task_id, child_session_id, role, status, note, result_json, started_at, completed_at, created_at, updated_at
                FROM delegations
                {where}
                ORDER BY updated_at DESC, id DESC
                """,
                params,
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json") or "{}")
            items.append(item)
        return items

    def delegations_for_parent_task(self, parent_task_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, parent_task_id, child_task_id, child_session_id, role, status, note, result_json, started_at, completed_at, created_at, updated_at
                FROM delegations
                WHERE parent_task_id=?
                ORDER BY id ASC
                """,
                (parent_task_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json") or "{}")
            items.append(item)
        return items

    def get_delegation(self, delegation_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, session_id, parent_task_id, child_task_id, child_session_id, role, status, note, result_json, started_at, completed_at, created_at, updated_at
                FROM delegations
                WHERE id=?
                """,
                (delegation_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json") or "{}")
        return item

    def next_pending_delegation(self, session_id: str | None = None) -> dict[str, Any] | None:
        params: list[Any] = []
        where = "WHERE status='assigned'"
        if session_id is not None:
            where += " AND session_id=?"
            params.append(session_id)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, session_id, parent_task_id, child_task_id, child_session_id, role, status, note, result_json, started_at, completed_at, created_at, updated_at
                FROM delegations
                {where}
                ORDER BY id ASC
                LIMIT 1
                """,
                params,
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json") or "{}")
        return item

    def summarize_session(
        self,
        session_id: str,
        summary: str,
        start_turn_id: int = 0,
        end_turn_id: int = 0,
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET summary=?, summarized_until_turn_id=?, updated_at=?
                WHERE session_id=?
                """,
                (summary, end_turn_id, now, session_id),
            )
            conn.execute(
                """
                INSERT INTO session_summaries (session_id, start_turn_id, end_turn_id, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, start_turn_id, end_turn_id, summary, now),
            )

    def remember(
        self,
        session_id: str,
        kind: str,
        title: str,
        content: str,
        score: float = 0.8,
        source_turn_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO memory_items (session_id, kind, title, content, score, source_turn_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    kind,
                    title,
                    content,
                    score,
                    source_turn_id,
                    datetime.utcnow().isoformat(),
                ),
            )
            return int(cur.lastrowid)

    def recall(self, session_id: str, query: str = "", limit: int = 6) -> list[dict[str, Any]]:
        params: list[Any] = [session_id]
        clause = ""
        if query.strip():
            like = f"%{query.lower()}%"
            clause = "AND (lower(title) LIKE ? OR lower(content) LIKE ?)"
            params.extend([like, like])
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT kind, title, content, score, created_at
                FROM memory_items
                WHERE session_id=? {clause}
                ORDER BY score DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_summary(self, session_id: str) -> str:
        session = self.get_session(session_id) or {}
        return str(session.get("summary") or "")

    def summarized_until_turn_id(self, session_id: str) -> int:
        session = self.get_session(session_id) or {}
        return int(session.get("summarized_until_turn_id") or 0)

    def turns_for_summary(
        self,
        session_id: str,
        after_turn_id: int,
        before_turn_id: int,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, skill
                FROM turns
                WHERE session_id=? AND id>? AND id<=?
                ORDER BY id ASC
                """,
                (session_id, after_turn_id, before_turn_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def last_turn_id(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(id) AS last_id FROM turns WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return int(row["last_id"] or 0) if row else 0

    def register_skill(
        self,
        name: str,
        trigger_terms: list[str],
        description: str,
        path: str,
        source: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO skills (name, trigger_terms, description, path, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    trigger_terms=excluded.trigger_terms,
                    description=excluded.description,
                    path=excluded.path,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    name,
                    json.dumps(trigger_terms, ensure_ascii=False),
                    description,
                    path,
                    source,
                    datetime.utcnow().isoformat(),
                ),
            )

    def list_skills(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, trigger_terms, description, path, source, updated_at FROM skills ORDER BY name ASC"
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["trigger_terms"] = json.loads(item["trigger_terms"])
            items.append(item)
        return items

    def request_approval(self, session_id: str, action: str, payload: dict[str, Any]) -> int:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO approvals (session_id, action, payload_json, status, note, result_json, created_at, decided_at)
                VALUES (?, ?, ?, 'pending', '', '', ?, '')
                """,
                (session_id, action, json.dumps(payload, ensure_ascii=False), now),
            )
            return int(cur.lastrowid)

    def list_pending_approvals(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM approvals
                WHERE status='pending'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_approval(self, approval_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE id=?",
                (approval_id,),
            ).fetchone()
        return dict(row) if row else None

    def decide_approval(
        self,
        approval_id: int,
        status: str,
        note: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status=?, note=?, result_json=?, decided_at=?
                WHERE id=?
                """,
                (
                    status,
                    note,
                    json.dumps(result or {}, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                    approval_id,
                ),
            )

    def grant_tool_reuse(self, session_id: str, tool_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_tool_grants (session_id, tool_name, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, tool_name) DO NOTHING
                """,
                (session_id, tool_name, datetime.utcnow().isoformat()),
            )

    def has_tool_reuse(self, session_id: str, tool_name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM session_tool_grants
                WHERE session_id=? AND tool_name=?
                """,
                (session_id, tool_name),
            ).fetchone()
        return row is not None

    def log_tool_run(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        status: str,
        output: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tool_runs (session_id, tool_name, arguments_json, status, output, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    tool_name,
                    json.dumps(arguments, ensure_ascii=False),
                    status,
                    output,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                ),
            )
            return int(cur.lastrowid)

    def list_tool_runs(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM tool_runs
                WHERE session_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["arguments"] = json.loads(item.pop("arguments_json"))
            item["metadata"] = json.loads(item.pop("metadata_json"))
            items.append(item)
        return items
