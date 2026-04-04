"""SQLite database bootstrap and connection management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_DIR = Path.home() / ".gitspoke"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "gitspoke.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS branches (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    tip_commit_id TEXT,
    created_by  TEXT NOT NULL,
    forked_from_commit TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commits (
    id          TEXT PRIMARY KEY,
    parent_ids  TEXT NOT NULL DEFAULT '[]',
    branch_id   TEXT NOT NULL,
    author      TEXT NOT NULL,
    author_type TEXT NOT NULL DEFAULT 'human',
    message     TEXT NOT NULL DEFAULT '',
    tree_hash   TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id               TEXT PRIMARY KEY,
    commit_id        TEXT NOT NULL,
    manifest_version TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    started_at       TEXT,
    completed_at     TEXT,
    FOREIGN KEY (commit_id) REFERENCES commits(id)
);

CREATE TABLE IF NOT EXISTS scores (
    id                 TEXT PRIMARY KEY,
    commit_id          TEXT NOT NULL,
    eval_version       TEXT NOT NULL,
    metric_name        TEXT NOT NULL,
    value              REAL NOT NULL,
    composite_score    REAL,
    runner_id          TEXT NOT NULL DEFAULT 'local',
    constraints_passed INTEGER NOT NULL DEFAULT 1,
    execution_log_hash TEXT,
    signature          TEXT,
    timestamp          TEXT NOT NULL,
    FOREIGN KEY (commit_id) REFERENCES commits(id)
);

CREATE INDEX IF NOT EXISTS idx_scores_commit ON scores(commit_id);
CREATE INDEX IF NOT EXISTS idx_scores_metric ON scores(metric_name);
CREATE INDEX IF NOT EXISTS idx_commits_branch ON commits(branch_id);
"""


def get_connection(
    db_path: str | Path | None = None,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    if db_path is None:
        DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
        db_path = DEFAULT_DB_PATH
    if str(db_path) != ":memory:":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def bootstrap(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
