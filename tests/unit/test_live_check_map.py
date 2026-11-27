"""Contract test pinning config/live_check_map.yaml to real QAT scenarios and spine surfaces."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.live_checks_for_diff import DEFAULT_MAP_PATH, load_map, resolve_checks

REPO_ROOT = Path(__file__).resolve().parents[2]


def _discovered_qat_ids_and_phases() -> tuple[set[str], set[str]]:
    out = subprocess.check_output(
        [sys.executable, "-m", "tests.qat", "--dry-run"],
        cwd=REPO_ROOT,
        text=True,
    )
    phases: set[str] = set()
    ids: set[str] = set()
    for line in out.splitlines():
        if m := re.match(r"\s+stage \d+ · phase (\S+)", line):
            phases.add(m.group(1))
        elif m := re.match(r"\s{4}(\S+)\s+tier=", line):
            ids.add(m.group(1))
    return ids, phases


def test_every_mapped_qat_scenario_and_phase_exists() -> None:
    cfg = load_map(DEFAULT_MAP_PATH)
    live_ids, live_phases = _discovered_qat_ids_and_phases()
    assert live_ids, "QAT dry-run returned no scenarios"

    missing_ids: list[str] = []
    missing_phases: list[str] = []
    for rule in cfg["rules"]:
        for sid in rule.get("qat_scenarios") or []:
            if sid not in live_ids:
                missing_ids.append(f"{rule['id']}:{sid}")
        for phase in rule.get("qat_phases") or []:
            if phase not in live_phases:
                missing_phases.append(f"{rule['id']}:{phase}")

    assert not missing_ids, f"Unknown QAT scenario IDs: {missing_ids}"
    assert not missing_phases, f"Unknown QAT phase names: {missing_phases}"


def test_every_spine_surface_maps_to_a_live_check() -> None:
    spine = yaml.safe_load((REPO_ROOT / "config" / "spine_surfaces.yaml").read_text())
    unmapped: list[str] = []
    for entry in spine["surfaces"]:
        probe_path = f"{entry['dir']}/__init__.py"
        plan = resolve_checks([probe_path])
        if not plan.matched_rules or not plan.commands():
            unmapped.append(entry["dir"])
    assert not unmapped, f"Spine surfaces without a live check rule: {unmapped}"


def test_resolve_checks_flags_rebuild_and_deduplicates() -> None:
    plan = resolve_checks(
        [
            "portal/platform/inference/router/streaming.py",
            "portal/modules/coding/tools/code_sandbox_mcp.py",
        ]
    )
    assert plan.rebuild_required is True
    assert plan.smoke_stream is True
    assert "s2-p1-auto" in plan.qat_scenarios
    assert "s5-sandbox-lifecycle" in plan.qat_scenarios
    assert len(plan.qat_scenarios) == len(set(plan.qat_scenarios))

    doc_only = resolve_checks(["docs/findings/TEST_STRATEGY_NEON_20261127.md"])
    assert doc_only.rebuild_required is False
    assert doc_only.commands() == []
