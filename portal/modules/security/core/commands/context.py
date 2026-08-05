"""Run-state context object threaded through the cli.py main() fall-through blocks — C2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class BenchRun:
    """Run state threaded through the cli.py main() fall-through blocks."""

    args: Any
    cfg: Any
    ts: str
    checkpoint_path: Path | None
    chain_results: list[dict]
    blue_results: list[dict]
    purple_results: list[dict]
    scenario: str | None
    scenario_averages: list[dict]
    multimodel_results: list[dict]
    _step_models: dict[str, str]
    _enabled_prompts: set[str]
    _target_prompts: set[str]
    results: list[dict] | None
    evasion_results: list[dict] | None
    false_positive_results: list[dict] | None
    defense_efficacy_results: list[dict] | None
    expansion_steps: dict[str, dict] | None
    matrix_results: dict | None
    matrix_units: list[dict] | None
    _snapshot_name: str
    refusal_results: list[dict]
    _audit_results: list[dict]
    _retry_data: dict
    _out_path: Path
    _t0_bench: float
