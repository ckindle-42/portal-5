#!/usr/bin/env python3
"""Portal 5 — CC-01 Challenge Shootout Matrix.

Reads tests/UAT_RESULTS.md rows for the ``challenge`` section (test ids
CC-01-* / BT-01-* / EX-01-*) and emits a comparative capability matrix:
one row per model, assertion pass-fraction, status, elapsed. No verdict —
the matrix is the deliverable (same contract as
tests/benchmarks/coding_shootout_analyze.py, TASK_CODING_SHOOTOUT_V2 §A6).
Promotion decisions remain operator-only (PROMOTE_POLICY).

Usage:
    python3 tests/scripts/cc_challenge_matrix.py \
        [--input tests/UAT_RESULTS.md] \
        [--output tests/benchmarks/results/CC01_CHALLENGE_MATRIX_<UTC>.md]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(?P<status>[A-Z]+)\s*\|\s*\[(?P<name>(?:CC|BT|EX)-01[^\]]*)\]"
    r"\([^)]*\)\s*\|\s*`(?P<slug>[^`]+)`\s*\|\s*(?P<detail>.*?)\|\s*(?P<elapsed>[\d.]+)s\s*\|\s*$"
)
FRACTION_RE = re.compile(r"(?P<passed>\d+)/(?P<total>\d+)\((?P<pct>\d+(?:\.\d+)?)%\)")


def parse_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        d = m.groupdict()
        f = FRACTION_RE.search(d["detail"])
        d["passed"] = int(f["passed"]) if f else None
        d["total"] = int(f["total"]) if f else None
        d["pct"] = float(f["pct"]) if f else None
        rows.append(d)
    return rows


def render(rows: list[dict], source: str) -> str:
    out = [
        "# CC-01 Challenge Shootout — Capability Matrix",
        "",
        f"**Source**: `{source}` · generated {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "One identical creative coding task per model (CC-01 Asteroids), plus",
        "domain challenges (BT-01, EX-01). No verdict — the matrix is the",
        "deliverable; promotions are operator-only (PROMOTE_POLICY).",
        "",
        "| Challenge | Workspace | Status | Assertions | Pass % | Elapsed |",
        "|---|---|---|---|---|---|",
    ]
    ranked = sorted(
        rows,
        key=lambda r: (-(r["pct"] if r["pct"] is not None else -1.0), r["slug"]),
    )
    for r in ranked:
        frac = f"{r['passed']}/{r['total']}" if r["total"] is not None else "—"
        pct = f"{r['pct']:.0f}%" if r["pct"] is not None else "—"
        out.append(
            f"| {r['name']} | `{r['slug']}` | {r['status']} | {frac} | {pct} | {r['elapsed']}s |"
        )
    if not rows:
        out.append("| _no challenge rows found in input_ | | | | | |")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(ROOT / "tests" / "UAT_RESULTS.md"))
    default_out = (
        ROOT
        / "tests"
        / "benchmarks"
        / "results"
        / ("CC01_CHALLENGE_MATRIX_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".md")
    )
    ap.add_argument("--output", default=str(default_out))
    args = ap.parse_args()

    text = Path(args.input).read_text()
    rows = parse_rows(text)
    Path(args.output).write_text(render(rows, args.input))
    print(f"wrote {args.output} ({len(rows)} challenge rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
