"""Tests for the gitspoke.yaml manifest parser."""

import pytest
from gitspoke.manifest import load_manifest, parse_manifest
from gitspoke.models import MetricDirection


def test_load_manifest_from_file(sample_manifest_path):
    manifest = load_manifest(sample_manifest_path)
    assert manifest.name == "test-suite"
    assert manifest.version == "1.0.0"
    assert len(manifest.metrics) == 1
    assert manifest.metrics[0].name == "accuracy"
    assert manifest.metrics[0].type == MetricDirection.HIGHER_IS_BETTER


def test_parse_manifest_full():
    raw = {
        "name": "benchmark",
        "version": "2.1.0",
        "environment": {"image": "python:3.11", "gpu": True},
        "build": ["pip install -r requirements.txt"],
        "metrics": [
            {"name": "loss", "type": "lower-is-better", "command": "python eval.py", "weight": 0.7},
            {"name": "speed", "type": "higher-is-better", "command": "python bench.py", "weight": 0.3},
            {"name": "canary", "type": "higher-is-better", "command": "python canary.py", "weight": 0},
        ],
        "constraints": [
            {"name": "tests", "command": "pytest", "type": "must-pass"},
            {"name": "mem", "value": "8GB", "type": "resource-limit"},
        ],
        "timeout": 300,
        "resources": {
            "minimum": {"gpu": "rtx-4090", "memory": "32GB"},
        },
    }
    manifest = parse_manifest(raw)
    assert manifest.name == "benchmark"
    assert manifest.major_version == 2
    assert manifest.environment.gpu is True
    assert len(manifest.weighted_metrics) == 2
    assert len(manifest.holdout_metrics) == 1
    assert manifest.holdout_metrics[0].name == "canary"
    assert len(manifest.constraints) == 2
    assert manifest.timeout == 300


def test_parse_manifest_missing_field():
    with pytest.raises(ValueError, match="Missing required field"):
        parse_manifest({"name": "x", "version": "1.0.0"})


def test_parse_manifest_bad_metric_type():
    raw = {
        "name": "x",
        "version": "1.0.0",
        "environment": "python:3.11",
        "metrics": [{"name": "m", "type": "invalid", "command": "echo 1"}],
    }
    with pytest.raises(ValueError, match="Unknown metric type"):
        parse_manifest(raw)


def test_load_manifest_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_manifest("/nonexistent/gitspoke.yaml")


def test_parse_manifest_string_environment():
    raw = {
        "name": "simple",
        "version": "1.0.0",
        "environment": "python:3.11-slim",
        "metrics": [{"name": "score", "type": "higher-is-better", "command": "echo 1"}],
    }
    manifest = parse_manifest(raw)
    assert manifest.environment.image == "python:3.11-slim"
    assert manifest.environment.gpu is False
