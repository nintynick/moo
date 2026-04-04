"""Tests for the GitSpoke API."""

import pytest
from fastapi.testclient import TestClient

from gitspoke.api import create_app
from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore
from gitspoke.score.store import ScoreStore


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "api_test.db")
    app = create_app(db_path)
    return TestClient(app)


@pytest.fixture
def seeded_client(tmp_path):
    db_path = str(tmp_path / "api_test.db")
    # Seed data first, then close the connection
    conn = get_connection(db_path)
    bootstrap(conn)
    gs = GraphStore(conn)
    ss = ScoreStore(conn)

    gs.create_branch("exp-1", "alice")
    c1 = gs.create_commit("exp-1", "alice", "first", "h1", parent_ids=[])
    c2 = gs.create_commit("exp-1", "alice", "second", "h2")

    ss.record_score(c1.id, "1.0.0", "accuracy", 0.85)
    ss.record_score(c2.id, "1.0.0", "accuracy", 0.92)

    c1_id, c2_id = c1.id, c2.id
    conn.close()

    # Now create the app with a fresh connection to the same DB
    app = create_app(db_path)
    client = TestClient(app)
    return client, c1_id, c2_id


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_leaderboard(seeded_client):
    client, c1_id, c2_id = seeded_client
    resp = client.get("/leaderboard", params={
        "metric": "accuracy",
        "direction": "higher-is-better",
    })
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 2
    assert entries[0]["commit_id"] == c2_id  # 0.92 ranked first


def test_branches(seeded_client):
    client, _, _ = seeded_client
    resp = client.get("/branches")
    assert resp.status_code == 200
    assert len(resp.json()["branches"]) == 1


def test_get_branch(seeded_client):
    client, _, _ = seeded_client
    resp = client.get("/branches/exp-1")
    assert resp.status_code == 200
    assert resp.json()["name"] == "exp-1"


def test_get_branch_not_found(client):
    resp = client.get("/branches/nonexistent")
    assert resp.status_code == 404


def test_get_commit(seeded_client):
    client, c1_id, _ = seeded_client
    resp = client.get(f"/commits/{c1_id}")
    assert resp.status_code == 200
    assert resp.json()["author"] == "alice"
    assert len(resp.json()["scores"]) == 1


def test_get_commit_not_found(client):
    resp = client.get("/commits/nonexistent")
    assert resp.status_code == 404


def test_commit_scores(seeded_client):
    client, c1_id, _ = seeded_client
    resp = client.get(f"/commits/{c1_id}/scores")
    assert resp.status_code == 200
    assert len(resp.json()["scores"]) == 1


def test_best_fork_point(seeded_client):
    client, _, c2_id = seeded_client
    resp = client.get("/leaderboard/best-fork-point", params={
        "metric": "accuracy",
        "direction": "higher-is-better",
    })
    assert resp.status_code == 200
    assert resp.json()["commit_id"] == c2_id


def test_time_series(seeded_client):
    client, _, _ = seeded_client
    resp = client.get("/leaderboard/time-series", params={
        "metric": "accuracy",
        "direction": "higher-is-better",
    })
    assert resp.status_code == 200
    assert len(resp.json()["series"]) > 0
