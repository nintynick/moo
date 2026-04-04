import Docker from "dockerode";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const docker = new Docker();

export interface SandboxConfig {
  repoPath: string;
  commitSha: string;
  command: string;
  image: string;
  timeoutSec: number;
  resultsFilename: string;
}

export interface SandboxResult {
  exitCode: number;
  log: string;
  scores: { metric: string; value: number }[];
  timedOut: boolean;
}

/**
 * Run an eval command inside a Docker container.
 *
 * The container gets:
 * - The repo mounted read-only at /workspace
 * - A writable /results directory for output
 * - Network disabled (eval can't phone home)
 * - Resource limits (CPU, memory)
 * - A hard timeout
 */
export async function runInSandbox(config: SandboxConfig): Promise<SandboxResult> {
  const {
    repoPath,
    commitSha,
    command,
    image,
    timeoutSec,
    resultsFilename,
  } = config;

  // Create container
  const container = await docker.createContainer({
    Image: image,
    Cmd: ["sh", "-c", `git checkout ${commitSha} --quiet && ${command}`],
    WorkingDir: "/workspace",
    HostConfig: {
      Binds: [`${repoPath}:/workspace:ro`],
      // Writable tmpfs for results
      Tmpfs: { "/results": "rw,size=100m" },
      // Resource limits
      Memory: 2 * 1024 * 1024 * 1024, // 2GB
      NanoCpus: 2_000_000_000, // 2 CPUs
      // No network access
      NetworkMode: "none",
      // Auto-remove on exit
      AutoRemove: false,
    },
    Env: [
      `GITSPOKE_RESULTS_FILE=/results/${resultsFilename}`,
      "GITSPOKE=1",
    ],
  });

  let timedOut = false;
  let log = "";
  let exitCode = 1;
  const scores: { metric: string; value: number }[] = [];

  try {
    await container.start();

    // Set up timeout
    const timeoutPromise = new Promise<"timeout">((resolve) =>
      setTimeout(() => resolve("timeout"), timeoutSec * 1000)
    );

    const waitPromise = container.wait();

    const result = await Promise.race([waitPromise, timeoutPromise]);

    if (result === "timeout") {
      timedOut = true;
      await container.kill().catch(() => {});
    } else {
      exitCode = result.StatusCode;
    }

    // Collect logs
    const logStream = await container.logs({ stdout: true, stderr: true });
    log = logStream.toString("utf-8").slice(0, 1_000_000); // Cap at 1MB

    // Try to read results file from container
    try {
      const archive = await container.getArchive({
        path: `/results/${resultsFilename}`,
      });
      // The archive is a tar stream; for MVP, we use a simpler approach
      // and have the eval script write to stdout in a known format.
      // TODO: properly extract tar archive
      const chunks: Buffer[] = [];
      for await (const chunk of archive as AsyncIterable<Buffer>) {
        chunks.push(chunk);
      }
      const tarContent = Buffer.concat(chunks);
      // Simple extraction: find JSON content after tar header (512 bytes)
      const jsonStart = tarContent.indexOf("{".charCodeAt(0), 512);
      if (jsonStart >= 0) {
        const jsonStr = tarContent.subarray(jsonStart).toString("utf-8").replace(/\0+$/, "");
        const parsed = JSON.parse(jsonStr);
        if (parsed.metrics && typeof parsed.metrics === "object") {
          for (const [metric, value] of Object.entries(parsed.metrics)) {
            if (typeof value === "number") {
              scores.push({ metric, value });
            }
          }
        }
      }
    } catch {
      // Results file not found — eval script might report via stdout instead
      // Try parsing last line of log as JSON
      const lines = log.trim().split("\n");
      const lastLine = lines[lines.length - 1];
      try {
        const parsed = JSON.parse(lastLine);
        if (parsed.metrics && typeof parsed.metrics === "object") {
          for (const [metric, value] of Object.entries(parsed.metrics)) {
            if (typeof value === "number") {
              scores.push({ metric, value });
            }
          }
        }
      } catch {
        // No parseable results
      }
    }
  } finally {
    await container.remove({ force: true }).catch(() => {});
  }

  return { exitCode, log, scores, timedOut };
}
