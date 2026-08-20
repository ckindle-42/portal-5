#!/usr/bin/env python3
"""scripts/bully_inject_capture.py -- run the E.5 generate/inject/capture
plane once and report which plane (live lab or the E.3 fixture) produced
the returned records. TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1.

Fail-closed: never fabricates a live result. Exits non-zero only when
neither the live plane nor the fixture could produce records (should not
happen -- the fixture has no live dependency).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import blend, inject_plane


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="use the E.3 fixture directly, never attempt the live plane",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report to this path")
    args = parser.parse_args()

    if args.dry_run:
        fixture_records, provenance = blend.compose_blend()
        captured_records: list[dict[str, object]] = list(fixture_records)
        report: dict[str, object] = {
            "plane": "fixture",
            "reason": "--dry-run requested the fixture directly",
            "n_records": len(captured_records),
            "schemas_present": sorted(blend.schemas_present(captured_records, provenance)),
            "injected_count": sum(1 for p in provenance.values() if p.injected),
            "benign_count": sum(1 for p in provenance.values() if not p.injected),
        }
    else:
        run = inject_plane.run_inject_capture()
        report = run.to_dict()
        captured_records = list(run.records)
        if run.plane == "fixture":
            _records, provenance = blend.compose_blend()
            report["schemas_present"] = sorted(blend.schemas_present(captured_records, provenance))

    graph = ag.build_graph(captured_records)
    report["extraction_valid"] = graph.role_map.extraction_valid if graph.role_map else False
    report["units"] = len(ag.enumerate_units(graph))

    print(json.dumps(report, indent=2, sort_keys=True))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(
        f"\n[bully_inject_capture] plane={report['plane']!r} reason={report['reason']!r}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
