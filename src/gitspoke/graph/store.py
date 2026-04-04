"""Graph Store — DAG of commits and branches backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from gitspoke.models import AuthorType, Branch, Commit


class GraphStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ── Branches ──

    def create_branch(
        self,
        name: str,
        created_by: str,
        forked_from_commit: str | None = None,
    ) -> Branch:
        branch = Branch(
            name=name,
            created_by=created_by,
            forked_from_commit=forked_from_commit,
            tip_commit_id=forked_from_commit,
        )
        self.conn.execute(
            "INSERT INTO branches (id, name, tip_commit_id, created_by, forked_from_commit, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                branch.id,
                branch.name,
                branch.tip_commit_id,
                branch.created_by,
                branch.forked_from_commit,
                branch.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return branch

    def get_branch(self, name: str) -> Branch | None:
        row = self.conn.execute(
            "SELECT * FROM branches WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_branch(row)

    def list_branches(self) -> list[Branch]:
        rows = self.conn.execute(
            "SELECT * FROM branches ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_branch(r) for r in rows]

    def update_branch_tip(self, name: str, commit_id: str) -> None:
        self.conn.execute(
            "UPDATE branches SET tip_commit_id = ? WHERE name = ?",
            (commit_id, name),
        )
        self.conn.commit()

    def fork_branch(
        self,
        source_commit_id: str,
        new_branch_name: str,
        author: str,
    ) -> Branch:
        commit = self.get_commit(source_commit_id)
        if commit is None:
            raise ValueError(f"Source commit not found: {source_commit_id}")
        return self.create_branch(
            name=new_branch_name,
            created_by=author,
            forked_from_commit=source_commit_id,
        )

    # ── Commits ──

    def create_commit(
        self,
        branch_name: str,
        author: str,
        message: str,
        tree_hash: str,
        parent_ids: list[str] | None = None,
        author_type: AuthorType = AuthorType.HUMAN,
        metadata: dict | None = None,
    ) -> Commit:
        branch = self.get_branch(branch_name)
        if branch is None:
            raise ValueError(f"Branch not found: {branch_name}")

        if parent_ids is None:
            parent_ids = [branch.tip_commit_id] if branch.tip_commit_id else []

        # Validate parents exist
        for pid in parent_ids:
            if self.get_commit(pid) is None:
                raise ValueError(f"Parent commit not found: {pid}")

        now = datetime.now(timezone.utc)
        commit_id = Commit.compute_id(parent_ids, tree_hash, now.isoformat())

        commit = Commit(
            id=commit_id,
            parent_ids=parent_ids,
            branch_id=branch.id,
            author=author,
            author_type=author_type,
            message=message,
            tree_hash=tree_hash,
            metadata=metadata or {},
            created_at=now,
        )

        self.conn.execute(
            "INSERT INTO commits (id, parent_ids, branch_id, author, author_type, message, tree_hash, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                commit.id,
                json.dumps(commit.parent_ids),
                commit.branch_id,
                commit.author,
                commit.author_type.value,
                commit.message,
                commit.tree_hash,
                json.dumps(commit.metadata),
                commit.created_at.isoformat(),
            ),
        )
        # Update branch tip
        self.update_branch_tip(branch_name, commit.id)
        return commit

    def get_commit(self, commit_id: str) -> Commit | None:
        row = self.conn.execute(
            "SELECT * FROM commits WHERE id = ?", (commit_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_commit(row)

    def list_commits(
        self, branch_name: str | None = None, limit: int = 50
    ) -> list[Commit]:
        if branch_name:
            branch = self.get_branch(branch_name)
            if branch is None:
                return []
            rows = self.conn.execute(
                "SELECT * FROM commits WHERE branch_id = ? ORDER BY created_at DESC LIMIT ?",
                (branch.id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM commits ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_commit(r) for r in rows]

    def get_ancestors(self, commit_id: str, depth: int = 50) -> list[Commit]:
        """BFS traversal up the DAG from a commit."""
        visited: set[str] = set()
        queue = [commit_id]
        result: list[Commit] = []

        while queue and len(result) < depth:
            cid = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)
            commit = self.get_commit(cid)
            if commit is None:
                continue
            result.append(commit)
            queue.extend(commit.parent_ids)

        return result

    def get_branch_for_commit(self, commit_id: str) -> Branch | None:
        commit = self.get_commit(commit_id)
        if commit is None:
            return None
        row = self.conn.execute(
            "SELECT * FROM branches WHERE id = ?", (commit.branch_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_branch(row)

    # ── Row mappers ──

    @staticmethod
    def _row_to_branch(row: sqlite3.Row) -> Branch:
        return Branch(
            id=row["id"],
            name=row["name"],
            tip_commit_id=row["tip_commit_id"],
            created_by=row["created_by"],
            forked_from_commit=row["forked_from_commit"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_commit(row: sqlite3.Row) -> Commit:
        return Commit(
            id=row["id"],
            parent_ids=json.loads(row["parent_ids"]),
            branch_id=row["branch_id"],
            author=row["author"],
            author_type=AuthorType(row["author_type"]),
            message=row["message"],
            tree_hash=row["tree_hash"],
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
