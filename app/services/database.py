"""SQLite storage for customers, sessions, and OAuth state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL,
    code_verifier TEXT,
    redirect_uri TEXT
);

CREATE TABLE IF NOT EXISTS gmail_connections (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    email TEXT NOT NULL,
    connected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    use_case TEXT NOT NULL DEFAULT 'all',
    onboarding_completed INTEGER NOT NULL DEFAULT 0,
    onboarding_skipped_count INTEGER NOT NULL DEFAULT 0,
    onboarding_completed_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_results (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    run_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_results_user_created
    ON agent_results(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_results_user_agent
    ON agent_results(user_id, agent_id, created_at DESC);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(oauth_states)").fetchall()
        }
        if "code_verifier" not in cols:
            conn.execute(
                "ALTER TABLE oauth_states ADD COLUMN code_verifier TEXT"
            )
        if "redirect_uri" not in cols:
            conn.execute(
                "ALTER TABLE oauth_states ADD COLUMN redirect_uri TEXT"
            )
        pref_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(user_preferences)").fetchall()
        }
        if "onboarding_skipped_count" not in pref_cols:
            conn.execute(
                "ALTER TABLE user_preferences ADD COLUMN onboarding_skipped_count INTEGER NOT NULL DEFAULT 0"
            )
        if "onboarding_completed_count" not in pref_cols:
            conn.execute(
                "ALTER TABLE user_preferences ADD COLUMN onboarding_completed_count INTEGER NOT NULL DEFAULT 0"
            )


def create_user(user_id: str, email: str, name: str, password_hash: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email.lower(), name, password_hash, _utcnow()),
        )


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()


def get_user_by_id(user_id: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_session(token: str, user_id: str, days: int = 30) -> None:
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires.isoformat()),
        )


def get_session_user(token: str) -> sqlite3.Row | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        expires = conn.execute(
            "SELECT expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if expires and datetime.fromisoformat(expires["expires_at"]) < datetime.now(
            timezone.utc
        ):
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        return row


def delete_session(token: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def save_oauth_state(
    state: str,
    user_id: str,
    code_verifier: str,
    redirect_uri: str,
    minutes: int = 10,
) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO oauth_states (state, user_id, expires_at, code_verifier, redirect_uri)
            VALUES (?, ?, ?, ?, ?)
            """,
            (state, user_id, expires.isoformat(), code_verifier, redirect_uri),
        )


def consume_oauth_state(state: str) -> tuple[str, str, str] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT user_id, expires_at, code_verifier, redirect_uri
            FROM oauth_states WHERE state = ?
            """,
            (state,),
        ).fetchone()
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return None
        code_verifier = row["code_verifier"] or ""
        redirect_uri = row["redirect_uri"] or ""
        return row["user_id"], code_verifier, redirect_uri


def save_gmail_connection(user_id: str, email: str) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO gmail_connections (user_id, email, connected_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET email = excluded.email, connected_at = excluded.connected_at
            """,
            (user_id, email, _utcnow()),
        )


def get_gmail_connection(user_id: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM gmail_connections WHERE user_id = ?", (user_id,)
        ).fetchone()


def clear_gmail_connection(user_id: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM gmail_connections WHERE user_id = ?", (user_id,))


def get_user_preferences(user_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT use_case, onboarding_completed, onboarding_skipped_count, onboarding_completed_count
            FROM user_preferences WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return {
            "use_case": "all",
            "onboarding_completed": False,
            "onboarding_skipped_count": 0,
            "onboarding_completed_count": 0,
        }
    return {
        "use_case": row["use_case"] or "all",
        "onboarding_completed": bool(row["onboarding_completed"]),
        "onboarding_skipped_count": int(row["onboarding_skipped_count"] or 0),
        "onboarding_completed_count": int(row["onboarding_completed_count"] or 0),
    }


def _ensure_preferences_row(conn: sqlite3.Connection, user_id: str) -> dict:
    row = conn.execute(
        "SELECT use_case, onboarding_completed, onboarding_skipped_count, onboarding_completed_count FROM user_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row:
        return {
            "use_case": row["use_case"] or "all",
            "onboarding_completed": bool(row["onboarding_completed"]),
            "onboarding_skipped_count": int(row["onboarding_skipped_count"] or 0),
            "onboarding_completed_count": int(row["onboarding_completed_count"] or 0),
        }
    defaults = {
        "use_case": "all",
        "onboarding_completed": False,
        "onboarding_skipped_count": 0,
        "onboarding_completed_count": 0,
    }
    conn.execute(
        """
        INSERT INTO user_preferences (
            user_id, use_case, onboarding_completed,
            onboarding_skipped_count, onboarding_completed_count, updated_at
        ) VALUES (?, ?, 0, 0, 0, ?)
        """,
        (user_id, defaults["use_case"], _utcnow()),
    )
    return defaults


def record_onboarding_skip(user_id: str) -> dict:
    with get_db() as conn:
        current = _ensure_preferences_row(conn, user_id)
        skipped = current["onboarding_skipped_count"] + 1
        conn.execute(
            """
            UPDATE user_preferences
            SET onboarding_skipped_count = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (skipped, _utcnow(), user_id),
        )
    return get_user_preferences(user_id)


def record_onboarding_complete(user_id: str) -> dict:
    with get_db() as conn:
        current = _ensure_preferences_row(conn, user_id)
        completed_count = current["onboarding_completed_count"] + 1
        conn.execute(
            """
            UPDATE user_preferences
            SET onboarding_completed = 1,
                onboarding_completed_count = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (completed_count, _utcnow(), user_id),
        )
    return get_user_preferences(user_id)


def upsert_user_preferences(
    user_id: str,
    *,
    use_case: str | None = None,
    onboarding_completed: bool | None = None,
) -> dict:
    with get_db() as conn:
        current = _ensure_preferences_row(conn, user_id)
        next_use_case = use_case if use_case is not None else current["use_case"]
        next_completed = (
            onboarding_completed
            if onboarding_completed is not None
            else current["onboarding_completed"]
        )
        conn.execute(
            """
            UPDATE user_preferences
            SET use_case = ?, onboarding_completed = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (next_use_case, int(next_completed), _utcnow(), user_id),
        )
    return get_user_preferences(user_id)


def save_agent_result(
    *,
    result_id: str,
    user_id: str,
    agent_id: str,
    agent_name: str,
    status: str,
    message: str,
    result: dict,
    run_id: str | None,
    created_at: str,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO agent_results
                (id, user_id, agent_id, agent_name, status, message, result_json, run_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                user_id,
                agent_id,
                agent_name,
                status,
                message,
                json.dumps(result, default=str),
                run_id,
                created_at,
            ),
        )


def list_agent_results(
    user_id: str,
    *,
    limit: int = 50,
    agent_id: str | None = None,
) -> list[dict]:
    with get_db() as conn:
        if agent_id:
            rows = conn.execute(
                """
                SELECT id, user_id, agent_id, agent_name, status, message, result_json, run_id, created_at
                FROM agent_results
                WHERE user_id = ? AND agent_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, agent_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, agent_id, agent_name, status, message, result_json, run_id, created_at
                FROM agent_results
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
    return [_row_to_agent_result(row) for row in rows]


def get_agent_result(user_id: str, result_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, agent_id, agent_name, status, message, result_json, run_id, created_at
            FROM agent_results
            WHERE user_id = ? AND id = ?
            """,
            (user_id, result_id),
        ).fetchone()
    return _row_to_agent_result(row) if row else None


def clear_agent_results(user_id: str) -> int:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM agent_results WHERE user_id = ?", (user_id,))
        return cur.rowcount


def _row_to_agent_result(row: sqlite3.Row) -> dict:
    try:
        parsed = json.loads(row["result_json"] or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "agent_id": row["agent_id"],
        "agent_name": row["agent_name"],
        "status": row["status"],
        "message": row["message"],
        "result": parsed,
        "run_id": row["run_id"],
        "created_at": row["created_at"],
    }
