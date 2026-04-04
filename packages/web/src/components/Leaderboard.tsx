import React, { useEffect, useState } from "react";

interface LeaderboardEntry {
  rank: number;
  commit_sha: string;
  commit_message: string;
  author: string;
  branch_name: string;
  score: number;
  evaluated_at: string;
}

interface LeaderboardData {
  metric: string;
  direction: string;
  entries: LeaderboardEntry[];
}

interface MetricInfo {
  name: string;
  direction: string;
}

interface Props {
  repoId: string;
}

export function Leaderboard({ repoId }: Props) {
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [metrics, setMetrics] = useState<MetricInfo[]>([]);
  const [selectedMetric, setSelectedMetric] = useState<string>("");

  // Fetch available metrics
  useEffect(() => {
    fetch(`/api/repos/${repoId}/evals/suites`)
      .then((r) => r.json())
      .then((suites: { metrics_summary: string }[]) => {
        const allMetrics: MetricInfo[] = [];
        for (const suite of suites) {
          if (suite.metrics_summary) {
            for (const entry of suite.metrics_summary.split(",")) {
              const [name, direction] = entry.split(":");
              allMetrics.push({ name, direction });
            }
          }
        }
        setMetrics(allMetrics);
        if (allMetrics.length > 0 && !selectedMetric) {
          setSelectedMetric(allMetrics[0].name);
        }
      })
      .catch(console.error);
  }, [repoId]);

  // Fetch leaderboard
  useEffect(() => {
    if (!selectedMetric) return;
    fetch(`/api/repos/${repoId}/leaderboard?metric=${encodeURIComponent(selectedMetric)}`)
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, [repoId, selectedMetric]);

  if (!metrics.length) {
    return (
      <div style={{ padding: 20, background: "#f9f9f9", borderRadius: 8, textAlign: "center" }}>
        No eval suites configured yet. Define evals via the API or add a <code>gitspoke.eval.yaml</code> to your repo.
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", gap: 8, alignItems: "center" }}>
        <label>Metric:</label>
        <select
          value={selectedMetric}
          onChange={(e) => setSelectedMetric(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 4, border: "1px solid #ccc" }}
        >
          {metrics.map((m) => (
            <option key={m.name} value={m.name}>
              {m.name} ({m.direction})
            </option>
          ))}
        </select>
      </div>

      {data && data.entries.length > 0 ? (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #333", textAlign: "left" }}>
              <th style={{ padding: 8 }}>#</th>
              <th style={{ padding: 8 }}>Score</th>
              <th style={{ padding: 8 }}>Branch</th>
              <th style={{ padding: 8 }}>Commit</th>
              <th style={{ padding: 8 }}>Author</th>
              <th style={{ padding: 8 }}>Message</th>
              <th style={{ padding: 8 }}>When</th>
            </tr>
          </thead>
          <tbody>
            {data.entries.map((entry) => (
              <tr key={entry.commit_sha} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: 8, fontWeight: entry.rank <= 3 ? "bold" : "normal" }}>
                  {entry.rank <= 3 ? ["", "1st", "2nd", "3rd"][entry.rank] : entry.rank}
                </td>
                <td style={{ padding: 8, fontFamily: "monospace", fontWeight: "bold" }}>
                  {typeof entry.score === "number" ? entry.score.toFixed(4) : entry.score}
                </td>
                <td style={{ padding: 8 }}>
                  <span style={{
                    background: "#e8f0fe",
                    padding: "2px 8px",
                    borderRadius: 12,
                    fontSize: 13,
                  }}>
                    {entry.branch_name}
                  </span>
                </td>
                <td style={{ padding: 8, fontFamily: "monospace", fontSize: 13 }}>
                  {entry.commit_sha?.slice(0, 8)}
                </td>
                <td style={{ padding: 8 }}>{entry.author}</td>
                <td style={{ padding: 8, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {entry.commit_message}
                </td>
                <td style={{ padding: 8, fontSize: 13, color: "#666" }}>
                  {entry.evaluated_at ? new Date(entry.evaluated_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ padding: 20, textAlign: "center", color: "#666" }}>
          No eval results yet. Push commits to trigger evals.
        </div>
      )}
    </div>
  );
}
