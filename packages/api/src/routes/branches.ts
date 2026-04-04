import { Router } from "express";
import { randomUUID } from "node:crypto";
import { getDb } from "../db/connection.js";

export const branchRoutes = Router({ mergeParams: true });

// List branches for a repo, with optional sorting by best eval score
branchRoutes.get("/", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;

  const branches = db.prepare(`
    SELECT b.*,
      (SELECT COUNT(*) FROM commits c WHERE c.branch_id = b.id) AS commit_count
    FROM branches b
    WHERE b.repo_id = ?
    ORDER BY b.created_at DESC
  `).all(repoId);

  res.json(branches);
});

// Get a single branch
branchRoutes.get("/:branchId", (req, res) => {
  const db = getDb();
  const branch = db.prepare(
    "SELECT * FROM branches WHERE id = ? AND repo_id = ?"
  ).get(req.params.branchId, req.params.repoId);
  if (!branch) return res.status(404).json({ error: "Branch not found" });
  res.json(branch);
});

// Create a branch (fork from any commit)
branchRoutes.post("/", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { name, forkedFromCommitId = null, createdBy } = req.body;

  if (!name || !createdBy) {
    return res.status(400).json({ error: "name and createdBy are required" });
  }

  // Verify the fork point exists if specified
  if (forkedFromCommitId) {
    const commit = db.prepare(
      "SELECT id FROM commits WHERE id = ? AND repo_id = ?"
    ).get(forkedFromCommitId, repoId);
    if (!commit) {
      return res.status(400).json({ error: "Fork point commit not found" });
    }
  }

  const id = randomUUID();
  db.prepare(`
    INSERT INTO branches (id, repo_id, name, forked_from_commit_id, head_commit_id, created_by)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(id, repoId, name, forkedFromCommitId, forkedFromCommitId, createdBy);

  const branch = db.prepare("SELECT * FROM branches WHERE id = ?").get(id);
  res.status(201).json(branch);
});

// Get branch lineage (the DAG path back to root)
branchRoutes.get("/:branchId/lineage", (req, res) => {
  const db = getDb();
  const { branchId, repoId } = req.params;

  const lineage: unknown[] = [];
  let currentBranch = db.prepare(
    "SELECT * FROM branches WHERE id = ? AND repo_id = ?"
  ).get(branchId, repoId) as { forked_from_commit_id: string | null } | undefined;

  while (currentBranch) {
    lineage.push(currentBranch);
    if (!currentBranch.forked_from_commit_id) break;
    const parentCommit = db.prepare(
      "SELECT branch_id FROM commits WHERE id = ?"
    ).get(currentBranch.forked_from_commit_id) as { branch_id: string } | undefined;
    if (!parentCommit) break;
    currentBranch = db.prepare(
      "SELECT * FROM branches WHERE id = ?"
    ).get(parentCommit.branch_id) as { forked_from_commit_id: string | null } | undefined;
  }

  res.json(lineage);
});
