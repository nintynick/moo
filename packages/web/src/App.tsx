import React, { useEffect, useState } from "react";
import { Leaderboard } from "./components/Leaderboard.js";
import { BranchGraph } from "./components/BranchGraph.js";
import { RepoSelector } from "./components/RepoSelector.js";

interface Repo {
  id: string;
  name: string;
  owner: string;
  description: string;
}

export function App() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null);
  const [view, setView] = useState<"leaderboard" | "graph">("leaderboard");

  useEffect(() => {
    fetch("/api/repos")
      .then((r) => r.json())
      .then(setRepos)
      .catch(console.error);
  }, []);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 1200, margin: "0 auto", padding: 20 }}>
      <header style={{ marginBottom: 32, borderBottom: "2px solid #333", paddingBottom: 16 }}>
        <h1 style={{ margin: 0, fontSize: 28 }}>
          GitSpoke
        </h1>
        <p style={{ margin: "4px 0 0", color: "#666" }}>
          Eval-driven code evolution. No main branch. Commits compete on a leaderboard.
        </p>
      </header>

      <RepoSelector repos={repos} selected={selectedRepo} onSelect={setSelectedRepo} />

      {selectedRepo && (
        <>
          <nav style={{ margin: "16px 0", display: "flex", gap: 8 }}>
            <button
              onClick={() => setView("leaderboard")}
              style={{
                padding: "8px 16px",
                background: view === "leaderboard" ? "#333" : "#eee",
                color: view === "leaderboard" ? "#fff" : "#333",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              Leaderboard
            </button>
            <button
              onClick={() => setView("graph")}
              style={{
                padding: "8px 16px",
                background: view === "graph" ? "#333" : "#eee",
                color: view === "graph" ? "#fff" : "#333",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              Branch Graph
            </button>
          </nav>

          {view === "leaderboard" ? (
            <Leaderboard repoId={selectedRepo.id} />
          ) : (
            <BranchGraph repoId={selectedRepo.id} />
          )}
        </>
      )}
    </div>
  );
}
