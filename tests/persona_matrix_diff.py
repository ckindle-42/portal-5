#!/usr/bin/env python3
"""Compare two persona-matrix result JSONs and surface regressions.

Usage:
    python3 tests/persona_matrix_diff.py BASELINE.json NEW.json
    python3 tests/persona_matrix_diff.py BASELINE.json NEW.json --threshold 5
    python3 tests/persona_matrix_diff.py BASELINE.json NEW.json --json

Exit codes:
    0 — no regressions over threshold
    1 — at least one regression over threshold
    2 — invalid input (file missing, schema mismatch, etc.)

A "regression" is defined as a drop in PASS-rate for a given
(persona, model) cell that exceeds --threshold percentage points.
PASS-rate = PASS / (PASS + WARN + FAIL) per cell. Cells with ERROR are
skipped (treated as 'no signal') to avoid false-positives from transient
backend hiccups.

Symmetric: also surfaces *improvements* over threshold for visibility
(in non-JSON mode, marked with '+'). Improvements never count toward
exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    with open(path) as f:
        d = json.load(f)
    if d.get("schema") != "portal5.persona_matrix.v1":
        raise ValueError(f"{path}: not a persona_matrix.v1 report (schema={d.get('schema')!r})")
    return d


def _cell_pass_rate(cell: dict[str, Any]) -> float | None:
    s = cell.get("summary", {})
    total = s.get("PASS", 0) + s.get("WARN", 0) + s.get("FAIL", 0)
    if total == 0:
        return None
    return 100.0 * s.get("PASS", 0) / total


def _index_cells(report: dict[str, Any]) -> dict[tuple[str, str, str], dict]:
    return {(c["persona"], c["backend"], c["model"]): c for c in report.get("cells", [])}


def compute_regressions(
    baseline_path: Path,
    new_report: dict[str, Any],
    threshold_pp: float = 10.0,
) -> list[str]:
    base = _load_report(baseline_path)
    base_idx = _index_cells(base)
    new_idx = _index_cells(new_report)

    regressions: list[str] = []
    for key, new_cell in new_idx.items():
        old_cell = base_idx.get(key)
        if old_cell is None:
            continue
        new_rate = _cell_pass_rate(new_cell)
        old_rate = _cell_pass_rate(old_cell)
        if new_rate is None or old_rate is None:
            continue
        delta = new_rate - old_rate
        if delta < -threshold_pp:
            persona, backend, model = key
            regressions.append(
                f"REGRESSION  {persona:30} on {backend}/{model:40}  "
                f"{old_rate:5.1f}% → {new_rate:5.1f}% (Δ {delta:+5.1f}pp)"
            )
    return regressions


def compute_improvements(
    baseline_path: Path, new_report: dict[str, Any], threshold_pp: float = 10.0
) -> list[str]:
    base = _load_report(baseline_path)
    base_idx = _index_cells(base)
    new_idx = _index_cells(new_report)

    improvements: list[str] = []
    for key, new_cell in new_idx.items():
        old_cell = base_idx.get(key)
        if old_cell is None:
            continue
        new_rate = _cell_pass_rate(new_cell)
        old_rate = _cell_pass_rate(old_cell)
        if new_rate is None or old_rate is None:
            continue
        delta = new_rate - old_rate
        if delta > threshold_pp:
            persona, backend, model = key
            improvements.append(
                f"+IMPROVED   {persona:30} on {backend}/{model:40}  "
                f"{old_rate:5.1f}% → {new_rate:5.1f}% (Δ {delta:+5.1f}pp)"
            )
    return improvements


def added_removed_cells(
    baseline_path: Path, new_report: dict[str, Any]
) -> tuple[list[str], list[str]]:
    base = _load_report(baseline_path)
    base_idx = _index_cells(base)
    new_idx = _index_cells(new_report)

    added = sorted(f"{p}/{be}/{m}" for (p, be, m) in (new_idx.keys() - base_idx.keys()))
    removed = sorted(f"{p}/{be}/{m}" for (p, be, m) in (base_idx.keys() - new_idx.keys()))
    return added, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("baseline", type=Path, help="baseline JSON path")
    parser.add_argument("new", type=Path, help="new run JSON path")
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="regression threshold in percentage points (default: 10.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of human text",
    )
    args = parser.parse_args(argv)

    if not args.baseline.is_file():
        print(f"baseline file not found: {args.baseline}", file=sys.stderr)
        return 2
    if not args.new.is_file():
        print(f"new file not found: {args.new}", file=sys.stderr)
        return 2

    try:
        new_report = _load_report(args.new)
    except Exception as e:
        print(f"could not load new report: {e}", file=sys.stderr)
        return 2

    regressions = compute_regressions(args.baseline, new_report, args.threshold)
    improvements = compute_improvements(args.baseline, new_report, args.threshold)
    added, removed = added_removed_cells(args.baseline, new_report)

    if args.json:
        out = {
            "baseline": str(args.baseline),
            "new": str(args.new),
            "threshold_pp": args.threshold,
            "regressions": regressions,
            "improvements": improvements,
            "added_cells": added,
            "removed_cells": removed,
        }
        print(json.dumps(out, indent=2))
    else:
        print(
            f"# Diff: {args.baseline.name} → {args.new.name}  (threshold ±{args.threshold:.1f}pp)\n"
        )
        if regressions:
            print(f"## Regressions ({len(regressions)})")
            for r in regressions:
                print(r)
            print()
        if improvements:
            print(f"## Improvements ({len(improvements)})")
            for r in improvements:
                print(r)
            print()
        if added:
            print(f"## New cells ({len(added)})")
            for a in added[:20]:
                print(f"  + {a}")
            if len(added) > 20:
                print(f"  ... and {len(added) - 20} more")
            print()
        if removed:
            print(f"## Removed cells ({len(removed)})")
            for r in removed[:20]:
                print(f"  - {r}")
            if len(removed) > 20:
                print(f"  ... and {len(removed) - 20} more")
            print()
        if not regressions and not improvements and not added and not removed:
            print("No changes over threshold.")

    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
