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
        repo_id: str = "default",
    ) -> Branch:
        branch = Branch(
            name=name,
            created_by=created_by,
            forked_from_commit=forked_from_commit,
            tip_commit_id=forked_from_commit,
            repo_id=repo_id,
        )
        self.conn.execute(
            "INSERT INTO branches (id, name, tip_commit_id, created_by, forked_from_commit, repo_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                branch.id,
                branch.name,
                branch.tip_commit_id,
                branch.created_by,
                branch.forked_from_commit,
                branch.repo_id,
                branch.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return branch

    def get_branch(self, name: str, repo_id: str = "default") -> Branch | None:
        row = self.conn.execute(
            "SELECT * FROM branches WHERE name = ? AND repo_id = ?", (name, repo_id)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_branch(row)

    def list_branches(self, repo_id: str | None = None) -> list[Branch]:
        if repo_id:
            rows = self.conn.execute(
                "SELECT * FROM branches WHERE repo_id = ? ORDER BY created_at DESC",
                (repo_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM branches ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_branch(r) for r in rows]

    def update_branch_tip(self, name: str, commit_id: str, repo_id: str = "default") -> None:
        self.conn.execute(
            "UPDATE branches SET tip_commit_id = ? WHERE name = ? AND repo_id = ?",
            (commit_id, name, repo_id),
        )
        self.conn.commit()

    def fork_branch(
        self,
        source_commit_id: str,
        new_branch_name: str,
        author: str,
        repo_id: str = "default",
    ) -> Branch:
        commit = self.get_commit(source_commit_id)
        if commit is None:
            raise ValueError(f"Source commit not found: {source_commit_id}")
        return self.create_branch(
            name=new_branch_name,
            created_by=author,
            forked_from_commit=source_commit_id,
            repo_id=repo_id,
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
        repo_id: str = "default",
    ) -> Commit:
        branch = self.get_branch(branch_name, repo_id)
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
            repo_id=repo_id,
            created_at=now,
        )

        self.conn.execute(
            "INSERT INTO commits (id, parent_ids, branch_id, author, author_type, message, tree_hash, metadata, repo_id, lineage_group_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                commit.id,
                json.dumps(commit.parent_ids),
                commit.branch_id,
                commit.author,
                commit.author_type.value,
                commit.message,
                commit.tree_hash,
                json.dumps(commit.metadata),
                commit.repo_id,
                commit.lineage_group_id,
                commit.created_at.isoformat(),
            ),
        )
        # Update branch tip
        self.update_branch_tip(branch_name, commit.id, repo_id)
        return commit

    def get_commit(self, commit_id: str) -> Commit | None:
        row = self.conn.execute(
            "SELECT * FROM commits WHERE id = ?", (commit_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_commit(row)

    def list_commits(
        self, branch_name: str | None = None, limit: int = 50, repo_id: str = "default"
    ) -> list[Commit]:
        if branch_name:
            branch = self.get_branch(branch_name, repo_id)
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

    def get_graph_data(self, repo_id: str = "default", limit: int = 200) -> dict:
        """Return the full branch graph as nodes and edges for visualization."""
        commits = self.conn.execute(
            "SELECT c.id, c.parent_ids, c.branch_id, c.author, c.message, c.created_at, "
            "b.name as branch_name "
            "FROM commits c JOIN branches b ON c.branch_id = b.id "
            "WHERE c.repo_id = ? ORDER BY c.created_at DESC LIMIT ?",
            (repo_id, limit),
        ).fetchall()

        nodes = []
        edges = []
        for c in commits:
            nodes.append({
                "id": c["id"],
                "author": c["author"],
                "message": c["message"],
                "branch": c["branch_name"],
                "created_at": c["created_at"],
            })
            for pid in json.loads(c["parent_ids"]):
                edges.append({"source": pid, "target": c["id"]})

        return {"nodes": nodes, "edges": edges}

    # ── Row mappers ──

    @staticmethod
    def _row_to_branch(row: sqlite3.Row) -> Branch:
        return Branch(
            id=row["id"],
            name=row["name"],
            tip_commit_id=row["tip_commit_id"],
            created_by=row["created_by"],
            forked_from_commit=row["forked_from_commit"],
            repo_id=row["repo_id"],
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
            repo_id=row["repo_id"],
            lineage_group_id=row["lineage_group_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
