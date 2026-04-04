"""Parser and validator for gitspoke.yaml eval manifests."""

from __future__ import annotations

from pathlib import Path

import yaml

from gitspoke.models import (
    ConstraintSpec,
    EnvironmentSpec,
    EvalManifest,
    MetricDirection,
    MetricSpec,
    ResourceSpec,
)

# Map friendly YAML direction strings to enum values
_DIRECTION_MAP = {
    "lower-is-better": MetricDirection.LOWER_IS_BETTER,
    "higher-is-better": MetricDirection.HIGHER_IS_BETTER,
    "target": MetricDirection.TARGET,
}


def load_manifest(path: str | Path) -> EvalManifest:
    """Load and validate a gitspoke.yaml manifest file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a YAML mapping")

    return parse_manifest(raw)


def parse_manifest(raw: dict) -> EvalManifest:
    """Parse a raw dict into a validated EvalManifest."""
    # Required top-level fields
    for field in ("name", "version", "environment", "metrics"):
        if field not in raw:
            raise ValueError(f"Missing required field: {field}")

    # Environment
    env_raw = raw["environment"]
    if isinstance(env_raw, str):
        env = EnvironmentSpec(image=env_raw)
    else:
        env = EnvironmentSpec(**env_raw)

    # Metrics
    metrics = []
    for m in raw["metrics"]:
        direction = _DIRECTION_MAP.get(m["type"])
        if direction is None:
            raise ValueError(
                f"Unknown metric type '{m['type']}' for metric '{m['name']}'. "
                f"Must be one of: {list(_DIRECTION_MAP.keys())}"
            )
        metrics.append(
            MetricSpec(
                name=m["name"],
                type=direction,
                command=m["command"],
                weight=m.get("weight", 1.0),
            )
        )

    # Constraints
    constraints = []
    for c in raw.get("constraints", []):
        constraints.append(
            ConstraintSpec(
                name=c["name"],
                command=c.get("command"),
                value=c.get("value"),
                type=c["type"],
            )
        )

    # Resources
    resources = {}
    for level, spec in raw.get("resources", {}).items():
        resources[level] = ResourceSpec(**spec) if isinstance(spec, dict) else ResourceSpec()

    return EvalManifest(
        name=raw["name"],
        version=raw["version"],
        environment=env,
        build=raw.get("build", []),
        metrics=metrics,
        constraints=constraints,
        timeout=raw.get("timeout", 600),
        resources=resources,
    )
