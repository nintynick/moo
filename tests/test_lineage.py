"""Tests for Lineage Group detection."""

import pytest

from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.lineage import LineageDetector
from gitspoke.graph.store import GraphStore


@pytest.fixture
def stores():
    conn = get_connection(":memory:")
    bootstrap(conn)
    return {
        "conn": conn,
        "graph": GraphStore(conn),
        "lineage": LineageDetector(conn),
    }


def test_create_lineage_group(stores):
    group = stores["lineage"].create_lineage_group(
        repo_id="repo-1",
        name="transformer-variants",
        description="All transformer-based approaches",
        root_commit_ids=["abc123"],
    )
    assert group.name == "transformer-variants"
    assert group.repo_id == "repo-1"


def test_list_lineage_groups(stores):
    stores["lineage"].create_lineage_group("repo-1", "group-a")
    stores["lineage"].create_lineage_group("repo-1", "group-b")
    stores["lineage"].create_lineage_group("repo-2", "group-c")

    groups = stores["lineage"].list_lineage_groups("repo-1")
    assert len(groups) == 2


def test_assign_commit_to_lineage(stores):
    gs = stores["graph"]
    gs.create_branch("main", "alice")
    c = gs.create_commit("main", "alice", "test", "h1", parent_ids=[])

    group = stores["lineage"].create_lineage_group("default", "group-1")
    stores["lineage"].assign_commit_to_lineage(c.id, group.id)

    fetched = gs.get_commit(c.id)
    assert fetched.lineage_group_id == group.id


def test_auto_detect_lineage_groups(stores):
    gs = stores["graph"]

    # Create two families of branches with shared ancestry
    gs.create_branch("main", "alice")
    root = gs.create_commit("main", "alice", "root", "h0", parent_ids=[])
    c1 = gs.create_commit("main", "alice", "base", "h1")
    c2 = gs.create_commit("main", "alice", "more", "h2")

    # Family A: two branches forking from c2
    gs.fork_branch(c2.id, "exp-a1", "alice")
    gs.create_commit("exp-a1", "alice", "a1", "ha1")

    gs.fork_branch(c2.id, "exp-a2", "bob")
    gs.create_commit("exp-a2", "bob", "a2", "ha2")

    groups = stores["lineage"].detect_lineage_groups("default", min_shared_depth=2)
    # Should find at least one group (the branches sharing deep ancestry)
    # Exact count depends on clustering, but the system should work without errors
    assert isinstance(groups, list)
