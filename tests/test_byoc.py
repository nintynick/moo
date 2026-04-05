"""Tests for the BYOC Gateway and Verification Pipeline."""

import pytest

from gitspoke.byoc.gateway import BYOCGateway
from gitspoke.byoc.verification import VerificationPipeline
from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore
from gitspoke.models import ChallengeStatus, RunnerStatus
from gitspoke.score.store import ScoreStore


@pytest.fixture
def stores():
    conn = get_connection(":memory:")
    bootstrap(conn)
    gs = GraphStore(conn)
    ss = ScoreStore(conn)
    byoc = BYOCGateway(conn)
    verif = VerificationPipeline(conn)

    # Seed data
    gs.create_branch("main", "alice")
    commit = gs.create_commit("main", "alice", "test", "h1", parent_ids=[])

    return {
        "conn": conn, "graph": gs, "score": ss,
        "byoc": byoc, "verification": verif,
        "commit_id": commit.id,
    }


# ── Runner Tests ──

def test_register_runner(stores):
    runner = stores["byoc"].register_runner(
        name="gpu-1", owner_id="alice",
        gpu_type="rtx-4090", gpu_memory="24GB",
        cpu_cores=16, memory="64GB",
    )
    assert runner.name == "gpu-1"
    assert runner.status == RunnerStatus.OFFLINE
    assert runner.gpu_type == "rtx-4090"


def test_heartbeat(stores):
    runner = stores["byoc"].register_runner("r1", "alice")
    updated = stores["byoc"].heartbeat(runner.id)
    assert updated.status == RunnerStatus.ONLINE
    assert updated.last_heartbeat is not None


def test_list_runners(stores):
    stores["byoc"].register_runner("r1", "alice")
    stores["byoc"].register_runner("r2", "bob")
    assert len(stores["byoc"].list_runners()) == 2
    assert len(stores["byoc"].list_runners("alice")) == 1


def test_trusted_runners(stores):
    r1 = stores["byoc"].register_runner("r1", "alice")
    stores["byoc"].set_trusted(r1.id, True)
    stores["byoc"].heartbeat(r1.id)
    trusted = stores["byoc"].list_trusted_runners()
    assert len(trusted) == 1
    assert trusted[0].trusted is True


# ── Job Dispatch Tests ──

def test_claim_job(stores):
    runner = stores["byoc"].register_runner("r1", "alice")
    stores["byoc"].heartbeat(runner.id)

    run = stores["score"].create_eval_run(stores["commit_id"], "1.0.0")
    success = stores["byoc"].claim_job(run.id, runner.id)
    assert success is True

    # Verify runner is busy
    r = stores["byoc"].get_runner(runner.id)
    assert r.status == RunnerStatus.BUSY


def test_claim_already_claimed(stores):
    r1 = stores["byoc"].register_runner("r1", "alice")
    r2 = stores["byoc"].register_runner("r2", "bob")

    run = stores["score"].create_eval_run(stores["commit_id"], "1.0.0")
    assert stores["byoc"].claim_job(run.id, r1.id) is True
    assert stores["byoc"].claim_job(run.id, r2.id) is False


def test_complete_job(stores):
    runner = stores["byoc"].register_runner("r1", "alice")
    run = stores["score"].create_eval_run(stores["commit_id"], "1.0.0")
    stores["byoc"].claim_job(run.id, runner.id)
    stores["byoc"].complete_job(run.id, runner.id)

    r = stores["byoc"].get_runner(runner.id)
    assert r.status == RunnerStatus.ONLINE
    assert r.jobs_completed == 1


# ── Verification Tests ──

def test_record_verification_match(stores):
    score = stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    result = stores["verification"].record_verification(score.id, 0.951, "verifier-1")
    assert result["matches"] is True
    assert result["verified"] is True


def test_record_verification_mismatch(stores):
    score = stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    result = stores["verification"].record_verification(score.id, 0.50, "verifier-1")
    assert result["matches"] is False


def test_verification_stats(stores):
    stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    stats = stores["verification"].get_verification_stats()
    assert stats["total_scores"] == 1
    assert stats["verified_scores"] == 0


# ── Challenge Tests ──

def test_create_challenge(stores):
    score = stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    challenge = stores["verification"].create_challenge(score.id, "bob", "Suspicious score")
    assert challenge.status == ChallengeStatus.OPEN
    assert challenge.original_score == 0.95


def test_resolve_challenge_upheld(stores):
    score = stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    challenge = stores["verification"].create_challenge(score.id, "bob")
    resolved = stores["verification"].resolve_challenge(challenge.id, 0.949)
    assert resolved.status == ChallengeStatus.UPHELD


def test_resolve_challenge_overturned(stores):
    score = stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    challenge = stores["verification"].create_challenge(score.id, "bob")
    resolved = stores["verification"].resolve_challenge(challenge.id, 0.50)
    assert resolved.status == ChallengeStatus.OVERTURNED


def test_list_challenges(stores):
    score = stores["score"].record_score(stores["commit_id"], "1.0.0", "accuracy", 0.95)
    stores["verification"].create_challenge(score.id, "bob")
    challenges = stores["verification"].list_challenges()
    assert len(challenges) == 1


# ── Anomaly Detection ──

def test_anomaly_detection(stores):
    gs = stores["graph"]
    ss = stores["score"]
    # Create many normal scores and one outlier
    for i in range(10):
        gs.create_branch(f"b{i}", "alice")
        c = gs.create_commit(f"b{i}", "alice", f"c{i}", f"h{i}", parent_ids=[])
        ss.record_score(c.id, "1.0.0", "accuracy", 0.90 + i * 0.001)

    # Add extreme outlier
    gs.create_branch("outlier", "evil")
    c_out = gs.create_commit("outlier", "evil", "sus", "h_out", parent_ids=[])
    ss.record_score(c_out.id, "1.0.0", "accuracy", 99.0)

    anomalies = stores["verification"].detect_anomalies("accuracy")
    assert len(anomalies) >= 1
    assert any(a["author"] == "evil" for a in anomalies)
