"""Eval Runner — orchestrates eval execution and score recording."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gitspoke.eval.harness import DockerHarness, HarnessResult, LocalHarness
from gitspoke.graph.store import GraphStore
from gitspoke.manifest import load_manifest
from gitspoke.models import EvalManifest, EvalRun, EvalRunStatus
from gitspoke.score.store import ScoreStore


class EvalRunner:
    def __init__(
        self,
        graph_store: GraphStore,
        score_store: ScoreStore,
        use_docker: bool = False,
    ) -> None:
        self.graph_store = graph_store
        self.score_store = score_store
        self.harness = DockerHarness() if use_docker else LocalHarness()

    def run_eval(
        self,
        commit_id: str,
        manifest_path: str | Path | None = None,
        manifest: EvalManifest | None = None,
        work_dir: str | Path | None = None,
    ) -> EvalRun:
        """Run the eval suite for a commit and record scores."""
        commit = self.graph_store.get_commit(commit_id)
        if commit is None:
            raise ValueError(f"Commit not found: {commit_id}")

        # Load manifest
        if manifest is None:
            if manifest_path is None:
                # Try to find it in the work_dir or commit metadata
                if work_dir:
                    manifest_path = Path(work_dir) / "gitspoke.yaml"
                elif "work_dir" in commit.metadata:
                    manifest_path = Path(commit.metadata["work_dir"]) / "gitspoke.yaml"
                else:
                    raise ValueError("No manifest path provided and none found in commit metadata")
            manifest = load_manifest(manifest_path)

        # Resolve work_dir
        if work_dir is None:
            work_dir = commit.metadata.get("work_dir")
            if work_dir is None:
                raise ValueError("No work_dir provided and none in commit metadata")

        # Create eval run record
        eval_run = self.score_store.create_eval_run(commit_id, manifest.version)
        self.score_store.update_eval_run(eval_run.id, EvalRunStatus.RUNNING)

        # Execute
        result: HarnessResult = self.harness.execute(work_dir, manifest)

        if not result.success:
            self.score_store.update_eval_run(eval_run.id, EvalRunStatus.FAILED)
            eval_run.status = EvalRunStatus.FAILED
            return eval_run

        # Compute composite score
        composite = self._compute_composite(manifest, result.metric_values)

        # Record individual metric scores
        for metric in manifest.metrics:
            if metric.name in result.metric_values:
                self.score_store.record_score(
                    commit_id=commit_id,
                    eval_version=manifest.version,
                    metric_name=metric.name,
                    value=result.metric_values[metric.name],
                    composite_score=composite if metric.weight > 0 else None,
                    constraints_passed=True,
                    execution_log_hash=result.log_hash,
                )

        # Mark completed
        self.score_store.update_eval_run(
            eval_run.id,
            EvalRunStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        eval_run.status = EvalRunStatus.COMPLETED
        return eval_run

    @staticmethod
    def _compute_composite(
        manifest: EvalManifest, values: dict[str, float]
    ) -> float:
        """Compute weighted composite score from individual metrics."""
        weighted = manifest.weighted_metrics
        if not weighted:
            return 0.0

        total_weight = sum(m.weight for m in weighted)
        if total_weight == 0:
            return 0.0

        composite = 0.0
        for m in weighted:
            if m.name in values:
                composite += (m.weight / total_weight) * values[m.name]
        return composite
