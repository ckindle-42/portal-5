"""Validate capture files against their scenario's detect_ground_truth signals.

Classifies every scenario as VALID / PARTIAL / INVALID / MISSING and writes
/tmp/recapture_needed.txt with the scenarios that need re-capture.

Usage:
    python3 -m portal.modules.security.core.validate_captures
    python3 -m portal.modules.security.core.validate_captures --scenario kerberoast_to_da
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from portal.modules.security.core.siem.capture_enrichment import validate_capture_signals
from portal.modules.security.core.siem.capture_store import list_captures


def _load_latest_capture(scenario: str) -> dict | None:
    """Load the newest capture file for a scenario. Returns telemetry dict or None."""
    caps = list_captures(scenario)
    if not caps:
        return None
    try:
        data = json.loads(caps[0].read_text())
        return data.get("telemetry", {})
    except Exception:
        return None


def _classify(coverage: float, has_capture: bool) -> str:
    """Classify a scenario's capture validity."""
    if not has_capture:
        return "MISSING"
    if coverage >= 1.0:
        return "VALID"
    if coverage > 0:
        return "PARTIAL"
    return "INVALID"


def validate_all(*, scenario: str | None = None) -> dict:
    """Validate captures for all (or one) scenario.

    Returns:
        {valid: [...], partial: [...], invalid: [...], missing: [...], details: {...}}
    """
    from portal.modules.security.core.exec_chain import SCENARIOS

    targets = {scenario: SCENARIOS[scenario]} if scenario else SCENARIOS

    valid, partial, invalid, missing = [], [], [], []
    details: dict[str, dict] = {}

    for name, sc in sorted(targets.items()):
        gt = sc.get("detect_ground_truth", [])
        telemetry = _load_latest_capture(name)
        has_capture = telemetry is not None and any(telemetry.values())

        if not has_capture:
            cls = "MISSING"
            info = {
                "classification": cls,
                "coverage": 0.0,
                "found": [],
                "missing": gt,
                "techniques_checked": len(gt),
                "capture_file": None,
            }
        else:
            result = validate_capture_signals(name, telemetry)
            cls = _classify(result["coverage"], True)
            caps = list_captures(name)
            info = {
                "classification": cls,
                "coverage": result["coverage"],
                "found": result["found"],
                "missing": result["missing"],
                "techniques_checked": result["techniques_checked"],
                "capture_file": str(caps[0]) if caps else None,
            }

        details[name] = info
        {"VALID": valid, "PARTIAL": partial, "INVALID": invalid, "MISSING": missing}[cls].append(
            name
        )

    return {
        "valid": valid,
        "partial": partial,
        "invalid": invalid,
        "missing": missing,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate capture files against ground-truth signals"
    )
    parser.add_argument("--scenario", help="Validate a single scenario instead of all")
    parser.add_argument(
        "--partial-ok",
        type=float,
        default=0.5,
        help="Treat PARTIAL as usable if coverage >= this threshold (default 0.5)",
    )
    args = parser.parse_args()

    result = validate_all(scenario=args.scenario)

    valid = result["valid"]
    partial = result["partial"]
    invalid = result["invalid"]
    missing = result["missing"]
    details = result["details"]

    # Print summary
    print(f"\n{'=' * 60}")
    print("CAPTURE VALIDITY REPORT")
    print(f"{'=' * 60}")
    print(f"  VALID   (all signals present):  {len(valid)}")
    print(f"  PARTIAL (some signals present):  {len(partial)}")
    print(f"  INVALID (no attack signals):     {len(invalid)}")
    print(f"  MISSING (no capture file):       {len(missing)}")
    total = len(valid) + len(partial) + len(invalid) + len(missing)
    usable = len(valid) + len([s for s in partial if details[s]["coverage"] >= args.partial_ok])
    print(f"\n  Usable for sweep (VALID + PARTIAL>={args.partial_ok}): {usable}/{total}")
    print(f"{'=' * 60}\n")

    # Print per-scenario details
    for name, info in sorted(details.items()):
        cls = info["classification"]
        cov = info["coverage"]
        found = info["found"]
        missing_t = info["missing"]
        marker = {"VALID": "OK", "PARTIAL": "??", "INVALID": "XX", "MISSING": "--"}[cls]
        print(f"  [{marker}] {name:35s}  coverage={cov:.1%}  found={found}  missing={missing_t}")

    # Write recapture list: INVALID + MISSING + PARTIAL below threshold
    recapture = invalid + missing + [s for s in partial if details[s]["coverage"] < args.partial_ok]
    recapture_path = Path("/tmp/recapture_needed.txt")
    recapture_path.write_text("\n".join(recapture) + "\n")
    print(f"\n  Recapture list written to {recapture_path} ({len(recapture)} scenarios)")

    # Also write the full report to a JSON for downstream use
    report_path = Path("/tmp/capture_validity_report.json")
    report_path.write_text(json.dumps(result, indent=2))
    print(f"  Full report written to {report_path}")

    if recapture:
        print("\n  Scenarios needing re-capture:")
        for s in recapture:
            print(f"    - {s}")


if __name__ == "__main__":
    main()
