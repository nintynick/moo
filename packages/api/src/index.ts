import express from "express";
import cors from "cors";
import { repoRoutes } from "./routes/repos.js";
import { branchRoutes } from "./routes/branches.js";
import { commitRoutes } from "./routes/commits.js";
import { evalRoutes } from "./routes/evals.js";
import { leaderboardRoutes } from "./routes/leaderboard.js";
import { webhookRoutes } from "./routes/webhooks.js";

const app = express();
const PORT = parseInt(process.env.PORT ?? "3000", 10);

app.use(cors());
app.use(express.json());

// Health check
app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "gitspoke-api" });
});

// API routes
app.use("/api/repos", repoRoutes);
app.use("/api/repos/:repoId/branches", branchRoutes);
app.use("/api/repos/:repoId/commits", commitRoutes);
app.use("/api/repos/:repoId/evals", evalRoutes);
app.use("/api/repos/:repoId/leaderboard", leaderboardRoutes);
app.use("/api/webhooks", webhookRoutes);

app.listen(PORT, () => {
  console.log(`GitSpoke API listening on http://localhost:${PORT}`);
});

export default app;
