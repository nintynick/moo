"""Tests for the Eval Runner (using LocalHarness)."""

from pathlib import Path

from gitspoke.eval.runner import EvalRunner
from gitspoke.graph.store import GraphStore
from gitspoke.models import EvalRunStatus
from gitspoke.score.store import ScoreStore


def test_run_eval_success(graph_store: GraphStore, score_store: ScoreStore, sample_work_dir: Path):
    graph_store.create_branch("test", "alice")
    commit = graph_store.create_commit(
        "test", "alice", "test commit", "h1",
        parent_ids=[],
        metadata={"work_dir": str(sample_work_dir)},
    )

    runner = EvalRunner(graph_store, score_store, use_docker=False)
    eval_run = runner.run_eval(commit.id, work_dir=str(sample_work_dir))

    assert eval_run.status == EvalRunStatus.COMPLETED

    scores = score_store.get_scores(commit.id)
    assert len(scores) == 1
    assert scores[0].metric_name == "accuracy"
    assert scores[0].value == 0.95


def test_run_eval_with_manifest_path(
    graph_store: GraphStore, score_store: ScoreStore, sample_work_dir: Path
):
    graph_store.create_branch("test", "alice")
    commit = graph_store.create_commit(
        "test", "alice", "test", "h1", parent_ids=[],
    )

    manifest_path = sample_work_dir / "gitspoke.yaml"
    runner = EvalRunner(graph_store, score_store, use_docker=False)
    eval_run = runner.run_eval(
        commit.id, manifest_path=manifest_path, work_dir=str(sample_work_dir)
    )

    assert eval_run.status == EvalRunStatus.COMPLETED


def test_run_eval_failure(graph_store: GraphStore, score_store: ScoreStore, tmp_path: Path):
    """Eval fails when the command fails."""
    work = tmp_path / "bad_project"
    work.mkdir()
    (work / "eval.py").write_text('import sys; sys.exit(1)\n')
    (work / "gitspoke.yaml").write_text(
        """
name: failing-test
version: 1.0.0
environment:
  image: python:3.11-slim
metrics:
  - name: score
    type: higher-is-better
    command: python eval.py
    weight: 1.0
constraints: []
timeout: 60
"""
    )

    graph_store.create_branch("fail", "alice")
    commit = graph_store.create_commit(
        "fail", "alice", "bad commit", "h1", parent_ids=[],
    )

    runner = EvalRunner(graph_store, score_store, use_docker=False)
    eval_run = runner.run_eval(commit.id, work_dir=str(work))

    assert eval_run.status == EvalRunStatus.FAILED


def test_run_eval_multi_metric(
    graph_store: GraphStore, score_store: ScoreStore, tmp_path: Path
):
    work = tmp_path / "multi"
    work.mkdir()
    (work / "accuracy.py").write_text('print("0.92")\n')
    (work / "speed.py").write_text('print("1500.5")\n')
    (work / "gitspoke.yaml").write_text(
        """
name: multi-metric
version: 1.0.0
environment:
  image: python:3.11-slim
metrics:
  - name: accuracy
    type: higher-is-better
    command: python accuracy.py
    weight: 0.7
  - name: throughput
    type: higher-is-better
    command: python speed.py
    weight: 0.3
constraints: []
timeout: 60
"""
    )

    graph_store.create_branch("multi", "alice")
    commit = graph_store.create_commit(
        "multi", "alice", "multi-metric test", "h1", parent_ids=[],
    )

    runner = EvalRunner(graph_store, score_store, use_docker=False)
    eval_run = runner.run_eval(commit.id, work_dir=str(work))

    assert eval_run.status == EvalRunStatus.COMPLETED

    scores = score_store.get_scores(commit.id)
    assert len(scores) == 2

    metric_names = {s.metric_name for s in scores}
    assert metric_names == {"accuracy", "throughput"}
