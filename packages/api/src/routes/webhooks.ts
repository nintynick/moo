import { Router } from "express";
import { randomUUID } from "node:crypto";
import { getDb } from "../db/connection.js";

export const webhookRoutes = Router();

/**
 * Git post-receive webhook.
 * Called by the git server when a push is received.
 * Records the commit and enqueues eval runs.
 */
webhookRoutes.post("/git/push", (req, res) => {
  const db = getDb();
  const { repoId, branchName, commits } = req.body as {
    repoId: string;
    branchName: string;
    commits: { sha: string; parentSha: string | null; message: string; author: string }[];
  };

  if (!repoId || !branchName || !commits?.length) {
    return res.status(400).json({ error: "repoId, branchName, and commits are required" });
  }

  // Find or verify the branch
  let branch = db.prepare(
    "SELECT * FROM branches WHERE repo_id = ? AND name = ?"
  ).get(repoId, branchName) as { id: string } | undefined;

  if (!branch) {
    // Auto-create the branch (this is how new branches appear)
    const branchId = randomUUID();
    db.prepare(`
      INSERT INTO branches (id, repo_id, name, created_by)
      VALUES (?, ?, ?, ?)
    `).run(branchId, repoId, branchName, commits[0].author);
    branch = { id: branchId };
  }

  const suites = db.prepare(
    "SELECT id FROM eval_suites WHERE repo_id = ?"
  ).all(repoId) as { id: string }[];

  const insertCommit = db.prepare(`
    INSERT OR IGNORE INTO commits (id, repo_id, branch_id, sha, parent_sha, message, author)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);
  const updateHead = db.prepare(
    "UPDATE branches SET head_commit_id = ? WHERE id = ?"
  );
  const insertRun = db.prepare(`
    INSERT INTO eval_runs (id, repo_id, commit_id, suite_id, status)
    VALUES (?, ?, ?, ?, 'queued')
  `);

  const commitIds: string[] = [];

  const tx = db.transaction(() => {
    for (const c of commits) {
      const commitId = randomUUID();
      commitIds.push(commitId);
      insertCommit.run(commitId, repoId, branch!.id, c.sha, c.parentSha, c.message, c.author);
      updateHead.run(commitId, branch!.id);

      // Enqueue evals for each commit
      for (const suite of suites) {
        insertRun.run(randomUUID(), repoId, commitId, suite.id);
      }
    }
  });
  tx();

  res.status(201).json({
    branchId: branch.id,
    commitIds,
    evalsQueued: commitIds.length * suites.length,
  });
});
