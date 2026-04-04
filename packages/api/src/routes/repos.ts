import { Router } from "express";
import { randomUUID } from "node:crypto";
import { getDb } from "../db/connection.js";

export const repoRoutes = Router();

// List all repos
repoRoutes.get("/", (_req, res) => {
  const db = getDb();
  const repos = db.prepare("SELECT * FROM repos ORDER BY created_at DESC").all();
  res.json(repos);
});

// Get a single repo
repoRoutes.get("/:repoId", (req, res) => {
  const db = getDb();
  const repo = db.prepare("SELECT * FROM repos WHERE id = ?").get(req.params.repoId);
  if (!repo) return res.status(404).json({ error: "Repo not found" });
  res.json(repo);
});

// Create a repo
repoRoutes.post("/", (req, res) => {
  const db = getDb();
  const { name, owner, description = "" } = req.body;
  if (!name || !owner) {
    return res.status(400).json({ error: "name and owner are required" });
  }
  const id = randomUUID();
  db.prepare(
    "INSERT INTO repos (id, name, owner, description) VALUES (?, ?, ?, ?)"
  ).run(id, name, owner, description);

  const repo = db.prepare("SELECT * FROM repos WHERE id = ?").get(id);
  res.status(201).json(repo);
});
