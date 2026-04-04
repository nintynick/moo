"""Core data models for GitSpoke."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuthorType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    HYBRID = "hybrid"


class MetricDirection(str, Enum):
    LOWER_IS_BETTER = "lower-is-better"
    HIGHER_IS_BETTER = "higher-is-better"
    TARGET = "target"


class EvalRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Commit ──


class Commit(BaseModel):
    id: str = Field(description="SHA-256 content-addressable hash")
    parent_ids: list[str] = Field(default_factory=list)
    branch_id: str
    author: str
    author_type: AuthorType = AuthorType.HUMAN
    message: str
    tree_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def compute_id(parent_ids: list[str], tree_hash: str, timestamp: str) -> str:
        payload = json.dumps(
            {"parents": sorted(parent_ids), "tree": tree_hash, "ts": timestamp},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


# ── Branch ──


class Branch(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    tip_commit_id: str | None = None
    created_by: str
    forked_from_commit: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Score ──


class Score(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    commit_id: str
    eval_version: str
    metric_name: str
    value: float
    composite_score: float | None = None
    runner_id: str = "local"
    constraints_passed: bool = True
    execution_log_hash: str | None = None
    signature: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Eval Run ──


class EvalRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    commit_id: str
    manifest_version: str
    status: EvalRunStatus = EvalRunStatus.PENDING
    scores: list[Score] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


# ── Leaderboard ──


class LeaderboardEntry(BaseModel):
    rank: int
    commit_id: str
    branch_name: str
    author: str
    metric_name: str
    best_score: float
    run_count: int = 1


# ── Manifest models ──


class MetricSpec(BaseModel):
    name: str
    type: MetricDirection
    command: str
    weight: float = 1.0


class ConstraintSpec(BaseModel):
    name: str
    command: str | None = None
    value: str | None = None
    type: str  # "must-pass" or "resource-limit"


class ResourceSpec(BaseModel):
    gpu: str | None = None
    memory: str | None = None
    cpus: int | None = None


class EnvironmentSpec(BaseModel):
    image: str
    gpu: bool = False


class EvalManifest(BaseModel):
    name: str
    version: str
    environment: EnvironmentSpec
    build: list[str] = Field(default_factory=list)
    metrics: list[MetricSpec]
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    timeout: int = 600
    resources: dict[str, ResourceSpec] = Field(default_factory=dict)

    @property
    def major_version(self) -> int:
        return int(self.version.split(".")[0])

    @property
    def weighted_metrics(self) -> list[MetricSpec]:
        return [m for m in self.metrics if m.weight > 0]

    @property
    def holdout_metrics(self) -> list[MetricSpec]:
        return [m for m in self.metrics if m.weight == 0]
