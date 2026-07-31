#!/usr/bin/env python3
"""Verify every scoreable live security capture can be replayed into Splunk."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

from portal.modules.security.core.corpus_coverage import build_coverage_report
from portal.modules.security.core.siem.capture_store import replay_capture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Ship into lab Splunk and require indexing confirmation; default is dry-run",
    )
    parser.add_argument("--scenario", action="append", default=[], help="Limit to a scenario")
    parser.add_argument("--timeout", type=int, default=30, help="Index wait timeout per capture")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    coverage = build_coverage_report(external_techniques=set())
    selected = set(args.scenario)
    results: list[dict] = []
    for scenario in coverage["scenario_coverage"]["valid_scenarios"]:
        if selected and scenario not in selected:
            continue
        path = coverage["scenario_coverage"]["details"][scenario]["valid_capture"]
        result = replay_capture(path, dry_run=not args.live, timeout_s=args.timeout)
        verified = bool(result.get("ok")) and (
            result.get("indexed_confirmed") is True if args.live else True
        )
        results.append({**result, "verified": verified})
        print(
            f"{'PASS' if verified else 'FAIL'} {scenario}: "
            f"shipped={result.get('shipped', 0)} indexed={result.get('indexed_confirmed')}"
        )

    unknown_selected = sorted(selected - {row["scenario"] for row in results})
    report = {
        "schema_version": 1,
        "mode": "live" if args.live else "dry-run",
        "eligible": len(results),
        "verified": sum(row["verified"] for row in results),
        "failed": [row["scenario"] for row in results if not row["verified"]],
        "unknown_or_unscoreable_requested": unknown_selected,
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in report if key != "results"}, indent=2))
    return 0 if report["verified"] == report["eligible"] and not unknown_selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
