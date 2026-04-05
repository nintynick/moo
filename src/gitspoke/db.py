"""SQLite database bootstrap and connection management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_DIR = Path.home() / ".gitspoke"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "gitspoke.db"

SCHEMA = """
-- ── Repositories ──
CREATE TABLE IF NOT EXISTS repositories (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    owner_id    TEXT NOT NULL,
    manifest_version TEXT,
    created_at  TEXT NOT NULL
);

-- ── Identities ──
CREATE TABLE IF NOT EXISTS identities (
    id              TEXT PRIMARY KEY,
    display_name    TEXT UNIQUE NOT NULL,
    identity_type   TEXT NOT NULL DEFAULT 'human',
    public_key      TEXT,
    organization    TEXT,
    agent_model     TEXT,
    agent_version   TEXT,
    reputation_score REAL NOT NULL DEFAULT 0.0,
    trust_score     REAL NOT NULL DEFAULT 1.0,
    total_commits   INTEGER NOT NULL DEFAULT 0,
    leaderboard_positions INTEGER NOT NULL DEFAULT 0,
    upstream_credits REAL NOT NULL DEFAULT 0.0,
    verification_match_rate REAL NOT NULL DEFAULT 1.0,
    created_at      TEXT NOT NULL
);

-- ── Branches ──
CREATE TABLE IF NOT EXISTS branches (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    tip_commit_id TEXT,
    created_by  TEXT NOT NULL,
    forked_from_commit TEXT,
    repo_id     TEXT NOT NULL DEFAULT 'default',
    created_at  TEXT NOT NULL,
    UNIQUE(name, repo_id)
);

-- ── Lineage Groups ──
CREATE TABLE IF NOT EXISTS lineage_groups (
    id              TEXT PRIMARY KEY,
    repo_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    root_commit_ids TEXT NOT NULL DEFAULT '[]',
    auto_detected   INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    UNIQUE(name, repo_id)
);

-- ── Commits ──
CREATE TABLE IF NOT EXISTS commits (
    id          TEXT PRIMARY KEY,
    parent_ids  TEXT NOT NULL DEFAULT '[]',
    branch_id   TEXT NOT NULL,
    author      TEXT NOT NULL,
    author_type TEXT NOT NULL DEFAULT 'human',
    message     TEXT NOT NULL DEFAULT '',
    tree_hash   TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    repo_id     TEXT NOT NULL DEFAULT 'default',
    lineage_group_id TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);

-- ── Eval Runs ──
CREATE TABLE IF NOT EXISTS eval_runs (
    id               TEXT PRIMARY KEY,
    commit_id        TEXT NOT NULL,
    manifest_version TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    runner_id        TEXT,
    started_at       TEXT,
    completed_at     TEXT,
    FOREIGN KEY (commit_id) REFERENCES commits(id)
);

-- ── Scores ──
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
    verified           INTEGER NOT NULL DEFAULT 0,
    timestamp          TEXT NOT NULL,
    FOREIGN KEY (commit_id) REFERENCES commits(id)
);

-- ── Runners (BYOC) ──
CREATE TABLE IF NOT EXISTS runners (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    owner_id        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'offline',
    gpu_type        TEXT,
    gpu_memory      TEXT,
    cpu_cores       INTEGER,
    memory          TEXT,
    public_key      TEXT,
    trusted         INTEGER NOT NULL DEFAULT 0,
    last_heartbeat  TEXT,
    jobs_completed  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

-- ── Challenges ──
CREATE TABLE IF NOT EXISTS challenges (
    id                  TEXT PRIMARY KEY,
    score_id            TEXT NOT NULL,
    commit_id           TEXT NOT NULL,
    challenger_id       TEXT NOT NULL,
    reason              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'open',
    verification_score  REAL,
    original_score      REAL,
    resolved_at         TEXT,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (score_id) REFERENCES scores(id),
    FOREIGN KEY (commit_id) REFERENCES commits(id)
);

-- ── Webhooks ──
CREATE TABLE IF NOT EXISTS webhooks (
    id          TEXT PRIMARY KEY,
    repo_id     TEXT NOT NULL,
    url         TEXT NOT NULL,
    events      TEXT NOT NULL DEFAULT '[]',
    secret      TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- ── Events ──
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    repo_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);

-- ── Indexes ──
CREATE INDEX IF NOT EXISTS idx_scores_commit ON scores(commit_id);
CREATE INDEX IF NOT EXISTS idx_scores_metric ON scores(metric_name);
CREATE INDEX IF NOT EXISTS idx_commits_branch ON commits(branch_id);
CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo_id);
CREATE INDEX IF NOT EXISTS idx_branches_repo ON branches(repo_id);
CREATE INDEX IF NOT EXISTS idx_events_repo ON events(repo_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_runners_owner ON runners(owner_id);
CREATE INDEX IF NOT EXISTS idx_challenges_commit ON challenges(commit_id);
CREATE INDEX IF NOT EXISTS idx_lineage_groups_repo ON lineage_groups(repo_id);
CREATE INDEX IF NOT EXISTS idx_commits_lineage ON commits(lineage_group_id);
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
