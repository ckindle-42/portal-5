"""Run-state context object threaded through the cli.py main() fall-through blocks — C2."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..matrix import RunUnit


@dataclass
class BenchRun:
    """Run state threaded through the cli.py main() fall-through blocks."""

    args: Any
    cfg: Any
    ts: str
    checkpoint_path: Path | None
    chain_results: list[dict[str, Any]]
    blue_results: list[dict[str, Any]]
    purple_results: list[dict[str, Any]]
    scenario: dict[str, Any] | None
    scenario_averages: list[dict[str, Any]]
    multimodel_results: list[dict[str, Any]]
    _step_models: dict[str, str]
    _enabled_prompts: set[str]
    _target_prompts: set[str]
    results: list[dict[str, Any]] | None
    evasion_results: list[dict[str, Any]] | None
    false_positive_results: list[dict[str, Any]] | None
    defense_efficacy_results: list[dict[str, Any]] | None
    expansion_steps: dict[str, dict[str, Any]] | None
    matrix_results: dict[str, Any] | None
    matrix_units: list[RunUnit] | None
    _snapshot_name: str
    refusal_results: list[dict[str, Any]]
    _audit_results: list[dict[str, Any]]
    _retry_data: dict[str, Any]
    _out_path: Path
    _t0_bench: float
    _retry_failed_prompts: set[str] = field(default_factory=set)
    _retry_failed_scenarios: set[str] = field(default_factory=set)
