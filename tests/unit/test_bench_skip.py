"""Tests for the pipeline_bench_skip mechanism in the bench package.

The skip list lives in config/backends.yaml top-level and is honored by
_config_workspaces(). An explicit --workspace filter passed to
bench_pipeline() overrides the skip.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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
