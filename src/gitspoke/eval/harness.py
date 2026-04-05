"""Eval harnesses — Docker and local subprocess execution."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from gitspoke.models import EvalManifest


class HarnessResult:
    def __init__(self, metric_values: dict[str, float], log: str, success: bool) -> None:
        self.metric_values = metric_values
        self.log = log
        self.log_hash = hashlib.sha256(log.encode()).hexdigest()
        self.success = success


class LocalHarness:
    """Runs eval commands via subprocess — no Docker required. For dev/testing."""

    def execute(self, work_dir: str | Path, manifest: EvalManifest) -> HarnessResult:
        work_dir = Path(work_dir)
        full_log = []
        metric_values: dict[str, float] = {}

        # Run build steps
        for cmd in manifest.build:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=manifest.timeout,
            )
            full_log.append(f"$ {cmd}\n{result.stdout}\n{result.stderr}")
            if result.returncode != 0:
                return HarnessResult(
                    metric_values={},
                    log="\n".join(full_log),
                    success=False,
                )

        # Run constraint checks
        for constraint in manifest.constraints:
            if constraint.type == "must-pass" and constraint.command:
                result = subprocess.run(
                    constraint.command,
                    shell=True,
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=manifest.timeout,
                )
                full_log.append(f"$ {constraint.command} (constraint: {constraint.name})\n{result.stdout}\n{result.stderr}")
                if result.returncode != 0:
                    return HarnessResult(
                        metric_values={},
                        log="\n".join(full_log),
                        success=False,
                    )

        # Run each metric command
        for metric in manifest.metrics:
            result = subprocess.run(
                metric.command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=manifest.timeout,
            )
            full_log.append(f"$ {metric.command}\n{result.stdout}\n{result.stderr}")

            if result.returncode != 0:
                return HarnessResult(
                    metric_values=metric_values,
                    log="\n".join(full_log),
                    success=False,
                )

            # Parse last non-empty line of stdout as the metric value
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if not lines:
                return HarnessResult(
                    metric_values=metric_values,
                    log="\n".join(full_log),
                    success=False,
                )
            try:
                metric_values[metric.name] = float(lines[-1])
            except ValueError:
                full_log.append(f"ERROR: Could not parse metric value from: {lines[-1]}")
                return HarnessResult(
                    metric_values=metric_values,
                    log="\n".join(full_log),
                    success=False,
                )

        return HarnessResult(
            metric_values=metric_values,
            log="\n".join(full_log),
            success=True,
        )


class DockerHarness:
    """Runs evals inside a Docker container with sandboxing."""

    def execute(self, work_dir: str | Path, manifest: EvalManifest) -> HarnessResult:
        import docker

        work_dir = Path(work_dir).resolve()
        client = docker.from_env()
        full_log = []
        metric_values: dict[str, float] = {}

        # Build the full eval script
        build_cmds = " && ".join(manifest.build) if manifest.build else "true"
        constraint_cmds = []
        for c in manifest.constraints:
            if c.type == "must-pass" and c.command:
                constraint_cmds.append(c.command)
        constraint_script = " && ".join(constraint_cmds) if constraint_cmds else "true"

        # Parse resource constraints
        mem_limit = None
        for c in manifest.constraints:
            if c.type == "resource-limit" and c.value and "memory" in c.name.lower():
                mem_limit = c.value

        # Run build + constraints first
        setup_script = f"{build_cmds} && {constraint_script}"
        try:
            output = client.containers.run(
                manifest.environment.image,
                command=["sh", "-c", setup_script],
                volumes={str(work_dir): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                mem_limit=mem_limit,
                network_mode="none",
                remove=True,
                timeout=manifest.timeout,
                stderr=True,
            )
            full_log.append(output.decode() if isinstance(output, bytes) else str(output))
        except Exception as e:
            return HarnessResult(
                metric_values={},
                log=f"Setup failed: {e}",
                success=False,
            )

        # Run each metric
        for metric in manifest.metrics:
            try:
                output = client.containers.run(
                    manifest.environment.image,
                    command=["sh", "-c", metric.command],
                    volumes={str(work_dir): {"bind": "/workspace", "mode": "ro"}},
                    working_dir="/workspace",
                    mem_limit=mem_limit,
                    network_mode="none",
                    remove=True,
                    timeout=manifest.timeout,
                    stderr=True,
                )
                text = output.decode() if isinstance(output, bytes) else str(output)
                full_log.append(text)

                lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
                if not lines:
                    return HarnessResult(metric_values=metric_values, log="\n".join(full_log), success=False)
                metric_values[metric.name] = float(lines[-1])

            except Exception as e:
                full_log.append(f"Metric {metric.name} failed: {e}")
                return HarnessResult(metric_values=metric_values, log="\n".join(full_log), success=False)

        return HarnessResult(
            metric_values=metric_values,
            log="\n".join(full_log),
            success=True,
        )
