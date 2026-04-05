"""Tests for multi-repo support."""

import pytest

from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.repo import RepoStore


@pytest.fixture
def repo_store():
    conn = get_connection(":memory:")
    bootstrap(conn)
    return RepoStore(conn)


def test_create_repo(repo_store):
    repo = repo_store.create_repo("nanochat", "alice", "ML training optimization")
    assert repo.name == "nanochat"
    assert repo.owner_id == "alice"


def test_get_repo_by_name(repo_store):
    repo_store.create_repo("nanochat", "alice")
    fetched = repo_store.get_repo_by_name("nanochat")
    assert fetched is not None
    assert fetched.name == "nanochat"


def test_list_repos(repo_store):
    repo_store.create_repo("repo-a", "alice")
    repo_store.create_repo("repo-b", "bob")
    repos = repo_store.list_repos()
    assert len(repos) == 2


def test_update_manifest_version(repo_store):
    repo = repo_store.create_repo("test", "alice")
    repo_store.update_manifest_version(repo.id, "2.0.0")
    fetched = repo_store.get_repo(repo.id)
    assert fetched.manifest_version == "2.0.0"
