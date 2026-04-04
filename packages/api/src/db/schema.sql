-- GitSpoke Database Schema
-- Append-only branch graph with eval-driven leaderboard

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─── Repositories ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS repos (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  owner       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(owner, name)
);

-- ─── Branches ───────────────────────────────────────────
-- No concept of "main". Branches are peers in a DAG.
-- Each branch is append-only: you can only add commits, never rewrite.

CREATE TABLE IF NOT EXISTS branches (
  id                    TEXT PRIMARY KEY,
  repo_id               TEXT NOT NULL REFERENCES repos(id),
  name                  TEXT NOT NULL,
  forked_from_commit_id TEXT REFERENCES commits(id),
  head_commit_id        TEXT REFERENCES commits(id),
  created_by            TEXT NOT NULL,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(repo_id, name)
);

-- ─── Commits ────────────────────────────────────────────
-- Append-only log. Once written, never modified.

CREATE TABLE IF NOT EXISTS commits (
  id          TEXT PRIMARY KEY,
  repo_id     TEXT NOT NULL REFERENCES repos(id),
  branch_id   TEXT NOT NULL REFERENCES branches(id),
  sha         TEXT NOT NULL,
  parent_sha  TEXT,
  message     TEXT NOT NULL,
  author      TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(repo_id, sha)
);

-- ─── Eval Suites ────────────────────────────────────────
-- Defined by the repo's gitspoke.eval.yaml config file.

CREATE TABLE IF NOT EXISTS eval_suites (
  id          TEXT PRIMARY KEY,
  repo_id     TEXT NOT NULL REFERENCES repos(id),
  name        TEXT NOT NULL,
  command     TEXT NOT NULL,
  timeout_sec INTEGER NOT NULL DEFAULT 300,
  image       TEXT NOT NULL DEFAULT 'gitspoke-eval-sandbox:latest',
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(repo_id, name)
);

-- ─── Eval Metric Definitions ────────────────────────────

CREATE TABLE IF NOT EXISTS eval_metric_defs (
  id          TEXT PRIMARY KEY,
  suite_id    TEXT NOT NULL REFERENCES eval_suites(id),
  name        TEXT NOT NULL,
  direction   TEXT NOT NULL CHECK (direction IN ('maximize', 'minimize')),
  unit        TEXT,
  UNIQUE(suite_id, name)
);

-- ─── Eval Runs ──────────────────────────────────────────
-- Every commit triggers an eval run for each suite.

CREATE TABLE IF NOT EXISTS eval_runs (
  id          TEXT PRIMARY KEY,
  repo_id     TEXT NOT NULL REFERENCES repos(id),
  commit_id   TEXT NOT NULL REFERENCES commits(id),
  suite_id    TEXT NOT NULL REFERENCES eval_suites(id),
  status      TEXT NOT NULL DEFAULT 'queued'
              CHECK (status IN ('queued', 'running', 'passed', 'failed', 'errored', 'timed_out')),
  log         TEXT NOT NULL DEFAULT '',
  duration_ms INTEGER,
  started_at  TEXT,
  finished_at TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(commit_id, suite_id)
);

-- ─── Eval Scores ────────────────────────────────────────
-- The actual metric values produced by each eval run.

CREATE TABLE IF NOT EXISTS eval_scores (
  id          TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES eval_runs(id),
  metric      TEXT NOT NULL,
  value       REAL NOT NULL,
  UNIQUE(run_id, metric)
);

-- ─── Indexes ────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_branches_repo ON branches(repo_id);
CREATE INDEX IF NOT EXISTS idx_commits_branch ON commits(branch_id);
CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_commit ON eval_runs(commit_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_status ON eval_runs(status);
CREATE INDEX IF NOT EXISTS idx_eval_scores_run ON eval_scores(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_scores_value ON eval_scores(metric, value);

-- ─── Leaderboard View ───────────────────────────────────
-- Materialized as a view; for production, consider a materialized table
-- refreshed on eval completion.

CREATE VIEW IF NOT EXISTS leaderboard AS
SELECT
  c.id          AS commit_id,
  c.sha         AS commit_sha,
  c.message     AS commit_message,
  c.author      AS author,
  b.id          AS branch_id,
  b.name        AS branch_name,
  er.id         AS eval_run_id,
  er.suite_id   AS suite_id,
  es.metric     AS metric,
  es.value      AS score,
  emd.direction AS direction,
  er.finished_at AS evaluated_at
FROM eval_scores es
JOIN eval_runs er ON er.id = es.run_id
JOIN commits c ON c.id = er.commit_id
JOIN branches b ON b.id = c.branch_id
JOIN eval_metric_defs emd ON emd.suite_id = er.suite_id AND emd.name = es.metric
WHERE er.status = 'passed';
