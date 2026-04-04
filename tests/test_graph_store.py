"""Tests for the Graph Store."""

import pytest
from gitspoke.graph.store import GraphStore
from gitspoke.models import AuthorType


def test_create_branch(graph_store: GraphStore):
    branch = graph_store.create_branch("experiment-1", "alice")
    assert branch.name == "experiment-1"
    assert branch.created_by == "alice"
    assert branch.tip_commit_id is None


def test_list_branches(graph_store: GraphStore):
    graph_store.create_branch("a", "alice")
    graph_store.create_branch("b", "bob")
    branches = graph_store.list_branches()
    assert len(branches) == 2


def test_create_root_commit(graph_store: GraphStore):
    graph_store.create_branch("main", "alice")
    commit = graph_store.create_commit(
        branch_name="main",
        author="alice",
        message="initial commit",
        tree_hash="abc123",
        parent_ids=[],
    )
    assert commit.id
    assert commit.parent_ids == []
    assert commit.author == "alice"

    # Branch tip should be updated
    branch = graph_store.get_branch("main")
    assert branch.tip_commit_id == commit.id


def test_create_child_commit(graph_store: GraphStore):
    graph_store.create_branch("main", "alice")
    root = graph_store.create_commit("main", "alice", "root", "hash1", parent_ids=[])
    child = graph_store.create_commit("main", "alice", "child", "hash2")

    assert child.parent_ids == [root.id]
    branch = graph_store.get_branch("main")
    assert branch.tip_commit_id == child.id


def test_fork_branch(graph_store: GraphStore):
    graph_store.create_branch("original", "alice")
    root = graph_store.create_commit("original", "alice", "root", "h1", parent_ids=[])

    forked = graph_store.fork_branch(root.id, "experiment", "bob")
    assert forked.name == "experiment"
    assert forked.forked_from_commit == root.id
    assert forked.tip_commit_id == root.id


def test_commit_on_forked_branch(graph_store: GraphStore):
    graph_store.create_branch("original", "alice")
    root = graph_store.create_commit("original", "alice", "root", "h1", parent_ids=[])

    graph_store.fork_branch(root.id, "fork", "bob")
    new_commit = graph_store.create_commit("fork", "bob", "improvement", "h2")
    assert root.id in new_commit.parent_ids


def test_get_ancestors(graph_store: GraphStore):
    graph_store.create_branch("main", "alice")
    c1 = graph_store.create_commit("main", "alice", "first", "h1", parent_ids=[])
    c2 = graph_store.create_commit("main", "alice", "second", "h2")
    c3 = graph_store.create_commit("main", "alice", "third", "h3")

    ancestors = graph_store.get_ancestors(c3.id, depth=10)
    assert len(ancestors) == 3
    ids = [a.id for a in ancestors]
    assert c3.id in ids
    assert c2.id in ids
    assert c1.id in ids


def test_list_commits_by_branch(graph_store: GraphStore):
    graph_store.create_branch("a", "alice")
    graph_store.create_branch("b", "bob")
    graph_store.create_commit("a", "alice", "a1", "h1", parent_ids=[])
    graph_store.create_commit("b", "bob", "b1", "h2", parent_ids=[])

    a_commits = graph_store.list_commits(branch_name="a")
    assert len(a_commits) == 1
    assert a_commits[0].author == "alice"


def test_agent_author_type(graph_store: GraphStore):
    graph_store.create_branch("agent-branch", "gpt-4")
    commit = graph_store.create_commit(
        "agent-branch", "gpt-4", "agent commit", "h1",
        parent_ids=[], author_type=AuthorType.AGENT,
    )
    fetched = graph_store.get_commit(commit.id)
    assert fetched.author_type == AuthorType.AGENT


def test_create_commit_nonexistent_branch(graph_store: GraphStore):
    with pytest.raises(ValueError, match="Branch not found"):
        graph_store.create_commit("nope", "alice", "msg", "h1", parent_ids=[])


def test_fork_nonexistent_commit(graph_store: GraphStore):
    with pytest.raises(ValueError, match="Source commit not found"):
        graph_store.fork_branch("nonexistent", "new-branch", "alice")
