"""Lineage group detection — clustering branches by shared ancestry."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from gitspoke.graph.store import GraphStore
from gitspoke.models import LineageGroup


class LineageDetector:
    """Detects and manages lineage groups — clusters of branches with shared
    architectural DNA whose eval scores are meaningfully comparable."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.graph_store = GraphStore(conn)

    # ── Manual lineage group management ──

    def create_lineage_group(
        self,
        repo_id: str,
        name: str,
        description: str = "",
        root_commit_ids: list[str] | None = None,
        auto_detected: bool = False,
    ) -> LineageGroup:
        group = LineageGroup(
            repo_id=repo_id,
            name=name,
            description=description,
            root_commit_ids=root_commit_ids or [],
            auto_detected=auto_detected,
        )
        self.conn.execute(
            "INSERT INTO lineage_groups (id, repo_id, name, description, root_commit_ids, auto_detected, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                group.id,
                group.repo_id,
                group.name,
                group.description,
                json.dumps(group.root_commit_ids),
                int(group.auto_detected),
                group.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return group

    def get_lineage_group(self, group_id: str) -> LineageGroup | None:
        row = self.conn.execute(
            "SELECT * FROM lineage_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_group(row)

    def list_lineage_groups(self, repo_id: str) -> list[LineageGroup]:
        rows = self.conn.execute(
            "SELECT * FROM lineage_groups WHERE repo_id = ? ORDER BY created_at",
            (repo_id,),
        ).fetchall()
        return [self._row_to_group(r) for r in rows]

    def assign_commit_to_lineage(self, commit_id: str, lineage_group_id: str) -> None:
        self.conn.execute(
            "UPDATE commits SET lineage_group_id = ? WHERE id = ?",
            (lineage_group_id, commit_id),
        )
        self.conn.commit()

    # ── Automatic detection ──

    def detect_lineage_groups(
        self, repo_id: str, min_shared_depth: int = 3
    ) -> list[LineageGroup]:
        """Auto-detect lineage groups by analyzing shared ancestry depth.

        Algorithm: for each pair of branch tips, compute the depth of their
        common ancestor. Branches that share deep common ancestry are grouped.
        """
        branches = self.conn.execute(
            "SELECT * FROM branches WHERE repo_id = ? AND tip_commit_id IS NOT NULL",
            (repo_id,),
        ).fetchall()

        if len(branches) < 2:
            return []

        # Build ancestry sets for each branch tip
        ancestry_map: dict[str, set[str]] = {}
        for branch in branches:
            tip = branch["tip_commit_id"]
            ancestors = self.graph_store.get_ancestors(tip, depth=100)
            ancestry_map[tip] = {a.id for a in ancestors}

        # Find clusters based on shared ancestry
        tips = list(ancestry_map.keys())
        clusters: list[set[str]] = []

        for i, tip_a in enumerate(tips):
            placed = False
            for cluster in clusters:
                for tip_b in cluster:
                    shared = len(ancestry_map[tip_a] & ancestry_map[tip_b])
                    if shared >= min_shared_depth:
                        cluster.add(tip_a)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                clusters.append({tip_a})

        # Create lineage groups for non-trivial clusters
        groups = []
        existing = {g.name for g in self.list_lineage_groups(repo_id)}

        for idx, cluster in enumerate(clusters):
            if len(cluster) < 2:
                continue

            name = f"lineage-{idx + 1}"
            if name in existing:
                continue

            # Find the deepest common ancestor as root
            common = set.intersection(*(ancestry_map[tip] for tip in cluster))
            root_ids = list(common)[:5] if common else list(cluster)[:1]

            group = self.create_lineage_group(
                repo_id=repo_id,
                name=name,
                description=f"Auto-detected group with {len(cluster)} branches",
                root_commit_ids=root_ids,
                auto_detected=True,
            )

            # Assign commits to the group
            for tip in cluster:
                for ancestor_id in ancestry_map[tip]:
                    self.assign_commit_to_lineage(ancestor_id, group.id)

            groups.append(group)

        return groups

    @staticmethod
    def _row_to_group(row: sqlite3.Row) -> LineageGroup:
        return LineageGroup(
            id=row["id"],
            repo_id=row["repo_id"],
            name=row["name"],
            description=row["description"],
            root_commit_ids=json.loads(row["root_commit_ids"]),
            auto_detected=bool(row["auto_detected"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
