import { EVAL_RESULTS_FILENAME } from "@gitspoke/shared";
import { runInSandbox } from "./sandbox.js";

interface WorkerConfig {
  apiUrl: string;
  pollIntervalMs: number;
  maxConcurrent: number;
  gitReposPath: string;
}

interface QueuedRun {
  id: string;
  repo_id: string;
  commit_id: string;
  suite_id: string;
}

interface EvalSuite {
  id: string;
  command: string;
  timeout_sec: number;
  image: string;
}

interface CommitInfo {
  commit: { sha: string; repo_id: string };
}

export class EvalWorker {
  private config: WorkerConfig;
  private running = false;
  private activeRuns = 0;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(config: WorkerConfig) {
    this.config = config;
  }

  start(): void {
    this.running = true;
    this.timer = setInterval(() => this.poll(), this.config.pollIntervalMs);
    this.poll(); // Immediate first poll
  }

  stop(): void {
    this.running = false;
    if (this.timer) clearInterval(this.timer);
  }

  private async poll(): Promise<void> {
    if (!this.running) return;
    if (this.activeRuns >= this.config.maxConcurrent) return;

    try {
      // Fetch queued runs from API
      const response = await fetch(
        `${this.config.apiUrl}/api/repos/_all/evals/runs?status=queued&limit=${this.config.maxConcurrent - this.activeRuns}`
      );

      // The API might not support _all yet; we'll poll per-repo in production.
      // For now, use a dedicated endpoint or scan repos.
      if (!response.ok) return;

      const runs = (await response.json()) as QueuedRun[];
      for (const run of runs) {
        if (this.activeRuns >= this.config.maxConcurrent) break;
        this.executeRun(run);
      }
    } catch {
      // API not available yet, that's fine during dev
    }
  }

  private async executeRun(run: QueuedRun): Promise<void> {
    this.activeRuns++;
    const startTime = Date.now();

    try {
      // Mark as running
      await fetch(
        `${this.config.apiUrl}/api/repos/${run.repo_id}/evals/runs/${run.id}/results`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "running" }),
        }
      );

      // Get suite config
      const suiteRes = await fetch(
        `${this.config.apiUrl}/api/repos/${run.repo_id}/evals/suites`
      );
      const suites = (await suiteRes.json()) as EvalSuite[];
      const suite = suites.find((s) => s.id === run.suite_id);
      if (!suite) throw new Error(`Suite ${run.suite_id} not found`);

      // Get commit SHA to checkout
      const commitRes = await fetch(
        `${this.config.apiUrl}/api/repos/${run.repo_id}/commits/${run.commit_id}`
      );
      const { commit } = (await commitRes.json()) as CommitInfo;

      // Run in sandbox
      const result = await runInSandbox({
        repoPath: `${this.config.gitReposPath}/${run.repo_id}`,
        commitSha: commit.sha,
        command: suite.command,
        image: suite.image,
        timeoutSec: suite.timeout_sec,
        resultsFilename: EVAL_RESULTS_FILENAME,
      });

      const durationMs = Date.now() - startTime;

      // Report results
      await fetch(
        `${this.config.apiUrl}/api/repos/${run.repo_id}/evals/runs/${run.id}/results`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: result.timedOut ? "timed_out" : result.exitCode === 0 ? "passed" : "failed",
            scores: result.scores,
            log: result.log,
            durationMs,
          }),
        }
      );
    } catch (err) {
      const durationMs = Date.now() - startTime;
      await fetch(
        `${this.config.apiUrl}/api/repos/${run.repo_id}/evals/runs/${run.id}/results`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: "errored",
            log: String(err),
            durationMs,
            scores: [],
          }),
        }
      ).catch(() => {});
    } finally {
      this.activeRuns--;
    }
  }
}
