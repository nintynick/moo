"""Tests for the extended API endpoints (Phase 2+3)."""

import pytest
from fastapi.testclient import TestClient

from gitspoke.api import create_app
from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore
from gitspoke.identity.store import IdentityStore
from gitspoke.score.store import ScoreStore


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "api_ext.db")
    app = create_app(db_path)
    return TestClient(app)


@pytest.fixture
def seeded_client(tmp_path):
    db_path = str(tmp_path / "api_ext.db")
    conn = get_connection(db_path)
    bootstrap(conn)
    gs = GraphStore(conn)
    ss = ScoreStore(conn)
    ids = IdentityStore(conn)

    gs.create_branch("exp-1", "alice")
    c1 = gs.create_commit("exp-1", "alice", "first", "h1", parent_ids=[])
    c2 = gs.create_commit("exp-1", "alice", "second", "h2")
    ss.record_score(c1.id, "1.0.0", "accuracy", 0.85)
    ss.record_score(c2.id, "1.0.0", "accuracy", 0.92)
    ids.create_identity("alice")

    c1_id, c2_id, s_id = c1.id, c2.id, None
    scores = ss.get_scores(c1.id)
    s_id = scores[0].id if scores else None
    conn.close()

    app = create_app(db_path)
    return TestClient(app), c1_id, c2_id, s_id


# ── Identity endpoints ──

def test_create_identity(client):
    resp = client.post("/api/identities", json={"display_name": "bob", "identity_type": "human"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "bob"


def test_list_identities(seeded_client):
    client, *_ = seeded_client
    resp = client.get("/api/identities")
    assert resp.status_code == 200
    assert len(resp.json()["identities"]) >= 1


def test_get_reputation(seeded_client):
    client, *_ = seeded_client
    # Get alice's identity first
    resp = client.get("/api/identities")
    alice = resp.json()["identities"][0]
    resp = client.get(f"/api/identities/{alice['id']}/reputation")
    assert resp.status_code == 200
    assert "reputation_score" in resp.json()


# ── Runner endpoints ──

def test_register_runner(client):
    resp = client.post("/api/runners", json={
        "name": "gpu-1", "owner_id": "alice", "gpu_type": "rtx-4090", "memory": "64GB"
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "gpu-1"


def test_runner_heartbeat(client):
    resp = client.post("/api/runners", json={"name": "r1", "owner_id": "alice"})
    runner_id = resp.json()["id"]
    resp = client.post(f"/api/runners/{runner_id}/heartbeat")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"


def test_list_runners(client):
    client.post("/api/runners", json={"name": "r1", "owner_id": "alice"})
    resp = client.get("/api/runners")
    assert resp.status_code == 200
    assert len(resp.json()["runners"]) >= 1


# ── Challenge endpoints ──

def test_create_and_list_challenges(seeded_client):
    client, c1_id, _, s_id = seeded_client
    resp = client.post("/api/challenges", json={
        "score_id": s_id, "challenger_id": "bob", "reason": "Suspicious"
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"

    resp = client.get("/api/challenges")
    assert resp.status_code == 200
    assert len(resp.json()["challenges"]) == 1


# ── Verification endpoints ──

def test_verification_stats(seeded_client):
    client, *_ = seeded_client
    resp = client.get("/api/verification/stats")
    assert resp.status_code == 200
    assert "total_scores" in resp.json()


# ── Repo endpoints ──

def test_create_and_list_repos(client):
    resp = client.post("/api/repos", json={"name": "nanochat", "owner_id": "alice"})
    assert resp.status_code == 200

    resp = client.get("/api/repos")
    assert resp.status_code == 200
    assert len(resp.json()["repos"]) >= 1


# ── Graph endpoint ──

def test_graph_data(seeded_client):
    client, *_ = seeded_client
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    assert "nodes" in resp.json()
    assert "edges" in resp.json()


# ── Event endpoints ──

def test_events(seeded_client):
    client, *_ = seeded_client
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert "events" in resp.json()


# ── Webhook endpoints ──

def test_webhooks(client):
    # Create repo first
    resp = client.post("/api/repos", json={"name": "test-repo", "owner_id": "alice"})
    repo_id = resp.json()["id"]

    resp = client.post("/api/webhooks", json={
        "repo_id": repo_id,
        "url": "https://example.com/hook",
        "events": ["commit.pushed"],
        "created_by": "alice",
    })
    assert resp.status_code == 200

    resp = client.get(f"/api/webhooks?repo_id={repo_id}")
    assert resp.status_code == 200
    assert len(resp.json()["webhooks"]) == 1


# ── Attribution endpoint ──

def test_attribution(seeded_client):
    client, _, c2_id, _ = seeded_client
    resp = client.get(f"/api/commits/{c2_id}/attribution")
    assert resp.status_code == 200
    assert len(resp.json()["attribution"]) > 0


# ── Lineage group endpoints ──

def test_lineage_groups(seeded_client):
    client, *_ = seeded_client
    resp = client.post("/api/repos/default/lineage-groups", json={
        "name": "test-group", "description": "Test lineage group"
    })
    assert resp.status_code == 200

    resp = client.get("/api/repos/default/lineage-groups")
    assert resp.status_code == 200
    assert len(resp.json()["lineage_groups"]) >= 1


# ── Web UI ──

def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "GitSpoke" in resp.text


# ── Health ──

def test_health_v2(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["version"] == "0.2.0"
