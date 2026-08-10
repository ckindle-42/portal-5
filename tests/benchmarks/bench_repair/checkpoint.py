"""Crash-safe incremental sample persistence + resume, mirroring bench/results_io.py."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from tests.benchmarks.bench_repair.runner import SampleResult


def checkpoint_path(results_dir: Path, gsha: str) -> Path:
    return results_dir / f"BENCH_REPAIR_CHECKPOINT_{gsha}.json"


def load_checkpoint(path: Path) -> list[SampleResult]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return [SampleResult(**s) for s in data.get("samples", [])]
    except Exception:  # noqa: BLE001
        return []


def append_samples(path: Path, gsha: str, new_samples: list[SampleResult]) -> None:
    """Read-modify-write the whole file (crash-safe; matches bench/results_io._append_result)."""
    existing = load_checkpoint(path)
    existing.extend(new_samples)
    path.write_text(json.dumps({"gsha": gsha, "samples": [asdict(s) for s in existing]}, indent=2))


def cell_done(
    samples: list[SampleResult], workspace: str, problem_id: str, arm: str, n: int
) -> bool:
    count = sum(
        1
        for s in samples
        if s.workspace == workspace and s.problem_id == problem_id and s.arm == arm
    )
    return count >= n


def samples_for_cell(
    samples: list[SampleResult], workspace: str, problem_id: str, arm: str
) -> list[SampleResult]:
    return [
        s
        for s in samples
        if s.workspace == workspace and s.problem_id == problem_id and s.arm == arm
    ]
