"""SQLite-backed store for the minimal web workspace."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from apps.webapp.models import MessageRecord, RunRecord, SessionSummary


def utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(tz=UTC).isoformat()


def default_db_path() -> Path:
    """Return the default sqlite path for the web workspace state."""
    db_dir = Path.home() / ".code2workspace"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "webapp.db"


class AppStore:
    """Simple repository-local store for web sessions and one-shot runs."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create the required tables if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    run_id TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    exit_code INTEGER,
                    output TEXT NOT NULL DEFAULT '',
                    error TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                """
            )

    def list_sessions(self) -> list[SessionSummary]:
        """Return web sessions ordered by most recent update."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.status,
                    s.created_at,
                    s.updated_at,
                    (
                        SELECT substr(m.content, 1, 160)
                        FROM messages m
                        WHERE m.session_id = s.id
                        ORDER BY m.created_at DESC
                        LIMIT 1
                    ) AS last_message_preview,
                    (
                        SELECT r.id
                        FROM runs r
                        WHERE r.session_id = s.id
                        ORDER BY r.created_at DESC
                        LIMIT 1
                    ) AS latest_run_id,
                    (
                        SELECT r.status
                        FROM runs r
                        WHERE r.session_id = s.id
                        ORDER BY r.created_at DESC
                        LIMIT 1
                    ) AS latest_run_status,
                    (
                        SELECT COUNT(*)
                        FROM runs r
                        WHERE r.session_id = s.id
                    ) AS run_count
                FROM sessions s
                ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [
            SessionSummary(
                id=row["id"],
                title=row["title"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                last_message_preview=row["last_message_preview"],
                latest_run_id=row["latest_run_id"],
                latest_run_status=row["latest_run_status"],
                run_count=row["run_count"],
            )
            for row in rows
        ]

    def create_session(self, title: str | None = None) -> SessionSummary:
        """Create a new web session."""
        session_id = str(uuid4())
        now = utc_now()
        session_title = (title or "Untitled Session").strip() or "Untitled Session"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, session_title, "idle", now, now),
            )
        return SessionSummary(
            id=session_id,
            title=session_title,
            status="idle",
            created_at=now,
            updated_at=now,
            last_message_preview=None,
            latest_run_id=None,
            latest_run_status=None,
            run_count=0,
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete one session and its dependent records."""
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def get_session(self, session_id: str) -> dict | None:
        """Return one session with all messages and runs."""
        with self._connect() as conn:
            session_row = conn.execute(
                """
                SELECT id, title, status, created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if session_row is None:
                return None

            message_rows = conn.execute(
                """
                SELECT id, session_id, role, content, created_at, run_id
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            run_rows = conn.execute(
                """
                SELECT id, session_id, prompt, status, created_at, started_at,
                       finished_at, exit_code, output, error
                FROM runs
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,),
            ).fetchall()

        return {
            "session": {
                "id": session_row["id"],
                "title": session_row["title"],
                "status": session_row["status"],
                "created_at": session_row["created_at"],
                "updated_at": session_row["updated_at"],
            },
            "messages": [
                MessageRecord(
                    id=row["id"],
                    session_id=row["session_id"],
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                    run_id=row["run_id"],
                ).__dict__
                for row in message_rows
            ],
            "runs": [
                RunRecord(
                    id=row["id"],
                    session_id=row["session_id"],
                    prompt=row["prompt"],
                    status=row["status"],
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                    exit_code=row["exit_code"],
                    output=row["output"],
                    error=row["error"],
                ).__dict__
                for row in run_rows
            ],
        }

    def get_run(self, run_id: str) -> dict | None:
        """Return one run without scanning all sessions."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, session_id, prompt, status, created_at, started_at,
                       finished_at, exit_code, output, error
                FROM runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            id=row["id"],
            session_id=row["session_id"],
            prompt=row["prompt"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            exit_code=row["exit_code"],
            output=row["output"],
            error=row["error"],
        ).__dict__

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        run_id: str | None = None,
    ) -> MessageRecord:
        """Persist one message and update the session timestamp."""
        message_id = str(uuid4())
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, session_id, role, content, created_at, run_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, now, run_id),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return MessageRecord(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
            run_id=run_id,
        )

    def create_run(self, session_id: str, prompt: str) -> RunRecord:
        """Create one queued run."""
        run_id = str(uuid4())
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, session_id, prompt, status, created_at, output
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, session_id, prompt, "queued", now, ""),
            )
            conn.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
                ("queued", now, session_id),
            )
        return RunRecord(
            id=run_id,
            session_id=session_id,
            prompt=prompt,
            status="queued",
            created_at=now,
            started_at=None,
            finished_at=None,
            exit_code=None,
            output="",
            error=None,
        )

    def mark_run_running(self, run_id: str) -> None:
        """Mark one run as executing."""
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                """
                UPDATE runs
                SET status = ?, started_at = ?
                WHERE id = ?
                """,
                ("running", now, run_id),
            )
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                ("running", now, row["session_id"]),
            )

    def complete_run(
        self,
        run_id: str,
        *,
        status: str,
        output: str,
        exit_code: int | None,
        error: str | None = None,
    ) -> None:
        """Finalize one run and sync session state."""
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, exit_code = ?, output = ?, error = ?
                WHERE id = ?
                """,
                (status, now, exit_code, output, error, run_id),
            )
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, now, row["session_id"]),
            )

    def append_run_output(self, run_id: str, chunk: str) -> None:
        """Append streamed output for one running task."""
        if not chunk:
            return
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                """
                UPDATE runs
                SET output = COALESCE(output, '') || ?
                WHERE id = ?
                """,
                (chunk, run_id),
            )
            conn.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, row["session_id"]),
            )

    def maybe_update_title_from_prompt(self, session_id: str, prompt: str) -> None:
        """Replace the default title with a prompt-derived summary."""
        normalized = " ".join(prompt.split())
        if not normalized:
            return
        derived = normalized[:72].strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT title FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return
            if row["title"] != "Untitled Session":
                return
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (derived, utc_now(), session_id),
            )
