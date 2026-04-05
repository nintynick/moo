"""Score Store — append-only ledger of eval results backed by SQLite."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from gitspoke.models import EvalRun, EvalRunStatus, MetricDirection, Score


class ScoreStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ── Scores (append-only) ──

    def record_score(
        self,
        commit_id: str,
        eval_version: str,
        metric_name: str,
        value: float,
        composite_score: float | None = None,
        runner_id: str = "local",
        constraints_passed: bool = True,
        execution_log_hash: str | None = None,
    ) -> Score:
        score = Score(
            id=uuid.uuid4().hex,
            commit_id=commit_id,
            eval_version=eval_version,
            metric_name=metric_name,
            value=value,
            composite_score=composite_score,
            runner_id=runner_id,
            constraints_passed=constraints_passed,
            execution_log_hash=execution_log_hash,
        )
        self.conn.execute(
            "INSERT INTO scores "
            "(id, commit_id, eval_version, metric_name, value, composite_score, "
            "runner_id, constraints_passed, execution_log_hash, signature, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                score.id,
                score.commit_id,
                score.eval_version,
                score.metric_name,
                score.value,
                score.composite_score,
                score.runner_id,
                int(score.constraints_passed),
                score.execution_log_hash,
                score.signature,
                score.timestamp.isoformat(),
            ),
        )
        self.conn.commit()
        return score

    def get_scores(
        self,
        commit_id: str,
        metric_name: str | None = None,
    ) -> list[Score]:
        if metric_name:
            rows = self.conn.execute(
                "SELECT * FROM scores WHERE commit_id = ? AND metric_name = ? ORDER BY timestamp DESC",
                (commit_id, metric_name),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM scores WHERE commit_id = ? ORDER BY timestamp DESC",
                (commit_id,),
            ).fetchall()
        return [self._row_to_score(r) for r in rows]

    def get_best_score(
        self,
        commit_id: str,
        metric_name: str,
        direction: MetricDirection,
    ) -> Score | None:
        agg = "MIN" if direction == MetricDirection.LOWER_IS_BETTER else "MAX"
        row = self.conn.execute(
            f"SELECT * FROM scores WHERE commit_id = ? AND metric_name = ? "
            f"ORDER BY value {'ASC' if agg == 'MIN' else 'DESC'} LIMIT 1",
            (commit_id, metric_name),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_score(row)

    def get_all_scores_for_metric(
        self, metric_name: str, eval_version: str | None = None
    ) -> list[Score]:
        if eval_version:
            rows = self.conn.execute(
                "SELECT * FROM scores WHERE metric_name = ? AND eval_version = ? ORDER BY timestamp DESC",
                (metric_name, eval_version),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM scores WHERE metric_name = ? ORDER BY timestamp DESC",
                (metric_name,),
            ).fetchall()
        return [self._row_to_score(r) for r in rows]

    # ── Eval Runs ──

    def create_eval_run(self, commit_id: str, manifest_version: str) -> EvalRun:
        run = EvalRun(
            id=uuid.uuid4().hex,
            commit_id=commit_id,
            manifest_version=manifest_version,
        )
        self.conn.execute(
            "INSERT INTO eval_runs (id, commit_id, manifest_version, status, started_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run.id,
                run.commit_id,
                run.manifest_version,
                run.status.value,
                None,
                None,
            ),
        )
        self.conn.commit()
        return run

    def update_eval_run(
        self,
        run_id: str,
        status: EvalRunStatus,
        completed_at: datetime | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        if status == EvalRunStatus.RUNNING:
            self.conn.execute(
                "UPDATE eval_runs SET status = ?, started_at = ? WHERE id = ?",
                (status.value, now.isoformat(), run_id),
            )
        elif status in (EvalRunStatus.COMPLETED, EvalRunStatus.FAILED):
            ts = (completed_at or now).isoformat()
            self.conn.execute(
                "UPDATE eval_runs SET status = ?, completed_at = ? WHERE id = ?",
                (status.value, ts, run_id),
            )
        else:
            self.conn.execute(
                "UPDATE eval_runs SET status = ? WHERE id = ?",
                (status.value, run_id),
            )
        self.conn.commit()

    def get_eval_run(self, run_id: str) -> EvalRun | None:
        row = self.conn.execute(
            "SELECT * FROM eval_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_eval_run(row)

    def get_eval_runs_for_commit(self, commit_id: str) -> list[EvalRun]:
        rows = self.conn.execute(
            "SELECT * FROM eval_runs WHERE commit_id = ? ORDER BY COALESCE(started_at, '') DESC",
            (commit_id,),
        ).fetchall()
        return [self._row_to_eval_run(r) for r in rows]

    # ── Row mappers ──

    @staticmethod
    def _row_to_score(row: sqlite3.Row) -> Score:
        return Score(
            id=row["id"],
            commit_id=row["commit_id"],
            eval_version=row["eval_version"],
            metric_name=row["metric_name"],
            value=row["value"],
            composite_score=row["composite_score"],
            runner_id=row["runner_id"],
            constraints_passed=bool(row["constraints_passed"]),
            execution_log_hash=row["execution_log_hash"],
            signature=row["signature"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )

    @staticmethod
    def _row_to_eval_run(row: sqlite3.Row) -> EvalRun:
        return EvalRun(
            id=row["id"],
            commit_id=row["commit_id"],
            manifest_version=row["manifest_version"],
            status=EvalRunStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )
