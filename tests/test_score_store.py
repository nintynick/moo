"""Tests for the Score Store."""

from gitspoke.graph.store import GraphStore
from gitspoke.models import MetricDirection
from gitspoke.score.store import ScoreStore


def _make_commit(graph_store: GraphStore, branch: str = "main", msg: str = "c") -> str:
    if graph_store.get_branch(branch) is None:
        graph_store.create_branch(branch, "test")
    c = graph_store.create_commit(branch, "test", msg, f"h_{msg}", parent_ids=[])
    return c.id


def test_record_and_get_score(graph_store, score_store):
    cid = _make_commit(graph_store)
    score = score_store.record_score(cid, "1.0.0", "accuracy", 0.95)
    assert score.value == 0.95
    assert score.metric_name == "accuracy"

    scores = score_store.get_scores(cid)
    assert len(scores) == 1
    assert scores[0].value == 0.95


def test_append_only(graph_store, score_store):
    cid = _make_commit(graph_store)
    score_store.record_score(cid, "1.0.0", "accuracy", 0.90)
    score_store.record_score(cid, "1.0.0", "accuracy", 0.95)

    scores = score_store.get_scores(cid, "accuracy")
    assert len(scores) == 2


def test_get_best_score_higher(graph_store, score_store):
    cid = _make_commit(graph_store)
    score_store.record_score(cid, "1.0.0", "accuracy", 0.90)
    score_store.record_score(cid, "1.0.0", "accuracy", 0.95)

    best = score_store.get_best_score(cid, "accuracy", MetricDirection.HIGHER_IS_BETTER)
    assert best.value == 0.95


def test_get_best_score_lower(graph_store, score_store):
    cid = _make_commit(graph_store)
    score_store.record_score(cid, "1.0.0", "loss", 0.5)
    score_store.record_score(cid, "1.0.0", "loss", 0.3)

    best = score_store.get_best_score(cid, "loss", MetricDirection.LOWER_IS_BETTER)
    assert best.value == 0.3


def test_eval_run_lifecycle(graph_store, score_store):
    from gitspoke.models import EvalRunStatus

    cid = _make_commit(graph_store)
    run = score_store.create_eval_run(cid, "1.0.0")
    assert run.status == EvalRunStatus.PENDING

    score_store.update_eval_run(run.id, EvalRunStatus.RUNNING)
    fetched = score_store.get_eval_run(run.id)
    assert fetched.status == EvalRunStatus.RUNNING
    assert fetched.started_at is not None

    score_store.update_eval_run(run.id, EvalRunStatus.COMPLETED)
    fetched = score_store.get_eval_run(run.id)
    assert fetched.status == EvalRunStatus.COMPLETED
    assert fetched.completed_at is not None


def test_scores_with_constraints(graph_store, score_store):
    cid = _make_commit(graph_store)
    score_store.record_score(cid, "1.0.0", "speed", 100.0, constraints_passed=True)
    score_store.record_score(cid, "1.0.0", "speed", 200.0, constraints_passed=False)

    # Only the passing score should show up in constraint-filtered queries
    all_scores = score_store.get_scores(cid, "speed")
    assert len(all_scores) == 2
