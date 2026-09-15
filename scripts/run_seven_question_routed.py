#!/usr/bin/env python3
"""Routed live run of the seven-question CIP-007 R2 arm (END_TO_END Phase 10).

Calls the deployed compliance service (HTTP, /tools/compliance_analyze) with
``analysis_plan=seven_question_cip007_r2`` against the actual operator corpus,
including an isolated proposed-change scenario (a compliant wording
improvement added to the patch work instruction). Saves the full response as
the run receipt under the private artifact hierarchy.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8937"
RECEIPT_ROOT = Path("coding_task/v9_compliance/private/seven_question")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--valid-at", default="2026-09-14")
    parser.add_argument("--scenario", action="store_true")
    args = parser.parse_args()

    body: dict[str, Any] = {
        "requirements": ["CIP-007-6 R2"],
        "valid_at": args.valid_at,
        "known_at": "",
        "analysis_plan": "seven_question_cip007_r2",
        "scenario_part_id": "CIP-007-6 R2 Part 2.2",
    }
    if args.scenario:
        body["scenario_edits"] = [
            {
                "operation": "ADD",
                "target_document": (
                    "CIP-007/LSPG Security Patch Management Work Instruction v7.pdf"
                ),
                "label": "proposed-evaluation-record-clause",
                "new_text": (
                    "The analyst shall record the completion date of each security "
                    "patch applicability evaluation, the sources reviewed, and the "
                    "resulting disposition (install, mitigation plan, or defer with "
                    "justification) in the patching tracker within one business day "
                    "of the evaluation."
                ),
            }
        ]

    req = urllib.request.Request(
        f"{BASE}/tools/compliance_analyze",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = datetime.now(UTC)
    with urllib.request.urlopen(req, timeout=14400) as resp:
        payload = json.loads(resp.read())
    finished = datetime.now(UTC)

    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    out = RECEIPT_ROOT / stamp / "seven_question_routed.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "executed_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "route": f"{BASE}/tools/compliance_analyze",
        "served_commit": "4a1b6694",
        "service_pid": 82834,
        "request": body,
        "response": payload,
    }
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n")
    ops = payload.get("operations", [])
    print(
        json.dumps(
            {
                "run_id": payload.get("run_id"),
                "n_operations": len(ops),
                "ran": [op.get("op") for op in ops if op.get("ran")],
                "elapsed_s": receipt["elapsed_seconds"],
                "receipt": str(out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
