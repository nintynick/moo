"""BYOC Gateway — runner registration, attestation, job dispatch."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from gitspoke.models import EvalRunStatus, Runner, RunnerStatus
from gitspoke.score.store import ScoreStore


class BYOCGateway:
    """Manages Bring-Your-Own-Compute runners and eval job dispatch."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.score_store = ScoreStore(conn)

    # ── Runner Registration ──

    def register_runner(
        self,
        name: str,
        owner_id: str,
        gpu_type: str | None = None,
        gpu_memory: str | None = None,
        cpu_cores: int | None = None,
        memory: str | None = None,
        public_key: str | None = None,
    ) -> Runner:
        runner = Runner(
            name=name,
            owner_id=owner_id,
            gpu_type=gpu_type,
            gpu_memory=gpu_memory,
            cpu_cores=cpu_cores,
            memory=memory,
            public_key=public_key,
        )
        self.conn.execute(
            "INSERT INTO runners "
            "(id, name, owner_id, status, gpu_type, gpu_memory, cpu_cores, memory, "
            "public_key, trusted, last_heartbeat, jobs_completed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                runner.id,
                runner.name,
                runner.owner_id,
                runner.status.value,
                runner.gpu_type,
                runner.gpu_memory,
                runner.cpu_cores,
                runner.memory,
                runner.public_key,
                int(runner.trusted),
                None,
                0,
                runner.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return runner

    def get_runner(self, runner_id: str) -> Runner | None:
        row = self.conn.execute(
            "SELECT * FROM runners WHERE id = ?", (runner_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_runner(row)

    def list_runners(self, owner_id: str | None = None) -> list[Runner]:
        if owner_id:
            rows = self.conn.execute(
                "SELECT * FROM runners WHERE owner_id = ? ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runners ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_runner(r) for r in rows]

    def list_trusted_runners(self) -> list[Runner]:
        rows = self.conn.execute(
            "SELECT * FROM runners WHERE trusted = 1 AND status != 'offline'"
        ).fetchall()
        return [self._row_to_runner(r) for r in rows]

    # ── Heartbeat & Status ──

    def heartbeat(self, runner_id: str) -> Runner | None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE runners SET last_heartbeat = ?, status = 'online' WHERE id = ?",
            (now, runner_id),
        )
        self.conn.commit()
        return self.get_runner(runner_id)

    def update_status(self, runner_id: str, status: RunnerStatus) -> None:
        self.conn.execute(
            "UPDATE runners SET status = ? WHERE id = ?",
            (status.value, runner_id),
        )
        self.conn.commit()

    def set_trusted(self, runner_id: str, trusted: bool) -> None:
        self.conn.execute(
            "UPDATE runners SET trusted = ? WHERE id = ?",
            (int(trusted), runner_id),
        )
        self.conn.commit()

    # ── Job Dispatch ──

    def get_pending_jobs(self, runner_id: str | None = None) -> list[dict]:
        """Get pending eval runs that need a runner."""
        rows = self.conn.execute(
            "SELECT er.*, c.author, c.message FROM eval_runs er "
            "JOIN commits c ON er.commit_id = c.id "
            "WHERE er.status = 'pending' "
            "ORDER BY er.id ASC"
        ).fetchall()
        jobs = []
        for row in rows:
            jobs.append({
                "eval_run_id": row["id"],
                "commit_id": row["commit_id"],
                "manifest_version": row["manifest_version"],
                "author": row["author"],
                "message": row["message"],
            })
        return jobs

    def claim_job(self, eval_run_id: str, runner_id: str) -> bool:
        """Attempt to claim a pending eval job for a runner. Returns True if successful."""
        result = self.conn.execute(
            "UPDATE eval_runs SET status = 'running', runner_id = ? "
            "WHERE id = ? AND status = 'pending'",
            (runner_id, eval_run_id),
        )
        self.conn.commit()
        if result.rowcount > 0:
            self.update_status(runner_id, RunnerStatus.BUSY)
            return True
        return False

    def complete_job(self, eval_run_id: str, runner_id: str) -> None:
        """Mark a job as completed and increment runner stats."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE eval_runs SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, eval_run_id),
        )
        self.conn.execute(
            "UPDATE runners SET jobs_completed = jobs_completed + 1, status = 'online' WHERE id = ?",
            (runner_id,),
        )
        self.conn.commit()

    def fail_job(self, eval_run_id: str, runner_id: str) -> None:
        """Mark a job as failed and free the runner."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE eval_runs SET status = 'failed', completed_at = ? WHERE id = ?",
            (now, eval_run_id),
        )
        self.conn.execute(
            "UPDATE runners SET status = 'online' WHERE id = ?",
            (runner_id,),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_runner(row: sqlite3.Row) -> Runner:
        return Runner(
            id=row["id"],
            name=row["name"],
            owner_id=row["owner_id"],
            status=RunnerStatus(row["status"]),
            gpu_type=row["gpu_type"],
            gpu_memory=row["gpu_memory"],
            cpu_cores=row["cpu_cores"],
            memory=row["memory"],
            public_key=row["public_key"],
            trusted=bool(row["trusted"]),
            last_heartbeat=datetime.fromisoformat(row["last_heartbeat"]) if row["last_heartbeat"] else None,
            jobs_completed=row["jobs_completed"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
