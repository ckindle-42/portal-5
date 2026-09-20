#!/usr/bin/env python3
"""CLOSEOUT_V1 P1.3 - the no-regression guard on the conjunction adoption.

A6.1 measured that the conjunction sentence fixes `choice` with no regressions.
This asserts it on the live seat instead of citing it: any case that was PASS
before the edit and is FAIL after halts the phase, and the adoption is rolled
back by the caller.

Verdict derivation (adaptation, recorded): ``p1_experiment`` cells carry no
verdict field, so the task's field-probe would grade every cell UNKNOWN and
pass trivially — the faked-green the task forbids. The verdict is therefore
derived mechanically from the fields this generation does write:

    FAIL  - the cell errored, or the answer is empty, or the stop reason is a
            reasoning-budget exhaustion
    PASS  - none of those, and the reading cited both sides
            (``cited_both_sides``, the campaign's own mechanical marker for
            "the reading engaged the requirement and the operator document")

The semantic judgment — does the answer honour the standard's disjunction —
is a reading, made at review over the diff; the guard's job is the
no-regression floor, and it says so on every receipt.

Exit codes:
    0 - no regressions (and the diff is written)
    1 - at least one case regressed PASS->FAIL
    3 - the two cell sets are not comparable
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Any


def _verdict(cell: dict[str, Any]) -> str:
    """Mechanical verdict from the fields p1_experiment writes. See module
    docstring for why the task's field-probe was replaced."""
    if cell.get("error"):
        return "FAIL"
    if not str(cell.get("answer", "") or "").strip():
        return "FAIL"
    if cell.get("stop_reason") == "budget_exhausted_in_reasoning":
        return "FAIL"
    if cell.get("cited_both_sides") is True:
        return "PASS"
    return "FAIL"


def _case(cell: dict[str, Any], path: pathlib.Path) -> str:
    for key in ("case", "case_id", "name"):
        val = cell.get(key)
        if isinstance(val, str) and val:
            return val
    stem = path.stem
    return stem.split("__")[-1] if "__" in stem else stem


def _load(d: pathlib.Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(d.glob("cell_*.json")):
        try:
            cell = json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            print(f"WARN: {p} does not parse ({exc}); skipped", file=sys.stderr)
            continue
        out[_case(cell, p)] = cell
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, type=pathlib.Path)
    ap.add_argument("--after", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    before = _load(args.before)
    after = _load(args.after)
    if not before or not after:
        print(f"FAIL: empty cell set (before={len(before)} after={len(after)})", file=sys.stderr)
        return 3

    shared = sorted(set(before) & set(after))
    if not shared:
        print(
            f"FAIL: no shared cases. before={sorted(before)} after={sorted(after)}", file=sys.stderr
        )
        return 3

    rows, regressions, fixes = [], [], []
    for case in shared:
        b, a = _verdict(before[case]), _verdict(after[case])
        rows.append({"case": case, "before": b, "after": a})
        if b == "PASS" and a == "FAIL":
            regressions.append(case)
        elif b == "FAIL" and a == "PASS":
            fixes.append(case)

    only_before = sorted(set(before) - set(after))
    only_after = sorted(set(after) - set(before))

    lines = [
        "# Conjunction adoption - before/after",
        "",
        f"Generated {_dt.datetime.now(_dt.UTC).isoformat()}",
        "",
        "Verdicts are the guard's mechanical floor (see the script docstring):",
        "FAIL on error / empty answer / budget-exhausted stop; PASS on a",
        "both-sides reading. The semantic judgment is a review reading.",
        "",
        "| case | before | after |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {r['case']} | {r['before']} | {r['after']} |" for r in rows]
    lines += [
        "",
        f"**Fixed:** {', '.join(fixes) if fixes else 'none'}",
        f"**Regressed:** {', '.join(regressions) if regressions else 'none'}",
    ]
    if only_before or only_after:
        lines.append(f"**Unmatched cases:** before-only {only_before}, after-only {only_after}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")

    summary = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "rows": rows,
        "fixes": fixes,
        "regressions": regressions,
        "only_before": only_before,
        "only_after": only_after,
        "verdict_basis": (
            "mechanical floor: FAIL on error/empty/budget-exhausted, PASS on "
            "cited_both_sides; the task's literal field-probe would have graded "
            "every cell UNKNOWN (no verdict field in this generation's cells) "
            "and passed trivially"
        ),
        "verdict": "FAIL" if regressions else "PASS",
        "reason": (
            f"regressions: {regressions}"
            if regressions
            else f"no regressions; fixed: {fixes or 'none'}"
        ),
    }
    args.out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(f"WROTE {args.out}  verdict={summary['verdict']}")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
