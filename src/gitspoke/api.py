"""GitSpoke API — FastAPI endpoints for the eval-driven platform."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from gitspoke.byoc.gateway import BYOCGateway
from gitspoke.byoc.verification import VerificationPipeline
from gitspoke.db import bootstrap, get_connection
from gitspoke.events.bus import EventBus
from gitspoke.graph.lineage import LineageDetector
from gitspoke.graph.repo import RepoStore
from gitspoke.graph.store import GraphStore
from gitspoke.identity.reputation import ReputationEngine
from gitspoke.identity.store import IdentityStore
from gitspoke.leaderboard.engine import LeaderboardEngine
from gitspoke.models import (
    AuthorType,
    EventType,
    MetricDirection,
    RunnerStatus,
)
from gitspoke.score.store import ScoreStore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="GitSpoke API",
        description="Eval-driven, branch-graph version control",
        version="0.2.0",
    )

    conn = get_connection(db_path, check_same_thread=False)
    bootstrap(conn)

    graph_store = GraphStore(conn)
    score_store = ScoreStore(conn)
    leaderboard = LeaderboardEngine(conn)
    identity_store = IdentityStore(conn)
    repo_store = RepoStore(conn)
    byoc = BYOCGateway(conn)
    verification = VerificationPipeline(conn)
    event_bus = EventBus(conn)
    lineage = LineageDetector(conn)
    reputation = ReputationEngine(conn)

    # ── Static files / Web UI ──
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return index_path.read_text()
        return "<h1>GitSpoke API</h1><p>Web UI not built. Use the API directly.</p>"

    # ═══════════════════════════════════════════
    # Leaderboard
    # ═══════════════════════════════════════════

    @app.get("/api/leaderboard")
    def get_leaderboard(
        metric: str,
        direction: str = Query(description="lower-is-better or higher-is-better"),
        limit: int = 50,
        branch: str | None = None,
        lineage_group: str | None = None,
        eval_version: str | None = None,
    ):
        d = MetricDirection(direction)
        if branch:
            entries = leaderboard.branch_ranking(branch, metric, d, limit)
        elif lineage_group:
            entries = leaderboard.lineage_ranking(lineage_group, metric, d, limit)
        else:
            entries = leaderboard.global_ranking(metric, d, limit, eval_version)
        return {"entries": [e.model_dump() for e in entries]}

    @app.get("/api/leaderboard/time-series")
    def get_time_series(
        metric: str,
        direction: str = Query(description="lower-is-better or higher-is-better"),
        limit: int = 100,
    ):
        d = MetricDirection(direction)
        return {"series": leaderboard.time_series(metric, d, limit)}

    @app.get("/api/leaderboard/best-fork-point")
    def get_best_fork_point(
        metric: str,
        direction: str = Query(description="lower-is-better or higher-is-better"),
    ):
        d = MetricDirection(direction)
        commit_id = leaderboard.best_fork_point(metric, d)
        if commit_id is None:
            raise HTTPException(404, "No scored commits found")
        return {"commit_id": commit_id}

    # ═══════════════════════════════════════════
    # Repositories
    # ═══════════════════════════════════════════

    @app.post("/api/repos")
    def create_repo(body: dict):
        repo = repo_store.create_repo(
            name=body["name"],
            owner_id=body["owner_id"],
            description=body.get("description", ""),
        )
        return repo.model_dump()

    @app.get("/api/repos")
    def list_repos(limit: int = 50):
        repos = repo_store.list_repos(limit)
        return {"repos": [r.model_dump() for r in repos]}

    @app.get("/api/repos/{repo_id}")
    def get_repo(repo_id: str):
        repo = repo_store.get_repo(repo_id)
        if repo is None:
            raise HTTPException(404, f"Repository not found: {repo_id}")
        return repo.model_dump()

    # ═══════════════════════════════════════════
    # Branches
    # ═══════════════════════════════════════════

    @app.get("/api/branches")
    def list_branches(repo_id: str | None = None):
        branches = graph_store.list_branches(repo_id)
        return {"branches": [b.model_dump() for b in branches]}

    @app.get("/api/branches/{name}")
    def get_branch(name: str, repo_id: str = "default"):
        branch = graph_store.get_branch(name, repo_id)
        if branch is None:
            raise HTTPException(404, f"Branch not found: {name}")
        return branch.model_dump()

    # ═══════════════════════════════════════════
    # Commits
    # ═══════════════════════════════════════════

    @app.get("/api/commits/{commit_id}")
    def get_commit(commit_id: str):
        commit = graph_store.get_commit(commit_id)
        if commit is None:
            raise HTTPException(404, f"Commit not found: {commit_id}")
        data = commit.model_dump()
        data["scores"] = [s.model_dump() for s in score_store.get_scores(commit_id)]
        return data

    @app.get("/api/commits/{commit_id}/scores")
    def get_commit_scores(commit_id: str, metric: str | None = None):
        scores = score_store.get_scores(commit_id, metric)
        return {"scores": [s.model_dump() for s in scores]}

    @app.get("/api/commits/{commit_id}/ancestors")
    def get_ancestors(commit_id: str, depth: int = 50):
        ancestors = graph_store.get_ancestors(commit_id, depth)
        return {"ancestors": [c.model_dump() for c in ancestors]}

    @app.get("/api/commits/{commit_id}/attribution")
    def get_attribution(commit_id: str, depth: int = 20):
        chain = reputation.compute_attribution_chain(commit_id, depth)
        return {"attribution": chain}

    # ═══════════════════════════════════════════
    # Graph Visualization
    # ═══════════════════════════════════════════

    @app.get("/api/graph")
    def get_graph(repo_id: str = "default", limit: int = 200):
        return graph_store.get_graph_data(repo_id, limit)

    # ═══════════════════════════════════════════
    # Eval Runs
    # ═══════════════════════════════════════════

    @app.get("/api/commits/{commit_id}/eval-runs")
    def get_eval_runs(commit_id: str):
        runs = score_store.get_eval_runs_for_commit(commit_id)
        return {"eval_runs": [r.model_dump() for r in runs]}

    # ═══════════════════════════════════════════
    # Agent-Specific Endpoints
    # ═══════════════════════════════════════════

    @app.post("/api/repos/{repo_id}/experiment")
    def create_experiment(repo_id: str, body: dict):
        """Atomic: fork → push → queue eval. One iteration of the autoresearch loop."""
        source_commit = body["source_commit_id"]
        branch_name = body["branch_name"]
        author = body["author"]
        message = body.get("message", "experiment")
        tree_hash = body["tree_hash"]
        metadata = body.get("metadata", {})

        # Fork
        branch = graph_store.fork_branch(source_commit, branch_name, author, repo_id)

        # Push commit
        commit = graph_store.create_commit(
            branch_name=branch_name,
            author=author,
            message=message,
            tree_hash=tree_hash,
            metadata=metadata,
            repo_id=repo_id,
        )

        # Queue eval
        run = score_store.create_eval_run(commit.id, "1.0.0")

        event_bus.emit(repo_id, EventType.COMMIT_PUSHED, {
            "commit_id": commit.id,
            "branch": branch_name,
            "author": author,
        })

        return {
            "branch": branch.model_dump(),
            "commit": commit.model_dump(),
            "eval_run": run.model_dump(),
        }

    @app.get("/api/repos/{repo_id}/research-directions")
    def get_research_directions(repo_id: str):
        """Suggested improvement areas — metrics with room for improvement."""
        # Analyze score distributions to suggest where gains are possible
        metrics = conn.execute(
            """
            SELECT metric_name,
                   MIN(value) as min_val,
                   MAX(value) as max_val,
                   AVG(value) as avg_val,
                   COUNT(DISTINCT commit_id) as commit_count
            FROM scores s
            JOIN commits c ON s.commit_id = c.id
            WHERE c.repo_id = ? AND s.constraints_passed = 1
            GROUP BY metric_name
            """,
            (repo_id,),
        ).fetchall()

        directions = []
        for m in metrics:
            spread = m["max_val"] - m["min_val"]
            directions.append({
                "metric": m["metric_name"],
                "min": m["min_val"],
                "max": m["max_val"],
                "average": m["avg_val"],
                "spread": spread,
                "commits_evaluated": m["commit_count"],
                "opportunity": "high" if spread > 0.1 else "medium" if spread > 0.01 else "low",
            })

        return {"directions": directions}

    # ═══════════════════════════════════════════
    # Identities
    # ═══════════════════════════════════════════

    @app.post("/api/identities")
    def create_identity(body: dict):
        identity = identity_store.create_identity(
            display_name=body["display_name"],
            identity_type=AuthorType(body.get("identity_type", "human")),
            public_key=body.get("public_key"),
            organization=body.get("organization"),
            agent_model=body.get("agent_model"),
            agent_version=body.get("agent_version"),
        )
        return identity.model_dump()

    @app.get("/api/identities")
    def list_identities(limit: int = 50):
        identities = identity_store.list_identities(limit)
        return {"identities": [i.model_dump() for i in identities]}

    @app.get("/api/identities/{identity_id}")
    def get_identity(identity_id: str):
        identity = identity_store.get_identity(identity_id)
        if identity is None:
            raise HTTPException(404, f"Identity not found: {identity_id}")
        return identity.model_dump()

    @app.get("/api/identities/{identity_id}/reputation")
    def get_reputation(identity_id: str):
        identity = identity_store.update_reputation(identity_id)
        if identity is None:
            raise HTTPException(404, f"Identity not found: {identity_id}")
        return {
            "identity_id": identity.id,
            "display_name": identity.display_name,
            "reputation_score": identity.reputation_score,
            "trust_score": identity.trust_score,
            "leaderboard_positions": identity.leaderboard_positions,
            "upstream_credits": identity.upstream_credits,
            "verification_match_rate": identity.verification_match_rate,
            "total_commits": identity.total_commits,
        }

    # ═══════════════════════════════════════════
    # Runners (BYOC)
    # ═══════════════════════════════════════════

    @app.post("/api/runners")
    def register_runner(body: dict):
        runner = byoc.register_runner(
            name=body["name"],
            owner_id=body["owner_id"],
            gpu_type=body.get("gpu_type"),
            gpu_memory=body.get("gpu_memory"),
            cpu_cores=body.get("cpu_cores"),
            memory=body.get("memory"),
            public_key=body.get("public_key"),
        )
        event_bus.emit("system", EventType.RUNNER_REGISTERED, {
            "runner_id": runner.id,
            "name": runner.name,
            "owner_id": runner.owner_id,
        })
        return runner.model_dump()

    @app.get("/api/runners")
    def list_runners(owner_id: str | None = None):
        runners = byoc.list_runners(owner_id)
        return {"runners": [r.model_dump() for r in runners]}

    @app.get("/api/runners/{runner_id}")
    def get_runner(runner_id: str):
        runner = byoc.get_runner(runner_id)
        if runner is None:
            raise HTTPException(404, f"Runner not found: {runner_id}")
        return runner.model_dump()

    @app.post("/api/runners/{runner_id}/heartbeat")
    def runner_heartbeat(runner_id: str):
        runner = byoc.heartbeat(runner_id)
        if runner is None:
            raise HTTPException(404, f"Runner not found: {runner_id}")
        return runner.model_dump()

    @app.get("/api/runners/{runner_id}/jobs")
    def get_runner_jobs(runner_id: str):
        jobs = byoc.get_pending_jobs(runner_id)
        return {"jobs": jobs}

    @app.post("/api/runners/{runner_id}/claim/{eval_run_id}")
    def claim_job(runner_id: str, eval_run_id: str):
        success = byoc.claim_job(eval_run_id, runner_id)
        if not success:
            raise HTTPException(409, "Job already claimed or not pending")
        return {"claimed": True, "eval_run_id": eval_run_id}

    # ═══════════════════════════════════════════
    # Verification & Challenges
    # ═══════════════════════════════════════════

    @app.get("/api/verification/stats")
    def verification_stats():
        return verification.get_verification_stats()

    @app.get("/api/verification/queue")
    def verification_queue(limit: int = 10):
        score_ids = verification.select_for_verification(limit)
        return {"score_ids": score_ids}

    @app.post("/api/verification/record")
    def record_verification(body: dict):
        result = verification.record_verification(
            original_score_id=body["score_id"],
            verification_value=body["value"],
            verifier_runner_id=body["runner_id"],
        )
        return result

    @app.post("/api/challenges")
    def create_challenge(body: dict):
        challenge = verification.create_challenge(
            score_id=body["score_id"],
            challenger_id=body["challenger_id"],
            reason=body.get("reason", ""),
        )
        event_bus.emit("system", EventType.CHALLENGE_OPENED, {
            "challenge_id": challenge.id,
            "score_id": challenge.score_id,
            "challenger_id": challenge.challenger_id,
        })
        return challenge.model_dump()

    @app.get("/api/challenges")
    def list_challenges(
        commit_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ):
        challenges = verification.list_challenges(commit_id, status, limit)
        return {"challenges": [c.model_dump() for c in challenges]}

    @app.get("/api/challenges/{challenge_id}")
    def get_challenge(challenge_id: str):
        challenge = verification.get_challenge(challenge_id)
        if challenge is None:
            raise HTTPException(404, f"Challenge not found: {challenge_id}")
        return challenge.model_dump()

    @app.post("/api/challenges/{challenge_id}/resolve")
    def resolve_challenge(challenge_id: str, body: dict):
        challenge = verification.resolve_challenge(
            challenge_id=challenge_id,
            verification_score=body["verification_score"],
        )
        event_bus.emit("system", EventType.CHALLENGE_RESOLVED, {
            "challenge_id": challenge.id,
            "status": challenge.status.value,
        })
        return challenge.model_dump()

    @app.get("/api/anomalies")
    def detect_anomalies(metric: str, threshold: float = 3.0):
        anomalies = verification.detect_anomalies(metric, threshold)
        return {"anomalies": anomalies}

    # ═══════════════════════════════════════════
    # Lineage Groups
    # ═══════════════════════════════════════════

    @app.get("/api/repos/{repo_id}/lineage-groups")
    def list_lineage_groups(repo_id: str):
        groups = lineage.list_lineage_groups(repo_id)
        return {"lineage_groups": [g.model_dump() for g in groups]}

    @app.post("/api/repos/{repo_id}/lineage-groups")
    def create_lineage_group(repo_id: str, body: dict):
        group = lineage.create_lineage_group(
            repo_id=repo_id,
            name=body["name"],
            description=body.get("description", ""),
            root_commit_ids=body.get("root_commit_ids", []),
        )
        return group.model_dump()

    @app.post("/api/repos/{repo_id}/lineage-groups/detect")
    def detect_lineage_groups(repo_id: str, min_depth: int = 3):
        groups = lineage.detect_lineage_groups(repo_id, min_depth)
        return {"detected": len(groups), "lineage_groups": [g.model_dump() for g in groups]}

    # ═══════════════════════════════════════════
    # Events & Webhooks
    # ═══════════════════════════════════════════

    @app.get("/api/events")
    def list_events(
        repo_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ):
        events = event_bus.list_events(repo_id, event_type, limit)
        return {"events": [e.model_dump() for e in events]}

    @app.post("/api/webhooks")
    def register_webhook(body: dict):
        webhook = event_bus.register_webhook(
            repo_id=body["repo_id"],
            url=body["url"],
            events=body.get("events", []),
            created_by=body["created_by"],
            secret=body.get("secret"),
        )
        return webhook.model_dump()

    @app.get("/api/webhooks")
    def list_webhooks(repo_id: str):
        webhooks = event_bus.list_webhooks(repo_id)
        return {"webhooks": [w.model_dump() for w in webhooks]}

    @app.delete("/api/webhooks/{webhook_id}")
    def delete_webhook(webhook_id: str):
        event_bus.delete_webhook(webhook_id)
        return {"deleted": True}

    # ═══════════════════════════════════════════
    # Health
    # ═══════════════════════════════════════════

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    # ── Backward compatibility aliases ──
    @app.get("/leaderboard")
    def leaderboard_compat(
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
    def time_series_compat(metric: str, direction: str, limit: int = 100):
        d = MetricDirection(direction)
        return {"series": leaderboard.time_series(metric, d, limit)}

    @app.get("/leaderboard/best-fork-point")
    def fork_point_compat(metric: str, direction: str):
        d = MetricDirection(direction)
        cid = leaderboard.best_fork_point(metric, d)
        if cid is None:
            raise HTTPException(404, "No scored commits found")
        return {"commit_id": cid}

    @app.get("/branches")
    def branches_compat():
        return {"branches": [b.model_dump() for b in graph_store.list_branches()]}

    @app.get("/branches/{name}")
    def branch_compat(name: str):
        b = graph_store.get_branch(name)
        if b is None:
            raise HTTPException(404, f"Branch not found: {name}")
        return b.model_dump()

    @app.get("/commits/{commit_id}")
    def commit_compat(commit_id: str):
        c = graph_store.get_commit(commit_id)
        if c is None:
            raise HTTPException(404, f"Commit not found: {commit_id}")
        data = c.model_dump()
        data["scores"] = [s.model_dump() for s in score_store.get_scores(commit_id)]
        return data

    @app.get("/commits/{commit_id}/scores")
    def scores_compat(commit_id: str, metric: str | None = None):
        return {"scores": [s.model_dump() for s in score_store.get_scores(commit_id, metric)]}

    @app.get("/commits/{commit_id}/eval-runs")
    def eval_runs_compat(commit_id: str):
        runs = score_store.get_eval_runs_for_commit(commit_id)
        return {"eval_runs": [r.model_dump() for r in runs]}

    @app.get("/commits/{commit_id}/ancestors")
    def ancestors_compat(commit_id: str, depth: int = 50):
        return {"ancestors": [c.model_dump() for c in graph_store.get_ancestors(commit_id, depth)]}

    @app.get("/health")
    def health_compat():
        return {"status": "ok", "version": "0.2.0"}

    return app


def _get_app():
    """Lazy default app for `uvicorn gitspoke.api:app`."""
    return create_app()

class _LazyApp:
    """Proxy that creates the app on first ASGI call."""
    def __init__(self):
        self._app = None
    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = _get_app()
        await self._app(scope, receive, send)

app = _LazyApp()
