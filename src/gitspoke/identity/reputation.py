"""Reputation system — upstream credit propagation through the branch graph."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from gitspoke.graph.store import GraphStore
from gitspoke.identity.store import IdentityStore
from gitspoke.score.store import ScoreStore


# Credit decays by this factor per hop in the ancestry graph
UPSTREAM_DECAY = 0.5


class ReputationEngine:
    """Computes and propagates upstream credit through the branch graph."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.graph_store = GraphStore(conn)
        self.identity_store = IdentityStore(conn)
        self.score_store = ScoreStore(conn)

    def propagate_upstream_credit(self, commit_id: str, credit_amount: float = 1.0) -> dict[str, float]:
        """Walk up the ancestor chain from a leaderboard-placing commit
        and distribute decaying credit to upstream authors.

        Returns a dict of {author_name: credit_awarded}.
        """
        commit = self.graph_store.get_commit(commit_id)
        if commit is None:
            return {}

        credits: dict[str, float] = {}
        visited: set[str] = {commit_id}
        queue: list[tuple[str, float]] = []

        # Seed queue with parents
        for pid in commit.parent_ids:
            queue.append((pid, credit_amount * UPSTREAM_DECAY))

        while queue:
            cid, amount = queue.pop(0)
            if cid in visited or amount < 0.01:
                continue
            visited.add(cid)

            ancestor = self.graph_store.get_commit(cid)
            if ancestor is None:
                continue

            credits[ancestor.author] = credits.get(ancestor.author, 0) + amount

            # Propagate further upstream with decay
            for pid in ancestor.parent_ids:
                if pid not in visited:
                    queue.append((pid, amount * UPSTREAM_DECAY))

        # Apply credits to identity store
        for author_name, amount in credits.items():
            identity = self.identity_store.get_identity_by_name(author_name)
            if identity:
                self.identity_store.add_upstream_credit(identity.id, amount)

        return credits

    def compute_attribution_chain(self, commit_id: str, depth: int = 20) -> list[dict]:
        """Return the full attribution chain for a commit — who contributed what upstream."""
        ancestors = self.graph_store.get_ancestors(commit_id, depth)
        chain = []
        for i, ancestor in enumerate(ancestors):
            decay = UPSTREAM_DECAY ** i if i > 0 else 1.0
            chain.append({
                "commit_id": ancestor.id,
                "author": ancestor.author,
                "author_type": ancestor.author_type.value,
                "message": ancestor.message,
                "depth": i,
                "credit_weight": decay,
            })
        return chain

    def refresh_all_reputations(self) -> int:
        """Recompute reputation scores for all identities."""
        identities = self.identity_store.list_identities(limit=10000)
        for identity in identities:
            self.identity_store.update_reputation(identity.id)
        return len(identities)
