"""Tests for the GitSpoke CLI."""

from pathlib import Path

from click.testing import CliRunner

from gitspoke.cli import main
from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore


def test_init(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    result = runner.invoke(main, ["--db", db, "init"])
    assert result.exit_code == 0
    assert "initialized" in result.output.lower()


def test_branch_and_push(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    work = tmp_path / "project"
    work.mkdir()
    (work / "main.py").write_text('print("hello")\n')

    result = runner.invoke(main, ["--db", db, "branch", "exp-1", "--author", "alice"])
    assert result.exit_code == 0
    assert "exp-1" in result.output

    result = runner.invoke(main, [
        "--db", db, "push",
        "--branch", "exp-1",
        "--author", "alice",
        "-m", "initial",
        "--dir", str(work),
    ])
    assert result.exit_code == 0
    assert "pushed" in result.output.lower()


def test_branches_list(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    runner.invoke(main, ["--db", db, "branch", "a", "--author", "alice"])
    runner.invoke(main, ["--db", db, "branch", "b", "--author", "bob"])

    result = runner.invoke(main, ["--db", db, "branches"])
    assert result.exit_code == 0
    assert "a" in result.output
    assert "b" in result.output


def _get_commit_id(db: str, branch: str) -> str:
    """Helper to get full commit ID from the database."""
    conn = get_connection(db)
    gs = GraphStore(conn)
    b = gs.get_branch(branch)
    conn.close()
    return b.tip_commit_id


def test_fork_and_log(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    work = tmp_path / "project"
    work.mkdir()
    (work / "main.py").write_text("x = 1\n")

    runner.invoke(main, ["--db", db, "branch", "main", "--author", "alice"])
    runner.invoke(main, [
        "--db", db, "push",
        "--branch", "main", "--author", "alice", "-m", "root",
        "--dir", str(work),
    ])

    commit_id = _get_commit_id(db, "main")
    assert commit_id is not None

    # Fork
    result = runner.invoke(main, [
        "--db", db, "fork", commit_id,
        "--branch", "experiment", "--author", "bob",
    ])
    assert result.exit_code == 0
    assert "forked" in result.output.lower()

    # Log
    result = runner.invoke(main, ["--db", db, "log", "--branch", "main"])
    assert result.exit_code == 0
    assert "root" in result.output


def test_eval_and_leaderboard(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    work = tmp_path / "project"
    work.mkdir()
    (work / "eval.py").write_text('print("0.95")\n')
    (work / "gitspoke.yaml").write_text("""
name: test
version: 1.0.0
environment:
  image: python:3.11-slim
metrics:
  - name: accuracy
    type: higher-is-better
    command: python eval.py
    weight: 1.0
constraints: []
timeout: 60
""")

    runner.invoke(main, ["--db", db, "branch", "exp", "--author", "alice"])
    runner.invoke(main, [
        "--db", db, "push",
        "--branch", "exp", "--author", "alice", "-m", "test commit",
        "--dir", str(work),
    ])

    commit_id = _get_commit_id(db, "exp")

    # Run eval
    eval_result = runner.invoke(main, [
        "--db", db, "eval",
        "--commit", commit_id,
        "--dir", str(work),
    ])
    assert eval_result.exit_code == 0
    assert "completed" in eval_result.output.lower() or "0.95" in eval_result.output

    # Check leaderboard
    lb_result = runner.invoke(main, [
        "--db", db, "leaderboard",
        "--metric", "accuracy",
        "--direction", "higher-is-better",
    ])
    assert lb_result.exit_code == 0
    assert "0.95" in lb_result.output


def test_show_commit(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    work = tmp_path / "project"
    work.mkdir()
    (work / "x.py").write_text("1\n")

    runner.invoke(main, ["--db", db, "branch", "b", "--author", "alice"])
    runner.invoke(main, [
        "--db", db, "push",
        "--branch", "b", "--author", "alice", "-m", "test",
        "--dir", str(work),
    ])

    commit_id = _get_commit_id(db, "b")

    result = runner.invoke(main, ["--db", db, "show", commit_id])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_empty_leaderboard(tmp_path):
    runner = CliRunner()
    db = str(tmp_path / "test.db")
    result = runner.invoke(main, [
        "--db", db, "leaderboard",
        "--metric", "accuracy",
        "--direction", "higher-is-better",
    ])
    assert result.exit_code == 0
    assert "no scores" in result.output.lower()
