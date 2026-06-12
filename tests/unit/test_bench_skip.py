"""Tests for the pipeline_bench_skip mechanism in the bench package.

The skip list lives in config/backends.yaml top-level and is honored by
_config_workspaces(). An explicit --workspace filter passed to
bench_pipeline() overrides the skip.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _make_cfg(skip_list: list[str] | None = None) -> dict:
    """Build a minimal backends.yaml-shaped config for testing."""
    cfg = {
        "backends": [],
        "workspace_routing": {
            "auto": ["security", "general"],
            "auto-coding": ["coding", "general"],
            "bench-something": ["coding", "general"],
            "bench-voxtral-realtime": ["general"],
            "bench-granite-speech": ["general"],
        },
        "defaults": {"fallback_group": "general"},
    }
    if skip_list is not None:
        cfg["pipeline_bench_skip"] = skip_list
    return cfg


def test_skip_list_excludes_workspaces() -> None:
    from tests.benchmarks.bench import discovery

    skip = ["bench-voxtral-realtime", "bench-granite-speech"]
    with patch.object(discovery, "_load_backends_config", return_value=_make_cfg(skip)):
        ws = discovery._config_workspaces()
    assert "bench-voxtral-realtime" not in ws
    assert "bench-granite-speech" not in ws
    # Non-skipped workspaces still present
    assert "auto" in ws
    assert "auto-coding" in ws
    assert "bench-something" in ws


def test_skip_list_absent_means_no_filter() -> None:
    """A missing pipeline_bench_skip key should not filter anything."""
    from tests.benchmarks.bench import discovery

    with patch.object(discovery, "_load_backends_config", return_value=_make_cfg(None)):
        ws = discovery._config_workspaces()
    assert "bench-voxtral-realtime" in ws
    assert "bench-granite-speech" in ws


def test_skip_list_empty_means_no_filter() -> None:
    """An empty pipeline_bench_skip list should not filter anything."""
    from tests.benchmarks.bench import discovery

    with patch.object(discovery, "_load_backends_config", return_value=_make_cfg([])):
        ws = discovery._config_workspaces()
    assert "bench-voxtral-realtime" in ws
    assert "bench-granite-speech" in ws


def test_real_backends_yaml_has_consistent_skip_list() -> None:
    """Integration check against the real backends.yaml.

    Every workspace listed in pipeline_bench_skip must exist in
    workspace_routing — otherwise it's a typo. Inverse not required:
    workspace_routing may legitimately contain workspaces not in the
    skip list.
    """
    cfg = yaml.safe_load((PROJECT_ROOT / "config" / "backends.yaml").read_text())
    skip = set(cfg.get("pipeline_bench_skip", []))
    routing = set(cfg.get("workspace_routing", {}).keys())
    orphans = skip - routing
    assert not orphans, f"pipeline_bench_skip references unknown workspaces: {orphans}"
