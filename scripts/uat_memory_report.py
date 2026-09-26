#!/usr/bin/env python3
"""Summarize a UAT memory-recording JSONL into the P5-FANOUT-001 W6 answer.

docs/TASK_FANOUT_CONCURRENCY_V1.md W6 asks whether OLLAMA_NUM_PARALLEL can go
back above 1 now that the fan-out lanes that originally forced it down
(compliance fan-out, several council seats) have moved to oMLX. That needs
real concurrent-load data, not a guess — this reads the JSONL that
tests/uat/monitor.py's MemoryMonitor writes when UAT_MEMORY_RECORD is set,
and reports the peak concurrent footprint each engine actually reached during
the run.

Usage:
    UAT_MEMORY_RECORD=/tmp/uat_mem.jsonl uv run python tests/portal5_uat_driver.py ...
    uv run python scripts/uat_memory_report.py /tmp/uat_mem.jsonl

The NUM_PARALLEL=2 projection below is a first-order proxy (doubling the
observed peak concurrent Ollama VRAM), not the exact weights+KV×NUM_PARALLEL
reservation math P5-ROUTER-EVICTION-001 used — /api/ps reports actual usage,
not Ollama's internal reservation. Read it as "is there room to even consider
this," not as a go/no-go by itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: iogpu.wired_limit_mb, GB (see feedback_gpu_wired_limit_intentional memory
#: and docs/TASK_MEMORY_FOOTPRINT_REDUCTION_V1.md — 56GB is deliberate
#: headroom below oMLX's own 58GB ceiling on a 64GB box, not the full budget).
WIRED_LIMIT_GB = 56.0


def load_snapshots(path: Path) -> list[dict[str, Any]]:
    snapshots = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                snapshots.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return snapshots


def report(snapshots: list[dict[str, Any]]) -> None:
    if not snapshots:
        print("No snapshots recorded — nothing to report.")
        return

    duration_s = snapshots[-1]["ts"] - snapshots[0]["ts"]
    peak_ollama = max(snapshots, key=lambda s: s["ollama_concurrent_vram_gb"])
    peak_omlx = max(snapshots, key=lambda s: s.get("omlx_current_model_memory_gb") or 0)
    peak_combined = max(
        snapshots,
        key=lambda s: s["ollama_concurrent_vram_gb"] + (s.get("omlx_current_model_memory_gb") or 0),
    )
    peak_mem_pct = max(s["memory_pct"] for s in snapshots)
    multi_model_samples = [s for s in snapshots if len(s["ollama_models"]) > 1]

    print(f"UAT memory recording: {len(snapshots)} samples over {duration_s / 60:.1f} min\n")

    print("── Peak Ollama concurrent footprint ──")
    print(
        f"  {peak_ollama['ollama_concurrent_vram_gb']:.1f} GB across {len(peak_ollama['ollama_models'])} resident model(s)"
    )
    for m in peak_ollama["ollama_models"]:
        print(
            f"    - {m['name']}: {m['size_vram'] / (1024**3):.1f} GB (ctx {m.get('context_length')})"
        )
    print(
        f"  Concurrent (>1 model) samples: {len(multi_model_samples)}/{len(snapshots)}"
        f"{' — Ollama never actually held concurrent residents during this run' if not multi_model_samples else ''}"
    )

    print("\n── Peak oMLX resident footprint ──")
    print(
        f"  {peak_omlx.get('omlx_current_model_memory_gb', 0):.1f} GB "
        f"({peak_omlx.get('omlx_loaded_count')} model(s) loaded), "
        f"guard ceiling at that moment: {peak_omlx.get('omlx_final_ceiling_gb', 0):.1f} GB"
    )

    print("\n── Peak combined (both engines at once) ──")
    combined_gb = peak_combined["ollama_concurrent_vram_gb"] + (
        peak_combined.get("omlx_current_model_memory_gb") or 0
    )
    print(
        f"  {combined_gb:.1f} GB of {WIRED_LIMIT_GB:.0f} GB wired limit ({combined_gb / WIRED_LIMIT_GB:.0%})"
    )
    print(f"  System memory_pct peak: {peak_mem_pct:.0f}%")

    print("\n── NUM_PARALLEL=2 projection (approximate — see module docstring) ──")
    projected = peak_ollama["ollama_concurrent_vram_gb"] * 2
    other_engine_gb = peak_ollama.get("omlx_current_model_memory_gb") or 0
    projected_combined = projected + other_engine_gb
    verdict = "FITS" if projected_combined <= WIRED_LIMIT_GB * 0.9 else "DOES NOT FIT"
    print(
        f"  Doubling peak Ollama VRAM ({peak_ollama['ollama_concurrent_vram_gb']:.1f} -> "
        f"{projected:.1f} GB) + oMLX's concurrent footprint at that moment "
        f"({other_engine_gb:.1f} GB) = {projected_combined:.1f} GB — {verdict} under "
        f"90% of the {WIRED_LIMIT_GB:.0f} GB wired limit."
    )
    if not multi_model_samples:
        print(
            "  CAVEAT: this run never exercised real Ollama concurrency — the projection "
            "is off a single-model peak, not a measured concurrent one. Re-run with a "
            "workload that actually overlaps two Ollama-only lanes (e.g. auto-data + "
            "auto-research back to back without a settling gap) before trusting this."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record_path", type=Path, help="JSONL file from UAT_MEMORY_RECORD")
    args = parser.parse_args()

    if not args.record_path.exists():
        print(f"error: {args.record_path} not found", file=sys.stderr)
        return 1

    report(load_snapshots(args.record_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
