"""Identity Store — cryptographic identity, reputation, and upstream credit."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from gitspoke.models import AuthorType, Identity


class IdentityStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_identity(
        self,
        display_name: str,
        identity_type: AuthorType = AuthorType.HUMAN,
        public_key: str | None = None,
        organization: str | None = None,
        agent_model: str | None = None,
        agent_version: str | None = None,
    ) -> Identity:
        identity = Identity(
            display_name=display_name,
            identity_type=identity_type,
            public_key=public_key,
            organization=organization,
            agent_model=agent_model,
            agent_version=agent_version,
        )
        self.conn.execute(
            "INSERT INTO identities "
            "(id, display_name, identity_type, public_key, organization, agent_model, "
            "agent_version, reputation_score, trust_score, total_commits, "
            "leaderboard_positions, upstream_credits, verification_match_rate, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identity.id,
                identity.display_name,
                identity.identity_type.value,
                identity.public_key,
                identity.organization,
                identity.agent_model,
                identity.agent_version,
                identity.reputation_score,
                identity.trust_score,
                identity.total_commits,
                identity.leaderboard_positions,
                identity.upstream_credits,
                identity.verification_match_rate,
                identity.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return identity

    def get_identity(self, identity_id: str) -> Identity | None:
        row = self.conn.execute(
            "SELECT * FROM identities WHERE id = ?", (identity_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_identity(row)

    def get_identity_by_name(self, display_name: str) -> Identity | None:
        row = self.conn.execute(
            "SELECT * FROM identities WHERE display_name = ?", (display_name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_identity(row)

    def list_identities(self, limit: int = 50) -> list[Identity]:
        rows = self.conn.execute(
            "SELECT * FROM identities ORDER BY reputation_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_identity(r) for r in rows]

    def update_reputation(self, identity_id: str) -> Identity | None:
        """Recompute reputation from component scores."""
        identity = self.get_identity(identity_id)
        if identity is None:
            return None

        # Reputation = weighted combination of leaderboard positions,
        # upstream credits, trust score, and consistency
        reputation = (
            identity.leaderboard_positions * 10.0
            + identity.upstream_credits * 5.0
            + identity.trust_score * 20.0
            + identity.verification_match_rate * 15.0
        )

        self.conn.execute(
            "UPDATE identities SET reputation_score = ? WHERE id = ?",
            (reputation, identity_id),
        )
        self.conn.commit()
        identity.reputation_score = reputation
        return identity

    def increment_commits(self, identity_id: str) -> None:
        self.conn.execute(
            "UPDATE identities SET total_commits = total_commits + 1 WHERE id = ?",
            (identity_id,),
        )
        self.conn.commit()

    def add_leaderboard_position(self, identity_id: str) -> None:
        self.conn.execute(
            "UPDATE identities SET leaderboard_positions = leaderboard_positions + 1 WHERE id = ?",
            (identity_id,),
        )
        self.conn.commit()

    def add_upstream_credit(self, identity_id: str, amount: float) -> None:
        self.conn.execute(
            "UPDATE identities SET upstream_credits = upstream_credits + ? WHERE id = ?",
            (amount, identity_id),
        )
        self.conn.commit()

    def update_verification_match_rate(self, identity_id: str, rate: float) -> None:
        self.conn.execute(
            "UPDATE identities SET verification_match_rate = ? WHERE id = ?",
            (rate, identity_id),
        )
        self.conn.commit()

    def update_trust_score(self, identity_id: str, score: float) -> None:
        self.conn.execute(
            "UPDATE identities SET trust_score = ? WHERE id = ?",
            (score, identity_id),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_identity(row: sqlite3.Row) -> Identity:
        return Identity(
            id=row["id"],
            display_name=row["display_name"],
            identity_type=AuthorType(row["identity_type"]),
            public_key=row["public_key"],
            organization=row["organization"],
            agent_model=row["agent_model"],
            agent_version=row["agent_version"],
            reputation_score=row["reputation_score"],
            trust_score=row["trust_score"],
            total_commits=row["total_commits"],
            leaderboard_positions=row["leaderboard_positions"],
            upstream_credits=row["upstream_credits"],
            verification_match_rate=row["verification_match_rate"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
