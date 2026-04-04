import { Router } from "express";
import { randomUUID } from "node:crypto";
import { getDb } from "../db/connection.js";

export const evalRoutes = Router({ mergeParams: true });

// List eval suites for a repo
evalRoutes.get("/suites", (req, res) => {
  const db = getDb();
  const suites = db.prepare(`
    SELECT es.*, GROUP_CONCAT(emd.name || ':' || emd.direction, ',') AS metrics_summary
    FROM eval_suites es
    LEFT JOIN eval_metric_defs emd ON emd.suite_id = es.id
    WHERE es.repo_id = ?
    GROUP BY es.id
  `).all(req.params.repoId);
  res.json(suites);
});

// Create an eval suite
evalRoutes.post("/suites", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { name, command, timeout = 300, image = "gitspoke-eval-sandbox:latest", metrics = [] } = req.body;

  if (!name || !command) {
    return res.status(400).json({ error: "name and command are required" });
  }

  const suiteId = randomUUID();

  const tx = db.transaction(() => {
    db.prepare(`
      INSERT INTO eval_suites (id, repo_id, name, command, timeout_sec, image)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(suiteId, repoId, name, command, timeout, image);

    for (const metric of metrics as { name: string; direction: string; unit?: string }[]) {
      db.prepare(`
        INSERT INTO eval_metric_defs (id, suite_id, name, direction, unit)
        VALUES (?, ?, ?, ?, ?)
      `).run(randomUUID(), suiteId, metric.name, metric.direction, metric.unit ?? null);
    }
  });
  tx();

  const suite = db.prepare("SELECT * FROM eval_suites WHERE id = ?").get(suiteId);
  res.status(201).json(suite);
});

// List eval runs (optionally filtered by status)
evalRoutes.get("/runs", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { status, limit = "50" } = req.query;

  let query = "SELECT * FROM eval_runs WHERE repo_id = ?";
  const params: unknown[] = [repoId];

  if (status) {
    query += " AND status = ?";
    params.push(status);
  }

  query += " ORDER BY created_at DESC LIMIT ?";
  params.push(parseInt(limit as string, 10));

  const runs = db.prepare(query).all(...params);
  res.json(runs);
});

// Get a specific eval run with scores
evalRoutes.get("/runs/:runId", (req, res) => {
  const db = getDb();
  const run = db.prepare(
    "SELECT * FROM eval_runs WHERE id = ? AND repo_id = ?"
  ).get(req.params.runId, req.params.repoId);
  if (!run) return res.status(404).json({ error: "Eval run not found" });

  const scores = db.prepare(
    "SELECT metric, value FROM eval_scores WHERE run_id = ?"
  ).all(req.params.runId);

  res.json({ ...run as object, scores });
});

// Report eval results (called by the eval runner)
evalRoutes.post("/runs/:runId/results", (req, res) => {
  const db = getDb();
  const { runId } = req.params;
  const { status, scores = [], log = "", durationMs } = req.body;

  if (!status) {
    return res.status(400).json({ error: "status is required" });
  }

  const tx = db.transaction(() => {
    db.prepare(`
      UPDATE eval_runs
      SET status = ?, log = ?, duration_ms = ?, finished_at = datetime('now')
      WHERE id = ?
    `).run(status, log, durationMs, runId);

    for (const score of scores as { metric: string; value: number }[]) {
      db.prepare(`
        INSERT INTO eval_scores (id, run_id, metric, value)
        VALUES (?, ?, ?, ?)
      `).run(randomUUID(), runId, score.metric, score.value);
    }
  });
  tx();

  const run = db.prepare("SELECT * FROM eval_runs WHERE id = ?").get(runId);
  res.json(run);
});
