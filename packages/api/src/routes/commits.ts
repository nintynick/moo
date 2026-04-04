import { Router } from "express";
import { randomUUID } from "node:crypto";
import { getDb } from "../db/connection.js";

export const commitRoutes = Router({ mergeParams: true });

// List commits for a repo (optionally filtered by branch)
commitRoutes.get("/", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { branchId, limit = "50" } = req.query;

  let query = "SELECT * FROM commits WHERE repo_id = ?";
  const params: unknown[] = [repoId];

  if (branchId) {
    query += " AND branch_id = ?";
    params.push(branchId);
  }

  query += " ORDER BY created_at DESC LIMIT ?";
  params.push(parseInt(limit as string, 10));

  const commits = db.prepare(query).all(...params);
  res.json(commits);
});

// Get a single commit with its eval results
commitRoutes.get("/:commitId", (req, res) => {
  const db = getDb();
  const commit = db.prepare(
    "SELECT * FROM commits WHERE id = ? AND repo_id = ?"
  ).get(req.params.commitId, req.params.repoId);
  if (!commit) return res.status(404).json({ error: "Commit not found" });

  const evalRuns = db.prepare(`
    SELECT er.*, es.metric, es.value
    FROM eval_runs er
    LEFT JOIN eval_scores es ON es.run_id = er.id
    WHERE er.commit_id = ?
  `).all(req.params.commitId);

  res.json({ commit, evalRuns });
});

// Record a new commit (called by git hooks or the git server)
commitRoutes.post("/", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { branchId, sha, parentSha = null, message, author } = req.body;

  if (!branchId || !sha || !message || !author) {
    return res.status(400).json({
      error: "branchId, sha, message, and author are required",
    });
  }

  // Verify branch exists and belongs to this repo
  const branch = db.prepare(
    "SELECT * FROM branches WHERE id = ? AND repo_id = ?"
  ).get(branchId, repoId);
  if (!branch) {
    return res.status(400).json({ error: "Branch not found in this repo" });
  }

  const id = randomUUID();

  const insertCommit = db.prepare(`
    INSERT INTO commits (id, repo_id, branch_id, sha, parent_sha, message, author)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);

  const updateBranch = db.prepare(
    "UPDATE branches SET head_commit_id = ? WHERE id = ?"
  );

  // Enqueue eval runs for all suites in this repo
  const suites = db.prepare(
    "SELECT * FROM eval_suites WHERE repo_id = ?"
  ).all(repoId) as { id: string }[];

  const insertRun = db.prepare(`
    INSERT INTO eval_runs (id, repo_id, commit_id, suite_id, status)
    VALUES (?, ?, ?, ?, 'queued')
  `);

  const tx = db.transaction(() => {
    insertCommit.run(id, repoId, branchId, sha, parentSha, message, author);
    updateBranch.run(id, branchId);
    for (const suite of suites) {
      insertRun.run(randomUUID(), repoId, id, suite.id);
    }
  });
  tx();

  const commit = db.prepare("SELECT * FROM commits WHERE id = ?").get(id);
  res.status(201).json(commit);
});
