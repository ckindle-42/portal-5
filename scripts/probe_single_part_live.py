#!/usr/bin/env python3
"""Smallest live case first (slice D0 discipline): ONE Part through the shared
assessment service with per-stage timing, before any full seven-question run.

Prints a stage timeline and the resulting verdict so a stall or a malformed
reading is visible in minutes, not hours.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", default="CIP-007-6 R2 Part 2.2")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    stages: list[dict[str, str]] = []

    def mark(stage: str, started: float) -> None:
        elapsed = time.time() - started
        stages.append({"stage": stage, "seconds": round(elapsed, 1)})
        print(f"[{elapsed:8.1f}s] {stage}", flush=True)

    t0 = time.time()
    from portal.modules.compliance.core.assessment_runs import assess_requirements_now

    mark("imports", t0)

    results = assess_requirements_now(
        [args.part],
        kb_id="operator_corpus",
        scope_text="high impact and medium impact BCS with associated EACMS PACS PCA",
        effective_on="2026-09-14",
        repository=None,
        on_result=lambda _r: mark("part persisted", time.time()),
    )
    result = results[0]
    mark("assess_part complete", t0)

    from dataclasses import asdict

    payload = asdict(result)
    receipt = payload.get("receipt") or {}
    explanation = receipt.get("explanation") or {}
    reading = explanation.get("raw") or {}
    response = reading.get("response") or {}
    summary = {
        "part": args.part,
        "documentary_coverage": payload.get("documentary_coverage"),
        "unresolved_code": payload.get("unresolved_code"),
        "substantively_resolved": payload.get("substantively_resolved"),
        "n_duties": len(response.get("duties") or []),
        "duty_findings": [
            {"duty_id": d.get("duty_id"), "finding": d.get("finding")}
            for d in (response.get("duties") or [])
        ],
        "n_gaps": len(payload.get("gaps") or []),
        "gap_kinds": [g.get("kind") for g in (payload.get("gaps") or [])],
        "n_covered": len(payload.get("covered") or []),
        "council_determination": (payload.get("council_result") or {}).get("determination"),
        "reading_valid": explanation.get("valid"),
        "reading_failure": explanation.get("failure"),
        "stages": stages,
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        Path(args.output).write_text(
            json.dumps(
                {"summary": summary, "result": json.loads(json.dumps(payload, default=str))},
                indent=2,
                default=str,
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
