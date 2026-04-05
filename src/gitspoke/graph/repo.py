"""Repository store — multi-repo support."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from gitspoke.models import Repository


class RepoStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_repo(
        self,
        name: str,
        owner_id: str,
        description: str = "",
    ) -> Repository:
        repo = Repository(
            name=name,
            owner_id=owner_id,
            description=description,
        )
        self.conn.execute(
            "INSERT INTO repositories (id, name, description, owner_id, manifest_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                repo.id,
                repo.name,
                repo.description,
                repo.owner_id,
                repo.manifest_version,
                repo.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return repo

    def get_repo(self, repo_id: str) -> Repository | None:
        row = self.conn.execute(
            "SELECT * FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_repo(row)

    def get_repo_by_name(self, name: str) -> Repository | None:
        row = self.conn.execute(
            "SELECT * FROM repositories WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_repo(row)

    def list_repos(self, limit: int = 50) -> list[Repository]:
        rows = self.conn.execute(
            "SELECT * FROM repositories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_repo(r) for r in rows]

    def update_manifest_version(self, repo_id: str, version: str) -> None:
        self.conn.execute(
            "UPDATE repositories SET manifest_version = ? WHERE id = ?",
            (version, repo_id),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_repo(row: sqlite3.Row) -> Repository:
        return Repository(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            owner_id=row["owner_id"],
            manifest_version=row["manifest_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
