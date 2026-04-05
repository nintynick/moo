"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from gitspoke.db import bootstrap, get_connection
from gitspoke.graph.store import GraphStore
from gitspoke.leaderboard.engine import LeaderboardEngine
from gitspoke.score.store import ScoreStore


@pytest.fixture
def db_conn():
    """In-memory SQLite database for tests."""
    conn = get_connection(":memory:")
    bootstrap(conn)
    yield conn
    conn.close()


@pytest.fixture
def graph_store(db_conn):
    return GraphStore(db_conn)


@pytest.fixture
def score_store(db_conn):
    return ScoreStore(db_conn)


@pytest.fixture
def leaderboard_engine(db_conn):
    return LeaderboardEngine(db_conn)


@pytest.fixture
def sample_manifest_path(tmp_path):
    manifest = tmp_path / "gitspoke.yaml"
    manifest.write_text(
        """
name: test-suite
version: 1.0.0

environment:
  image: python:3.11-slim

metrics:
  - name: accuracy
    type: higher-is-better
    command: echo 0.95
    weight: 1.0

constraints: []
timeout: 60
"""
    )
    return manifest


@pytest.fixture
def sample_work_dir(tmp_path):
    """Create a minimal project directory for eval testing."""
    work = tmp_path / "project"
    work.mkdir()
    (work / "eval.py").write_text('print("0.95")\n')
    (work / "gitspoke.yaml").write_text(
        """
name: test-suite
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
"""
    )
    return work
