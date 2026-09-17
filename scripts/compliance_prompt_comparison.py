#!/usr/bin/env python3
"""Did the prompt change help? One variable, measured.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P4. The acceptance suite scores the reader
through the DEPLOYED service, which loads whichever prompt is live. This
isolates the prompt instead: the same seat, the same code, the same cases, the
same store, one variable — `config/compliance/reading_prompt.md` (v2) against
`tests/data/compliance/reading_prompt_v1.md`, the prompt as it stood at
0db04c6f.

It runs IN PROCESS rather than through the MCP, because `compliance_ask` takes
no prompt path and adding one would be a production surface that exists only for
a measurement. That is the deviation, and it is stated rather than hidden;
everything else is identical to an acceptance cell.

Tool-call counts are reported per prompt, because the claim being tested is that
v1 never asked the model to use its tools and a control contract then had to
fail readings for not using them.

Usage:
  uv run python scripts/compliance_prompt_comparison.py --out <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

V1 = REPO / "tests" / "data" / "compliance" / "reading_prompt_v1.md"
V2 = REPO / "config" / "compliance" / "reading_prompt.md"
CASES = REPO / "config" / "compliance" / "cases" / "cip_007_6.yaml"


def one(case: dict[str, Any], seat: str, prompt_path: Path) -> dict[str, Any]:
    from portal.modules.compliance.core.reader import read
    from portal.modules.compliance.core.repository import Repository
    from scripts.compliance_acceptance import check_case, truncation_guard

    repo = Repository()
    started = time.monotonic()
    try:
        payload = read(
            repo,
            str(case["question"]).strip(),
            str(case["ref"]),
            model=seat,
            prompt_path=prompt_path,
            # Nothing is projected into the corpus: this is a measurement about
            # the prompt, not an analyst's reading, and a stored answer is a
            # derived source that later readings can see.
            store=False,
            retain_run=False,
            timeout=3600,
        )
    finally:
        repo.close()
    guard = truncation_guard(payload)
    checks = check_case(case, payload) if all(g["ok"] for g in guard) else []
    closure = payload.get("closure_receipt") or {}
    return {
        "case": case["id"],
        "ref": case["ref"],
        "prompt_version": payload.get("prompt_version"),
        "prompt_sha": payload.get("prompt_sha"),
        "wall_s": round(time.monotonic() - started, 1),
        "model_tool_calls": closure.get("model_tool_calls"),
        "tools_used": [
            t["tool"] for t in closure.get("tool_trace", []) if t["derivation"] == "model"
        ],
        "answer_chars": len(str(payload.get("answer", "") or "")),
        "citations_resolved": sum(
            1 for c in (payload.get("verification") or {}).get("citations", []) if c.get("resolved")
        ),
        "operator_examined": len(closure.get("operator_examined") or []),
        "operator_cited": len(closure.get("operator_cited") or []),
        "failed": bool(payload.get("failed")),
        "failure": payload.get("failure", ""),
        "guard": guard,
        "checks": checks,
        "failed_assertions": [r["assertion"] for r in [*guard, *checks] if not r["ok"]],
        "applied_settings": payload.get("applied_settings"),
        "answer": payload.get("answer", ""),
    }


def main() -> int:
    from portal.modules.compliance.core.runtime_config import reading_seat

    parser = argparse.ArgumentParser()
    parser.add_argument("--seat", default="")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--out", default=str(REPO / "reports/compliance/prompt_comparison"))
    args = parser.parse_args()

    seat = args.seat or reading_seat()
    manifest = yaml.safe_load(CASES.read_text())
    cases = [c for c in manifest["cases"] if not args.case or c["id"] in args.case]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for label, path in (("v1", V1), ("v2", V2)):
        for case in cases:
            row = one(case, seat, path)
            row["prompt"] = label
            rows.append(row)
            print(
                f"{label}  {row['case']:<18} tool_calls={row['model_tool_calls']:<3} "
                f"citations={row['citations_resolved']:<3} "
                f"op_cited={row['operator_cited']:<3} "
                f"failed={row['failed']}  {row['failed_assertions']}",
                flush=True,
            )
            (out_dir / "comparison.json").write_text(
                json.dumps({"seat": seat, "rows": rows}, indent=1, default=str)
            )
    print(f"\nartifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
