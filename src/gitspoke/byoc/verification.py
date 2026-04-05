"""Score verification pipeline — random re-evaluation and challenge resolution."""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timezone

from gitspoke.models import Challenge, ChallengeStatus, Score


# Percentage of scores to randomly verify
VERIFICATION_SAMPLE_RATE = 0.10

# Score difference threshold to flag as suspicious
SCORE_TOLERANCE = 0.05


class VerificationPipeline:
    """Manages score verification: random re-evaluation and community challenges."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ── Random Verification ──

    def select_for_verification(self, limit: int = 10) -> list[str]:
        """Select unverified scores for independent re-evaluation.
        Prioritizes top leaderboard positions."""
        rows = self.conn.execute(
            """
            SELECT s.id, s.commit_id, s.value, s.metric_name
            FROM scores s
            WHERE s.verified = 0 AND s.constraints_passed = 1
            ORDER BY s.value DESC
            LIMIT ?
            """,
            (limit * 5,),
        ).fetchall()

        # Sample a subset
        candidates = [dict(r) for r in rows]
        sample_size = min(limit, len(candidates))
        selected = random.sample(candidates, sample_size) if candidates else []
        return [s["id"] for s in selected]

    def record_verification(
        self,
        original_score_id: str,
        verification_value: float,
        verifier_runner_id: str,
    ) -> dict:
        """Record a verification result and determine if the original score stands."""
        row = self.conn.execute(
            "SELECT * FROM scores WHERE id = ?", (original_score_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Score not found: {original_score_id}")

        original_value = row["value"]
        difference = abs(original_value - verification_value)
        relative_diff = difference / max(abs(original_value), 1e-10)

        matches = relative_diff <= SCORE_TOLERANCE

        if matches:
            self.conn.execute(
                "UPDATE scores SET verified = 1 WHERE id = ?",
                (original_score_id,),
            )

        self.conn.commit()

        return {
            "original_score_id": original_score_id,
            "original_value": original_value,
            "verification_value": verification_value,
            "difference": difference,
            "relative_difference": relative_diff,
            "matches": matches,
            "verified": matches,
        }

    def get_verification_stats(self) -> dict:
        """Get overall verification statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        verified = self.conn.execute(
            "SELECT COUNT(*) FROM scores WHERE verified = 1"
        ).fetchone()[0]
        return {
            "total_scores": total,
            "verified_scores": verified,
            "verification_rate": verified / total if total > 0 else 0.0,
        }

    # ── Community Challenges ──

    def create_challenge(
        self,
        score_id: str,
        challenger_id: str,
        reason: str = "",
    ) -> Challenge:
        """Open a community challenge against a leaderboard score."""
        row = self.conn.execute(
            "SELECT * FROM scores WHERE id = ?", (score_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Score not found: {score_id}")

        challenge = Challenge(
            score_id=score_id,
            commit_id=row["commit_id"],
            challenger_id=challenger_id,
            reason=reason,
            original_score=row["value"],
        )
        self.conn.execute(
            "INSERT INTO challenges "
            "(id, score_id, commit_id, challenger_id, reason, status, "
            "verification_score, original_score, resolved_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                challenge.id,
                challenge.score_id,
                challenge.commit_id,
                challenge.challenger_id,
                challenge.reason,
                challenge.status.value,
                challenge.verification_score,
                challenge.original_score,
                None,
                challenge.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return challenge

    def resolve_challenge(
        self,
        challenge_id: str,
        verification_score: float,
    ) -> Challenge:
        """Resolve a challenge based on re-evaluation results."""
        row = self.conn.execute(
            "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Challenge not found: {challenge_id}")

        original = row["original_score"]
        difference = abs(original - verification_score)
        relative_diff = difference / max(abs(original), 1e-10)

        if relative_diff <= SCORE_TOLERANCE:
            status = ChallengeStatus.UPHELD  # Original score stands
        else:
            status = ChallengeStatus.OVERTURNED  # Score was inaccurate

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE challenges SET status = ?, verification_score = ?, resolved_at = ? WHERE id = ?",
            (status.value, verification_score, now, challenge_id),
        )

        # If overturned, mark the original score as unverified
        if status == ChallengeStatus.OVERTURNED:
            self.conn.execute(
                "UPDATE scores SET verified = 0 WHERE id = ?",
                (row["score_id"],),
            )

        self.conn.commit()

        return Challenge(
            id=row["id"],
            score_id=row["score_id"],
            commit_id=row["commit_id"],
            challenger_id=row["challenger_id"],
            reason=row["reason"],
            status=status,
            verification_score=verification_score,
            original_score=original,
            resolved_at=datetime.fromisoformat(now),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_challenge(self, challenge_id: str) -> Challenge | None:
        row = self.conn.execute(
            "SELECT * FROM challenges WHERE id = ?", (challenge_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_challenge(row)

    def list_challenges(
        self, commit_id: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[Challenge]:
        query = "SELECT * FROM challenges WHERE 1=1"
        params: list = []
        if commit_id:
            query += " AND commit_id = ?"
            params.append(commit_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_challenge(r) for r in rows]

    # ── Anomaly Detection ──

    def detect_anomalies(self, metric_name: str, std_threshold: float = 3.0) -> list[dict]:
        """Flag scores that are statistical outliers for a given metric."""
        rows = self.conn.execute(
            """
            SELECT s.id, s.commit_id, s.value, s.runner_id, c.author
            FROM scores s
            JOIN commits c ON s.commit_id = c.id
            WHERE s.metric_name = ? AND s.constraints_passed = 1
            """,
            (metric_name,),
        ).fetchall()

        if len(rows) < 3:
            return []

        values = [r["value"] for r in rows]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5

        if std < 1e-10:
            return []

        anomalies = []
        for row in rows:
            z_score = abs(row["value"] - mean) / std
            if z_score > std_threshold:
                anomalies.append({
                    "score_id": row["id"],
                    "commit_id": row["commit_id"],
                    "author": row["author"],
                    "value": row["value"],
                    "z_score": z_score,
                    "mean": mean,
                    "std": std,
                })

        return anomalies

    @staticmethod
    def _row_to_challenge(row: sqlite3.Row) -> Challenge:
        return Challenge(
            id=row["id"],
            score_id=row["score_id"],
            commit_id=row["commit_id"],
            challenger_id=row["challenger_id"],
            reason=row["reason"],
            status=ChallengeStatus(row["status"]),
            verification_score=row["verification_score"],
            original_score=row["original_score"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
