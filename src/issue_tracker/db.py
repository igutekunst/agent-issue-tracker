"""Database connection and schema management.

The tracker stores everything in a single SQLite database that lives in a
``.issues/`` directory (git-ignored) at the project root. The project root is
found by walking up from the current directory looking for a ``.git`` folder,
so the CLI works from any subdirectory.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_ENV_VAR = "ISSUE_TRACKER_DB"
DATA_DIRNAME = ".issues"
DB_FILENAME = "tracker.db"


def find_project_root(start: Path | None = None) -> Path:
    """Return the nearest ancestor directory containing a ``.git`` folder.

    Falls back to the current working directory if no git root is found.
    """
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def db_path() -> Path:
    """Resolve the path to the SQLite database file.

    Honors ``ISSUE_TRACKER_DB`` if set, otherwise ``<root>/.issues/tracker.db``.
    """
    override = os.environ.get(DB_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return find_project_root() / DATA_DIRNAME / DB_FILENAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with sensible defaults and ensure the schema exists."""
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _init_schema(conn)
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'open',
    priority    TEXT    NOT NULL DEFAULT 'P2',
    parent_id   INTEGER REFERENCES issues(id) ON DELETE SET NULL,
    branch      TEXT,
    worktree    TEXT,
    assignee    TEXT,
    metadata    TEXT    NOT NULL DEFAULT '{}',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    blocker_id  INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    blocked_id  INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    PRIMARY KEY (blocker_id, blocked_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id    INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    author      TEXT    NOT NULL DEFAULT 'agent',
    body        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_proposals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    key            TEXT    NOT NULL,
    operation      TEXT    NOT NULL,          -- 'set' or 'delete'
    proposed_value TEXT,                      -- NULL for delete
    current_value  TEXT,                      -- snapshot at proposal time
    author         TEXT    NOT NULL DEFAULT 'agent',
    note           TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    created_at     TEXT    NOT NULL,
    resolved_at    TEXT
);

-- A monotonic change feed. Every mutation appends a row here so that the SSE
-- endpoint can push live updates regardless of which process (CLI or web)
-- performed the write.
CREATE TABLE IF NOT EXISTS change_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind    TEXT NOT NULL,     -- e.g. 'issue', 'dependency', 'knowledge', 'proposal'
    action  TEXT NOT NULL,     -- e.g. 'created', 'updated', 'deleted', 'approved'
    ref     TEXT,              -- id or key of the affected entity
    actor   TEXT,              -- who made the change (agent name / 'web'), if known
    ts      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_issues_parent ON issues(parent_id);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON knowledge_proposals(status);
CREATE INDEX IF NOT EXISTS idx_comments_issue ON comments(issue_id);
"""


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Small, idempotent migrations for databases created by older versions."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(change_log)")}
    if "actor" not in cols:
        conn.execute("ALTER TABLE change_log ADD COLUMN actor TEXT")
