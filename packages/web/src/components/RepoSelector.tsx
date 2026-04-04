import React from "react";

interface Repo {
  id: string;
  name: string;
  owner: string;
  description: string;
}

interface Props {
  repos: Repo[];
  selected: Repo | null;
  onSelect: (repo: Repo) => void;
}

export function RepoSelector({ repos, selected, onSelect }: Props) {
  if (repos.length === 0) {
    return (
      <div style={{ padding: 20, background: "#f9f9f9", borderRadius: 8, textAlign: "center" }}>
        <p>No repositories yet. Create one via the API:</p>
        <pre style={{ background: "#eee", padding: 12, borderRadius: 4, textAlign: "left", display: "inline-block" }}>
{`curl -X POST http://localhost:3000/api/repos \\
  -H "Content-Type: application/json" \\
  -d '{"name": "my-project", "owner": "alice"}'`}
        </pre>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {repos.map((repo) => (
        <button
          key={repo.id}
          onClick={() => onSelect(repo)}
          style={{
            padding: "8px 16px",
            background: selected?.id === repo.id ? "#0066ff" : "#f0f0f0",
            color: selected?.id === repo.id ? "#fff" : "#333",
            border: "1px solid #ddd",
            borderRadius: 6,
            cursor: "pointer",
          }}
        >
          {repo.owner}/{repo.name}
        </button>
      ))}
    </div>
  );
}
