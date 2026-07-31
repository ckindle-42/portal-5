#!/usr/bin/env python3
"""Report readiness of combined live and external red data."""

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

from portal.modules.security.core.corpus_coverage import build_coverage_report, write_report
from portal.modules.security.core.corpus_replay_bench import discover_curated_techniques


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe-external",
        action="store_true",
        help="Query lab Splunk now; required for a ready validation gate",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    external = None
    validation = "declared"
    if args.probe_external:
        from portal.modules.security.core.siem.spl_backend import SplunkBackend

        backend = SplunkBackend()
        try:
            backend._run_search(
                f"search index={backend.index} evidence_origin=corpus:* | head 1",
                "0",
                "now",
            )
        except Exception as exc:
            print(f"External corpus probe failed: {exc}", file=sys.stderr)
            return 2
        external = set(discover_curated_techniques())
        validation = "live-probed"

    report = build_coverage_report(
        external_techniques=external,
        external_validation=validation,
    )
    if args.output:
        write_report(report, args.output)
    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_detection_design"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
