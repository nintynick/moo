"""GitSpoke CLI — eval-driven, branch-graph version control."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import click

from gitspoke.db import bootstrap, get_connection
from gitspoke.eval.runner import EvalRunner
from gitspoke.graph.store import GraphStore
from gitspoke.leaderboard.engine import LeaderboardEngine
from gitspoke.models import AuthorType, MetricDirection
from gitspoke.score.store import ScoreStore


def _hash_directory(path: Path) -> str:
    """Compute a hash of all files in a directory for tree_hash."""
    h = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            h.update(str(f.relative_to(path)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


@click.group()
@click.option("--db", envvar="GITSPOKE_DB", default=None, help="Path to SQLite database")
@click.pass_context
def main(ctx: click.Context, db: str | None) -> None:
    """GitSpoke — Eval-driven, branch-graph version control."""
    ctx.ensure_object(dict)
    conn = get_connection(db)
    bootstrap(conn)
    ctx.obj["conn"] = conn
    ctx.obj["db_path"] = db


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize the GitSpoke database."""
    click.echo("GitSpoke database initialized.")
    conn = ctx.obj["conn"]
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    click.echo(f"Database: {path}")


@main.command("branch")
@click.argument("name")
@click.option("--author", required=True, help="Branch creator")
@click.option("--fork-from", default=None, help="Commit ID to fork from")
@click.pass_context
def create_branch(ctx: click.Context, name: str, author: str, fork_from: str | None) -> None:
    """Create a new branch, optionally forking from an existing commit."""
    gs = GraphStore(ctx.obj["conn"])
    if fork_from:
        branch = gs.fork_branch(fork_from, name, author)
        click.echo(f"Branch '{name}' forked from {fork_from[:12]}")
    else:
        branch = gs.create_branch(name, author)
        click.echo(f"Branch '{name}' created")
    click.echo(f"  ID: {branch.id}")


@main.command()
@click.pass_context
def branches(ctx: click.Context) -> None:
    """List all branches."""
    gs = GraphStore(ctx.obj["conn"])
    branch_list = gs.list_branches()
    if not branch_list:
        click.echo("No branches yet. Create one with: gitspoke branch <name> --author <author>")
        return
    for b in branch_list:
        tip = b.tip_commit_id[:12] if b.tip_commit_id else "(empty)"
        fork = f" (forked from {b.forked_from_commit[:12]})" if b.forked_from_commit else ""
        click.echo(f"  {b.name:30s} tip={tip}{fork}  by {b.created_by}")


@main.command()
@click.option("--branch", required=True, help="Target branch name")
@click.option("--author", required=True, help="Commit author")
@click.option("--message", "-m", required=True, help="Commit message")
@click.option("--dir", "work_dir", required=True, type=click.Path(exists=True), help="Directory to commit")
@click.option("--author-type", type=click.Choice(["human", "agent", "hybrid"]), default="human")
@click.pass_context
def push(
    ctx: click.Context,
    branch: str,
    author: str,
    message: str,
    work_dir: str,
    author_type: str,
) -> None:
    """Push a commit from a local directory to a branch."""
    gs = GraphStore(ctx.obj["conn"])
    work_path = Path(work_dir).resolve()
    tree_hash = _hash_directory(work_path)

    commit = gs.create_commit(
        branch_name=branch,
        author=author,
        message=message,
        tree_hash=tree_hash,
        author_type=AuthorType(author_type),
        metadata={"work_dir": str(work_path)},
    )

    click.echo(f"Commit {commit.id[:12]} pushed to '{branch}'")
    click.echo(f"  Author: {author} ({author_type})")
    click.echo(f"  Tree:   {tree_hash[:12]}")


@main.command()
@click.argument("source_commit")
@click.option("--branch", required=True, help="New branch name")
@click.option("--author", required=True, help="Fork author")
@click.pass_context
def fork(ctx: click.Context, source_commit: str, branch: str, author: str) -> None:
    """Fork a new branch from an existing commit."""
    gs = GraphStore(ctx.obj["conn"])
    new_branch = gs.fork_branch(source_commit, branch, author)
    click.echo(f"Forked branch '{branch}' from commit {source_commit[:12]}")
    click.echo(f"  Branch ID: {new_branch.id}")


@main.command("eval")
@click.option("--commit", required=True, help="Commit ID to evaluate")
@click.option("--manifest", default=None, type=click.Path(exists=True), help="Path to gitspoke.yaml")
@click.option("--dir", "work_dir", default=None, type=click.Path(exists=True), help="Working directory")
@click.option("--docker/--no-docker", default=False, help="Use Docker harness")
@click.pass_context
def run_eval(
    ctx: click.Context,
    commit: str,
    manifest: str | None,
    work_dir: str | None,
    docker: bool,
) -> None:
    """Run the eval suite for a commit."""
    conn = ctx.obj["conn"]
    gs = GraphStore(conn)
    ss = ScoreStore(conn)
    runner = EvalRunner(gs, ss, use_docker=docker)

    click.echo(f"Running eval for commit {commit[:12]}...")
    eval_run = runner.run_eval(
        commit_id=commit,
        manifest_path=manifest,
        work_dir=work_dir,
    )

    if eval_run.status.value == "completed":
        click.echo(f"Eval completed successfully (run: {eval_run.id[:12]})")
        # Show scores
        scores = ss.get_scores(commit)
        for s in scores:
            click.echo(f"  {s.metric_name}: {s.value:.6f}")
    else:
        click.echo(f"Eval failed (run: {eval_run.id[:12]})")


@main.command()
@click.option("--metric", required=True, help="Metric name to rank by")
@click.option("--direction", type=click.Choice(["lower-is-better", "higher-is-better"]), required=True)
@click.option("--limit", default=20, help="Number of entries")
@click.option("--branch", "branch_name", default=None, help="Filter to a specific branch")
@click.pass_context
def leaderboard(
    ctx: click.Context,
    metric: str,
    direction: str,
    limit: int,
    branch_name: str | None,
) -> None:
    """Display the leaderboard for a metric."""
    engine = LeaderboardEngine(ctx.obj["conn"])
    d = MetricDirection(direction)

    if branch_name:
        entries = engine.branch_ranking(branch_name, metric, d, limit)
    else:
        entries = engine.global_ranking(metric, d, limit)

    if not entries:
        click.echo("No scores yet.")
        return

    # Header
    click.echo(f"\n  {'Rank':>4}  {'Commit':12}  {'Score':>14}  {'Author':20}  {'Branch':20}")
    click.echo(f"  {'─' * 4}  {'─' * 12}  {'─' * 14}  {'─' * 20}  {'─' * 20}")

    for e in entries:
        click.echo(
            f"  {e.rank:>4}  {e.commit_id[:12]}  {e.best_score:>14.6f}  {e.author:20}  {e.branch_name:20}"
        )
    click.echo()


@main.command()
@click.option("--branch", default=None, help="Branch to show history for")
@click.option("--limit", default=20, help="Number of commits")
@click.pass_context
def log(ctx: click.Context, branch: str | None, limit: int) -> None:
    """Show commit history."""
    gs = GraphStore(ctx.obj["conn"])

    if branch:
        b = gs.get_branch(branch)
        if b is None:
            click.echo(f"Branch '{branch}' not found.")
            return
        if b.tip_commit_id is None:
            click.echo(f"Branch '{branch}' has no commits.")
            return
        commits = gs.get_ancestors(b.tip_commit_id, depth=limit)
    else:
        commits = gs.list_commits(limit=limit)

    if not commits:
        click.echo("No commits yet.")
        return

    for c in commits:
        parents = ", ".join(p[:12] for p in c.parent_ids) if c.parent_ids else "(root)"
        click.echo(f"  {c.id[:12]}  {c.message:40}  by {c.author}  parents: {parents}")


@main.command()
@click.argument("commit_id")
@click.pass_context
def show(ctx: click.Context, commit_id: str) -> None:
    """Show details for a commit including scores."""
    conn = ctx.obj["conn"]
    gs = GraphStore(conn)
    ss = ScoreStore(conn)

    commit = gs.get_commit(commit_id)
    if commit is None:
        click.echo(f"Commit not found: {commit_id}")
        return

    branch = gs.get_branch_for_commit(commit_id)
    branch_name = branch.name if branch else "unknown"

    click.echo(f"Commit:  {commit.id}")
    click.echo(f"Branch:  {branch_name}")
    click.echo(f"Author:  {commit.author} ({commit.author_type.value})")
    click.echo(f"Message: {commit.message}")
    click.echo(f"Parents: {', '.join(commit.parent_ids) or '(root)'}")
    click.echo(f"Tree:    {commit.tree_hash}")
    click.echo(f"Date:    {commit.created_at.isoformat()}")

    scores = ss.get_scores(commit_id)
    if scores:
        click.echo(f"\nScores:")
        for s in scores:
            click.echo(f"  {s.metric_name}: {s.value:.6f}  (eval v{s.eval_version})")

    runs = ss.get_eval_runs_for_commit(commit_id)
    if runs:
        click.echo(f"\nEval Runs:")
        for r in runs:
            click.echo(f"  {r.id[:12]}  status={r.status.value}  manifest_v={r.manifest_version}")


@main.command()
@click.option("--metric", required=True, help="Metric name")
@click.option("--direction", type=click.Choice(["lower-is-better", "higher-is-better"]), required=True)
@click.pass_context
def best_fork_point(ctx: click.Context, metric: str, direction: str) -> None:
    """Find the recommended fork point (best-scoring commit)."""
    engine = LeaderboardEngine(ctx.obj["conn"])
    d = MetricDirection(direction)
    commit_id = engine.best_fork_point(metric, d)
    if commit_id:
        click.echo(f"Recommended fork point: {commit_id}")
    else:
        click.echo("No scored commits found.")


@main.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int) -> None:
    """Start the GitSpoke API server."""
    import uvicorn
    from gitspoke.api import create_app

    app = create_app(ctx.obj.get("db_path"))
    click.echo(f"Starting GitSpoke API at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
