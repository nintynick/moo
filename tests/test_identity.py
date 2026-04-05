"""Tests for the Identity system and Reputation engine."""

import pytest

from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore
from gitspoke.identity.reputation import ReputationEngine
from gitspoke.identity.store import IdentityStore
from gitspoke.models import AuthorType
from gitspoke.score.store import ScoreStore


@pytest.fixture
def stores():
    conn = get_connection(":memory:")
    bootstrap(conn)
    return {
        "conn": conn,
        "identity": IdentityStore(conn),
        "graph": GraphStore(conn),
        "score": ScoreStore(conn),
        "reputation": ReputationEngine(conn),
    }


def test_create_identity(stores):
    identity = stores["identity"].create_identity("alice", AuthorType.HUMAN, public_key="pk_alice")
    assert identity.display_name == "alice"
    assert identity.public_key == "pk_alice"
    assert identity.reputation_score == 0.0


def test_create_agent_identity(stores):
    identity = stores["identity"].create_identity(
        "gpt-4-agent",
        AuthorType.AGENT,
        agent_model="gpt-4",
        agent_version="2024-01",
        organization="openai",
    )
    assert identity.identity_type == AuthorType.AGENT
    assert identity.agent_model == "gpt-4"


def test_get_by_name(stores):
    stores["identity"].create_identity("bob")
    fetched = stores["identity"].get_identity_by_name("bob")
    assert fetched is not None
    assert fetched.display_name == "bob"


def test_list_identities(stores):
    stores["identity"].create_identity("alice")
    stores["identity"].create_identity("bob")
    identities = stores["identity"].list_identities()
    assert len(identities) == 2


def test_reputation_computation(stores):
    identity = stores["identity"].create_identity("alice")
    stores["identity"].add_leaderboard_position(identity.id)
    stores["identity"].add_leaderboard_position(identity.id)
    stores["identity"].add_upstream_credit(identity.id, 3.0)

    updated = stores["identity"].update_reputation(identity.id)
    assert updated.reputation_score > 0


def test_trust_score_update(stores):
    identity = stores["identity"].create_identity("alice")
    stores["identity"].update_trust_score(identity.id, 0.95)
    fetched = stores["identity"].get_identity(identity.id)
    assert fetched.trust_score == 0.95


def test_upstream_credit_propagation(stores):
    gs = stores["graph"]
    gs.create_branch("alice-branch", "alice")
    c1 = gs.create_commit("alice-branch", "alice", "foundation", "h1", parent_ids=[])
    c2 = gs.create_commit("alice-branch", "alice", "improvement", "h2")

    gs.fork_branch(c2.id, "bob-branch", "bob")
    c3 = gs.create_commit("bob-branch", "bob", "bob's work", "h3")

    # Create identities
    stores["identity"].create_identity("alice")
    stores["identity"].create_identity("bob")

    # Bob's commit reaches the leaderboard — propagate upstream credit
    credits = stores["reputation"].propagate_upstream_credit(c3.id, credit_amount=1.0)

    assert "alice" in credits
    assert credits["alice"] > 0


def test_attribution_chain(stores):
    gs = stores["graph"]
    gs.create_branch("main", "alice")
    c1 = gs.create_commit("main", "alice", "root", "h1", parent_ids=[])
    c2 = gs.create_commit("main", "bob", "build on root", "h2")

    chain = stores["reputation"].compute_attribution_chain(c2.id)
    assert len(chain) == 2
    assert chain[0]["author"] == "bob"
    assert chain[0]["depth"] == 0
    assert chain[0]["credit_weight"] == 1.0
    assert chain[1]["author"] == "alice"
    assert chain[1]["credit_weight"] < 1.0
