import React, { useEffect, useState } from "react";

interface Branch {
  id: string;
  name: string;
  forked_from_commit_id: string | null;
  head_commit_id: string;
  created_by: string;
  created_at: string;
  commit_count: number;
}

interface Props {
  repoId: string;
}

/**
 * A simple text-based branch DAG visualization.
 * TODO: Replace with a proper SVG/Canvas graph renderer.
 */
export function BranchGraph({ repoId }: Props) {
  const [branches, setBranches] = useState<Branch[]>([]);

  useEffect(() => {
    fetch(`/api/repos/${repoId}/branches`)
      .then((r) => r.json())
      .then(setBranches)
      .catch(console.error);
  }, [repoId]);

  if (branches.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: "center", color: "#666" }}>
        No branches yet. Push to any branch to get started.
      </div>
    );
  }

  // Build a simple parent-child map
  const branchMap = new Map(branches.map((b) => [b.id, b]));

  // Color palette for branches
  const colors = [
    "#0066ff", "#e63946", "#2a9d8f", "#e9c46a", "#f4a261",
    "#264653", "#a855f7", "#06b6d4", "#84cc16", "#f43f5e",
  ];

  return (
    <div>
      <div style={{ display: "grid", gap: 12 }}>
        {branches.map((branch, i) => (
          <div
            key={branch.id}
            style={{
              border: `2px solid ${colors[i % colors.length]}`,
              borderRadius: 8,
              padding: 16,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <div style={{ fontWeight: "bold", fontSize: 16 }}>
                <span style={{
                  display: "inline-block",
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: colors[i % colors.length],
                  marginRight: 8,
                }} />
                {branch.name}
              </div>
              <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
                by {branch.created_by} — {branch.commit_count} commits
                {branch.forked_from_commit_id && " — forked"}
              </div>
            </div>
            <div style={{ textAlign: "right", fontSize: 13, color: "#999" }}>
              {new Date(branch.created_at).toLocaleDateString()}
            </div>
          </div>
        ))}
      </div>
      <p style={{ marginTop: 16, fontSize: 13, color: "#999", textAlign: "center" }}>
        Full DAG visualization coming soon. This shows the flat branch list for now.
      </p>
    </div>
  );
}
