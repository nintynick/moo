"""Tests for the Leaderboard Engine."""

from gitspoke.graph.store import GraphStore
from gitspoke.leaderboard.engine import LeaderboardEngine
from gitspoke.models import MetricDirection
from gitspoke.score.store import ScoreStore


def _setup_scored_commits(graph_store: GraphStore, score_store: ScoreStore):
    """Create multiple branches with scored commits."""
    graph_store.create_branch("alice-branch", "alice")
    graph_store.create_branch("bob-branch", "bob")

    c1 = graph_store.create_commit("alice-branch", "alice", "attempt 1", "h1", parent_ids=[])
    c2 = graph_store.create_commit("alice-branch", "alice", "attempt 2", "h2")
    c3 = graph_store.create_commit("bob-branch", "bob", "bob's try", "h3", parent_ids=[])

    score_store.record_score(c1.id, "1.0.0", "accuracy", 0.85)
    score_store.record_score(c2.id, "1.0.0", "accuracy", 0.92)
    score_store.record_score(c3.id, "1.0.0", "accuracy", 0.88)

    return c1, c2, c3


def test_global_ranking_higher_is_better(graph_store, score_store, leaderboard_engine):
    c1, c2, c3 = _setup_scored_commits(graph_store, score_store)

    ranking = leaderboard_engine.global_ranking("accuracy", MetricDirection.HIGHER_IS_BETTER)
    assert len(ranking) == 3
    assert ranking[0].commit_id == c2.id  # 0.92
    assert ranking[0].rank == 1
    assert ranking[1].commit_id == c3.id  # 0.88
    assert ranking[2].commit_id == c1.id  # 0.85


def test_global_ranking_lower_is_better(graph_store, score_store, leaderboard_engine):
    graph_store.create_branch("main", "alice")
    c1 = graph_store.create_commit("main", "alice", "a", "h1", parent_ids=[])
    c2 = graph_store.create_commit("main", "alice", "b", "h2")

    score_store.record_score(c1.id, "1.0.0", "loss", 0.5)
    score_store.record_score(c2.id, "1.0.0", "loss", 0.3)

    ranking = leaderboard_engine.global_ranking("loss", MetricDirection.LOWER_IS_BETTER)
    assert ranking[0].commit_id == c2.id  # 0.3 is better
    assert ranking[0].best_score == 0.3


def test_branch_ranking(graph_store, score_store, leaderboard_engine):
    c1, c2, c3 = _setup_scored_commits(graph_store, score_store)

    ranking = leaderboard_engine.branch_ranking(
        "alice-branch", "accuracy", MetricDirection.HIGHER_IS_BETTER
    )
    assert len(ranking) == 2  # Only alice's commits
    assert ranking[0].commit_id == c2.id


def test_best_fork_point(graph_store, score_store, leaderboard_engine):
    _setup_scored_commits(graph_store, score_store)

    best = leaderboard_engine.best_fork_point("accuracy", MetricDirection.HIGHER_IS_BETTER)
    assert best is not None


def test_time_series(graph_store, score_store, leaderboard_engine):
    graph_store.create_branch("main", "alice")
    c1 = graph_store.create_commit("main", "alice", "a", "h1", parent_ids=[])
    c2 = graph_store.create_commit("main", "alice", "b", "h2")
    c3 = graph_store.create_commit("main", "alice", "c", "h3")

    score_store.record_score(c1.id, "1.0.0", "accuracy", 0.80)
    score_store.record_score(c2.id, "1.0.0", "accuracy", 0.75)  # Regression
    score_store.record_score(c3.id, "1.0.0", "accuracy", 0.90)  # New best

    series = leaderboard_engine.time_series("accuracy", MetricDirection.HIGHER_IS_BETTER)
    # Should only show improvements: 0.80, 0.90
    assert len(series) == 2
    assert series[0]["score"] == 0.80
    assert series[1]["score"] == 0.90


def test_empty_leaderboard(leaderboard_engine):
    ranking = leaderboard_engine.global_ranking("accuracy", MetricDirection.HIGHER_IS_BETTER)
    assert ranking == []


def test_best_fork_point_empty(leaderboard_engine):
    assert leaderboard_engine.best_fork_point("accuracy", MetricDirection.HIGHER_IS_BETTER) is None
