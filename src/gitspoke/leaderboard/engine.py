"""Leaderboard Engine — ranking logic over the Score Store."""

from __future__ import annotations

import sqlite3

from gitspoke.graph.store import GraphStore
from gitspoke.models import LeaderboardEntry, MetricDirection
from gitspoke.score.store import ScoreStore


class LeaderboardEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.graph_store = GraphStore(conn)
        self.score_store = ScoreStore(conn)

    def global_ranking(
        self,
        metric_name: str,
        direction: MetricDirection,
        limit: int = 50,
        eval_version: str | None = None,
    ) -> list[LeaderboardEntry]:
        """Rank all commits by best score for a given metric."""
        agg = "MIN" if direction == MetricDirection.LOWER_IS_BETTER else "MAX"
        order = "ASC" if direction == MetricDirection.LOWER_IS_BETTER else "DESC"

        version_filter = ""
        params: list = [metric_name]
        if eval_version:
            version_filter = "AND s.eval_version = ? "
            params.append(eval_version)
        params.append(limit)

        rows = self.conn.execute(
            f"""
            SELECT
                s.commit_id,
                {agg}(s.value) AS best_score,
                COUNT(*) AS run_count,
                c.author,
                b.name AS branch_name
            FROM scores s
            JOIN commits c ON s.commit_id = c.id
            JOIN branches b ON c.branch_id = b.id
            WHERE s.metric_name = ? AND s.constraints_passed = 1
            {version_filter}
            GROUP BY s.commit_id
            ORDER BY best_score {order}
            LIMIT ?
            """,
            params,
        ).fetchall()

        entries = []
        for rank, row in enumerate(rows, start=1):
            entries.append(
                LeaderboardEntry(
                    rank=rank,
                    commit_id=row["commit_id"],
                    branch_name=row["branch_name"],
                    author=row["author"],
                    metric_name=metric_name,
                    best_score=row["best_score"],
                    run_count=row["run_count"],
                )
            )
        return entries

    def branch_ranking(
        self,
        branch_name: str,
        metric_name: str,
        direction: MetricDirection,
        limit: int = 50,
    ) -> list[LeaderboardEntry]:
        """Rank commits within a single branch."""
        branch = self.graph_store.get_branch(branch_name)
        if branch is None:
            return []

        agg = "MIN" if direction == MetricDirection.LOWER_IS_BETTER else "MAX"
        order = "ASC" if direction == MetricDirection.LOWER_IS_BETTER else "DESC"

        rows = self.conn.execute(
            f"""
            SELECT
                s.commit_id,
                {agg}(s.value) AS best_score,
                COUNT(*) AS run_count,
                c.author
            FROM scores s
            JOIN commits c ON s.commit_id = c.id
            WHERE s.metric_name = ?
              AND c.branch_id = ?
              AND s.constraints_passed = 1
            GROUP BY s.commit_id
            ORDER BY best_score {order}
            LIMIT ?
            """,
            (metric_name, branch.id, limit),
        ).fetchall()

        entries = []
        for rank, row in enumerate(rows, start=1):
            entries.append(
                LeaderboardEntry(
                    rank=rank,
                    commit_id=row["commit_id"],
                    branch_name=branch_name,
                    author=row["author"],
                    metric_name=metric_name,
                    best_score=row["best_score"],
                    run_count=row["run_count"],
                )
            )
        return entries

    def best_fork_point(
        self,
        metric_name: str,
        direction: MetricDirection,
    ) -> str | None:
        """Return the commit_id of the current best-scoring commit — the recommended fork point."""
        ranking = self.global_ranking(metric_name, direction, limit=1)
        if not ranking:
            return None
        return ranking[0].commit_id

    def time_series(
        self,
        metric_name: str,
        direction: MetricDirection,
        limit: int = 100,
    ) -> list[dict]:
        """Return best score over time — the autoresearch staircase chart."""
        order = "ASC" if direction == MetricDirection.LOWER_IS_BETTER else "DESC"

        rows = self.conn.execute(
            """
            SELECT s.commit_id, s.value, s.timestamp, c.author
            FROM scores s
            JOIN commits c ON s.commit_id = c.id
            WHERE s.metric_name = ? AND s.constraints_passed = 1
            ORDER BY s.timestamp ASC
            """,
            (metric_name,),
        ).fetchall()

        # Build the staircase: track the running best
        best = None
        series = []
        is_lower = direction == MetricDirection.LOWER_IS_BETTER

        for row in rows:
            val = row["value"]
            if best is None or (is_lower and val < best) or (not is_lower and val > best):
                best = val
                series.append({
                    "commit_id": row["commit_id"],
                    "score": val,
                    "timestamp": row["timestamp"],
                    "author": row["author"],
                })

        return series[-limit:]
