"""GitSpoke API — FastAPI endpoints for the eval-driven platform."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore
from gitspoke.leaderboard.engine import LeaderboardEngine
from gitspoke.models import MetricDirection
from gitspoke.score.store import ScoreStore


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="GitSpoke API",
        description="Eval-driven, branch-graph version control",
        version="0.1.0",
    )

    conn = get_connection(db_path, check_same_thread=False)
    bootstrap(conn)
    graph_store = GraphStore(conn)
    score_store = ScoreStore(conn)
    leaderboard = LeaderboardEngine(conn)

    # ── Leaderboard ──

    @app.get("/leaderboard")
    def get_leaderboard(
        metric: str,
        direction: str = Query(description="lower-is-better or higher-is-better"),
        limit: int = 50,
        branch: str | None = None,
        eval_version: str | None = None,
    ):
        d = MetricDirection(direction)
        if branch:
            entries = leaderboard.branch_ranking(branch, metric, d, limit)
        else:
            entries = leaderboard.global_ranking(metric, d, limit, eval_version)
        return {"entries": [e.model_dump() for e in entries]}

    @app.get("/leaderboard/time-series")
    def get_time_series(
        metric: str,
        direction: str = Query(description="lower-is-better or higher-is-better"),
        limit: int = 100,
    ):
        d = MetricDirection(direction)
        return {"series": leaderboard.time_series(metric, d, limit)}

    @app.get("/leaderboard/best-fork-point")
    def get_best_fork_point(
        metric: str,
        direction: str = Query(description="lower-is-better or higher-is-better"),
    ):
        d = MetricDirection(direction)
        commit_id = leaderboard.best_fork_point(metric, d)
        if commit_id is None:
            raise HTTPException(404, "No scored commits found")
        return {"commit_id": commit_id}

    # ── Branches ──

    @app.get("/branches")
    def list_branches():
        branches = graph_store.list_branches()
        return {"branches": [b.model_dump() for b in branches]}

    @app.get("/branches/{name}")
    def get_branch(name: str):
        branch = graph_store.get_branch(name)
        if branch is None:
            raise HTTPException(404, f"Branch not found: {name}")
        return branch.model_dump()

    # ── Commits ──

    @app.get("/commits/{commit_id}")
    def get_commit(commit_id: str):
        commit = graph_store.get_commit(commit_id)
        if commit is None:
            raise HTTPException(404, f"Commit not found: {commit_id}")
        data = commit.model_dump()
        data["scores"] = [s.model_dump() for s in score_store.get_scores(commit_id)]
        return data

    @app.get("/commits/{commit_id}/scores")
    def get_commit_scores(commit_id: str, metric: str | None = None):
        scores = score_store.get_scores(commit_id, metric)
        return {"scores": [s.model_dump() for s in scores]}

    @app.get("/commits/{commit_id}/ancestors")
    def get_ancestors(commit_id: str, depth: int = 50):
        ancestors = graph_store.get_ancestors(commit_id, depth)
        return {"ancestors": [c.model_dump() for c in ancestors]}

    # ── Eval Runs ──

    @app.get("/commits/{commit_id}/eval-runs")
    def get_eval_runs(commit_id: str):
        runs = score_store.get_eval_runs_for_commit(commit_id)
        return {"eval_runs": [r.model_dump() for r in runs]}

    # ── Health ──

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


# Default app instance for `uvicorn gitspoke.api:app`
app = create_app()
