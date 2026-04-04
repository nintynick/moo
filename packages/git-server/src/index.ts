import express from "express";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Lightweight git HTTP server that wraps git-http-backend.
 * On push, it fires a webhook to the GitSpoke API to record commits
 * and trigger eval runs.
 *
 * For MVP, this uses git's smart HTTP protocol via CGI.
 * For production, consider gitea or a custom pack protocol handler.
 */

const app = express();
const PORT = parseInt(process.env.GIT_SERVER_PORT ?? "3001", 10);
const REPOS_PATH = process.env.GIT_REPOS_PATH ?? "/var/gitspoke/repos";
const API_URL = process.env.GITSPOKE_API_URL ?? "http://localhost:3000";

// Ensure repos directory exists
mkdirSync(REPOS_PATH, { recursive: true });

// Initialize a bare repo for a given repo ID
app.post("/init/:repoId", (req, res) => {
  const repoPath = join(REPOS_PATH, req.params.repoId);
  if (existsSync(repoPath)) {
    return res.json({ status: "already exists" });
  }
  mkdirSync(repoPath, { recursive: true });
  execSync("git init --bare", { cwd: repoPath });

  // Set up post-receive hook to notify the API
  const hookPath = join(repoPath, "hooks", "post-receive");
  const hookScript = `#!/bin/sh
# GitSpoke post-receive hook
# Reads pushed refs and notifies the API

REPO_ID="${req.params.repoId}"
API_URL="${API_URL}"

while read oldrev newrev refname; do
  branch=$(echo "$refname" | sed 's|refs/heads/||')

  # Get commit info
  commits=$(git log --format='{"sha":"%H","parentSha":"%P","message":"%s","author":"%an"}' "$oldrev..$newrev" 2>/dev/null || \
            git log --format='{"sha":"%H","parentSha":"","message":"%s","author":"%an"}' "$newrev" -1)

  # Build JSON array
  json_commits="["
  first=true
  echo "$commits" | while read line; do
    if [ "$first" = true ]; then
      first=false
    else
      json_commits="$json_commits,"
    fi
    json_commits="$json_commits$line"
  done
  json_commits="$json_commits]"

  curl -s -X POST "$API_URL/api/webhooks/git/push" \\
    -H "Content-Type: application/json" \\
    -d "{\\"repoId\\":\\"$REPO_ID\\",\\"branchName\\":\\"$branch\\",\\"commits\\":$json_commits}" || true
done
`;
  require("node:fs").writeFileSync(hookPath, hookScript, { mode: 0o755 });

  res.status(201).json({ status: "initialized", path: repoPath });
});

// Health check
app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "gitspoke-git-server" });
});

app.listen(PORT, () => {
  console.log(`GitSpoke Git Server listening on http://localhost:${PORT}`);
  console.log(`  Repos path: ${REPOS_PATH}`);
});
