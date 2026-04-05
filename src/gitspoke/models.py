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


class RunnerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class ChallengeStatus(str, Enum):
    OPEN = "open"
    VERIFYING = "verifying"
    UPHELD = "upheld"
    OVERTURNED = "overturned"
    DISMISSED = "dismissed"


class EventType(str, Enum):
    COMMIT_PUSHED = "commit.pushed"
    EVAL_STARTED = "eval.started"
    EVAL_COMPLETED = "eval.completed"
    EVAL_FAILED = "eval.failed"
    SCORE_RECORDED = "score.recorded"
    LEADERBOARD_CHANGED = "leaderboard.changed"
    BRANCH_CREATED = "branch.created"
    BRANCH_FORKED = "branch.forked"
    CHALLENGE_OPENED = "challenge.opened"
    CHALLENGE_RESOLVED = "challenge.resolved"
    VERIFICATION_COMPLETED = "verification.completed"
    RUNNER_REGISTERED = "runner.registered"
    RUNNER_STATUS_CHANGED = "runner.status_changed"


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
    repo_id: str = "default"
    lineage_group_id: str | None = None
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
    repo_id: str = "default"
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
    verified: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Eval Run ──


class EvalRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    commit_id: str
    manifest_version: str
    status: EvalRunStatus = EvalRunStatus.PENDING
    runner_id: str | None = None
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
    verified: bool = False
    lineage_group: str | None = None


# ── Repository ──


class Repository(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    description: str = ""
    owner_id: str
    manifest_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Identity ──


class Identity(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    display_name: str
    identity_type: AuthorType = AuthorType.HUMAN
    public_key: str | None = None
    organization: str | None = None
    agent_model: str | None = None
    agent_version: str | None = None
    reputation_score: float = 0.0
    trust_score: float = 1.0
    total_commits: int = 0
    leaderboard_positions: int = 0
    upstream_credits: float = 0.0
    verification_match_rate: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Runner (BYOC) ──


class Runner(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    owner_id: str
    status: RunnerStatus = RunnerStatus.OFFLINE
    gpu_type: str | None = None
    gpu_memory: str | None = None
    cpu_cores: int | None = None
    memory: str | None = None
    public_key: str | None = None
    trusted: bool = False
    last_heartbeat: datetime | None = None
    jobs_completed: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



# ── Lineage Group ──


class LineageGroup(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    repo_id: str
    name: str
    description: str = ""
    root_commit_ids: list[str] = Field(default_factory=list)
    auto_detected: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Challenge ──


class Challenge(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    score_id: str
    commit_id: str
    challenger_id: str
    reason: str = ""
    status: ChallengeStatus = ChallengeStatus.OPEN
    verification_score: float | None = None
    original_score: float | None = None
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Webhook ──


class Webhook(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    repo_id: str
    url: str
    events: list[str] = Field(default_factory=list)
    secret: str | None = None
    active: bool = True
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Event ──


class Event(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    repo_id: str
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
