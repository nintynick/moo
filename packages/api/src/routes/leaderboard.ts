import { Router } from "express";
import { getDb } from "../db/connection.js";

export const leaderboardRoutes = Router({ mergeParams: true });

// Get leaderboard for a repo, ranked by a specific metric
leaderboardRoutes.get("/", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { metric, suite, limit = "100" } = req.query;

  if (!metric) {
    return res.status(400).json({ error: "metric query param is required" });
  }

  // Determine sort direction from metric definition
  const metricDef = db.prepare(`
    SELECT emd.direction FROM eval_metric_defs emd
    JOIN eval_suites es ON es.id = emd.suite_id
    WHERE es.repo_id = ? AND emd.name = ?
    LIMIT 1
  `).get(repoId, metric) as { direction: string } | undefined;

  const direction = metricDef?.direction === "minimize" ? "ASC" : "DESC";

  let query = `
    SELECT
      l.commit_id,
      l.commit_sha,
      l.commit_message,
      l.author,
      l.branch_id,
      l.branch_name,
      l.eval_run_id,
      l.score,
      l.evaluated_at
    FROM leaderboard l
    JOIN eval_suites es ON es.id = l.suite_id
    WHERE es.repo_id = ?
      AND l.metric = ?
  `;
  const params: unknown[] = [repoId, metric];

  if (suite) {
    query += " AND es.name = ?";
    params.push(suite);
  }

  // Best score per commit (dedup if a commit was eval'd multiple times)
  query = `
    SELECT * FROM (${query}) sub
    GROUP BY sub.commit_id
    ORDER BY sub.score ${direction}
    LIMIT ?
  `;
  params.push(parseInt(limit as string, 10));

  const entries = db.prepare(query).all(...params);

  // Add rank numbers
  const ranked = (entries as Record<string, unknown>[]).map((entry, i) => ({
    rank: i + 1,
    ...entry,
  }));

  res.json({
    metric,
    direction: metricDef?.direction ?? "maximize",
    entries: ranked,
  });
});

// Get the Pareto frontier across two metrics
leaderboardRoutes.get("/pareto", (req, res) => {
  const db = getDb();
  const { repoId } = req.params;
  const { metricX, metricY } = req.query;

  if (!metricX || !metricY) {
    return res.status(400).json({ error: "metricX and metricY are required" });
  }

  // Get all commits with both metrics
  const points = db.prepare(`
    SELECT
      c.id AS commit_id,
      c.sha AS commit_sha,
      c.author,
      b.name AS branch_name,
      sx.value AS x,
      sy.value AS y
    FROM commits c
    JOIN branches b ON b.id = c.branch_id
    JOIN eval_runs erx ON erx.commit_id = c.id AND erx.status = 'passed'
    JOIN eval_scores sx ON sx.run_id = erx.id AND sx.metric = ?
    JOIN eval_runs ery ON ery.commit_id = c.id AND ery.status = 'passed'
    JOIN eval_scores sy ON sy.run_id = ery.id AND sy.metric = ?
    WHERE c.repo_id = ?
  `).all(metricX, metricY, repoId);

  res.json({ metricX, metricY, points });
});
