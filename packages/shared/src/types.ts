// ──────────────────────────────────────────────
// Core domain types for GitSpoke
// ──────────────────────────────────────────────

/** A GitSpoke repository — the top-level container. */
export interface Repo {
  id: string;
  name: string;
  owner: string;
  description: string;
  /** The eval configuration lives in the repo itself (gitspoke.eval.yaml). */
  createdAt: string;
  updatedAt: string;
}

/**
 * A branch in the append-only DAG.
 * Branches can fork from any commit on any other branch.
 * There is no "main" — branches are peers competing on evals.
 */
export interface Branch {
  id: string;
  repoId: string;
  name: string;
  /** The commit this branch was forked from (null for the root branch). */
  forkedFromCommitId: string | null;
  /** The latest commit on this branch. */
  headCommitId: string;
  /** Who created this branch — a human username or agent identifier. */
  createdBy: string;
  createdAt: string;
}

/** A commit in the append-only log. */
export interface Commit {
  id: string;
  repoId: string;
  branchId: string;
  /** Git SHA — the content-addressable hash. */
  sha: string;
  parentSha: string | null;
  message: string;
  author: string;
  createdAt: string;
}

/**
 * An eval suite definition. Repos declare these in gitspoke.eval.yaml.
 * Each suite produces one or more metrics.
 */
export interface EvalSuite {
  id: string;
  repoId: string;
  name: string;
  /** The command to run inside the sandbox (e.g. "python run_eval.py"). */
  command: string;
  /** Timeout in seconds. */
  timeout: number;
  /** Docker image to use for the sandbox. */
  image: string;
  /** The metrics this suite reports. */
  metrics: EvalMetricDef[];
  createdAt: string;
  updatedAt: string;
}

/** Definition of a single metric within an eval suite. */
export interface EvalMetricDef {
  name: string;
  /** Higher is better, or lower is better? */
  direction: "maximize" | "minimize";
  /** Optional unit label (e.g. "ms", "accuracy %", "bits/byte"). */
  unit?: string;
}

/** The result of running an eval suite against a specific commit. */
export interface EvalRun {
  id: string;
  repoId: string;
  commitId: string;
  suiteId: string;
  status: EvalRunStatus;
  /** The scores produced by this run. */
  scores: EvalScore[];
  /** Container logs (stdout + stderr). */
  log: string;
  /** Wall-clock duration in milliseconds. */
  durationMs: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
}

export type EvalRunStatus =
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "errored"
  | "timed_out";

/** A single metric value from an eval run. */
export interface EvalScore {
  metric: string;
  value: number;
}

/**
 * A leaderboard entry — one row in the rankings.
 * The leaderboard is a materialized view over eval runs.
 */
export interface LeaderboardEntry {
  rank: number;
  commitId: string;
  commitSha: string;
  branchId: string;
  branchName: string;
  author: string;
  message: string;
  scores: EvalScore[];
  /** Composite score used for ranking (when multiple metrics exist). */
  compositeScore: number;
  evalRunId: string;
  evaluatedAt: string;
}

/**
 * The eval config file that lives in the repo root.
 * Path: gitspoke.eval.yaml
 */
export interface EvalConfig {
  version: 1;
  suites: EvalSuiteConfig[];
}

export interface EvalSuiteConfig {
  name: string;
  command: string;
  image?: string;
  timeout?: number;
  metrics: EvalMetricConfig[];
}

export interface EvalMetricConfig {
  name: string;
  direction: "maximize" | "minimize";
  unit?: string;
}
