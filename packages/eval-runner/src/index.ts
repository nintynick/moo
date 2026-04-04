import { EvalWorker } from "./worker.js";

const API_URL = process.env.GITSPOKE_API_URL ?? "http://localhost:3000";
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL_MS ?? "5000", 10);
const MAX_CONCURRENT = parseInt(process.env.MAX_CONCURRENT ?? "2", 10);
const GIT_REPOS_PATH = process.env.GIT_REPOS_PATH ?? "/var/gitspoke/repos";

const worker = new EvalWorker({
  apiUrl: API_URL,
  pollIntervalMs: POLL_INTERVAL_MS,
  maxConcurrent: MAX_CONCURRENT,
  gitReposPath: GIT_REPOS_PATH,
});

console.log("GitSpoke Eval Runner starting...");
console.log(`  API: ${API_URL}`);
console.log(`  Poll interval: ${POLL_INTERVAL_MS}ms`);
console.log(`  Max concurrent: ${MAX_CONCURRENT}`);

worker.start();

process.on("SIGINT", () => {
  console.log("Shutting down eval runner...");
  worker.stop();
  process.exit(0);
});
