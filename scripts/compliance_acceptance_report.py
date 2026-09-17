#!/usr/bin/env python3
"""Render the acceptance tables from the artifacts, never from memory.

TASK_COMPLIANCE_PROVE_CIP_007_V1 §P5. Every count, latency and applied setting
in CIP_007_ACCEPTANCE_V1.md is derived here from the run's own JSON, so a number
in the report cannot drift from the run it describes — which is the same rule
Rule 12 applies to fact-units, applied to a results report.

Usage:
  uv run python scripts/compliance_acceptance_report.py <acceptance-dir> [more dirs]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def load(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if path.name in {"manifest.json", "status.json", "preflight.json"}:
            continue
        rows.append(json.loads(path.read_text()))
    return rows


def cell_table(rows: list[dict[str, Any]]) -> str:
    out = [
        "| case | seat | run | verdict | tool calls | citations (reg/op) | prompt tok | "
        "headroom | latency s | failed assertions |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        closure = row.get("closure_receipt") or {}
        fit = row.get("context_fit") or {}
        citations = row.get("citations") or []
        regulatory = sum(
            1 for c in citations if c.get("side") == "regulatory" and c.get("resolved")
        )
        operator = sum(
            1
            for c in citations
            if str(c.get("side", "")).startswith("operator") and c.get("resolved")
        )
        latency = (row.get("latency") or {}).get("elapsed_s")
        out.append(
            f"| `{row['case']}` | {row['seat'].split('/')[-1]} | {row['run_index']} | "
            f"{'PASS' if row.get('passed') else 'FAIL'} | "
            f"{closure.get('model_tool_calls')} | {regulatory}/{operator} | "
            f"{fit.get('actual_prompt_tokens')} | {fit.get('headroom_tokens')} | "
            f"{latency} | {', '.join(row.get('failed_assertions') or []) or '—'} |"
        )
    return "\n".join(out)


def case_summary(rows: list[dict[str, Any]]) -> str:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(str(row["case"]), []).append(row)
    out = [
        "| case | runs | passed | tool calls (min/median/max) | operator sections cited | "
        "answer chars (median) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case, group in by_case.items():
        calls = [int((r.get("closure_receipt") or {}).get("model_tool_calls") or 0) for r in group]
        operator = sorted(
            {
                str(c["cited_ref"])
                for r in group
                for c in (r.get("citations") or [])
                if str(c.get("side", "")).startswith("operator") and c.get("resolved")
            }
        )
        chars = [len(str((r.get("payload") or {}).get("answer", "") or "")) for r in group]
        out.append(
            f"| `{case}` | {len(group)} | {sum(1 for r in group if r.get('passed'))} | "
            f"{min(calls)}/{int(statistics.median(calls))}/{max(calls)} | "
            f"{len(operator)} | {int(statistics.median(chars))} |"
        )
    return "\n".join(out)


def applied_settings(rows: list[dict[str, Any]]) -> str:
    out = [
        "| seat | requested ctx | applied ctx | temperature | answer budget | "
        "reasoning allowance | prompt tok (min/max) | chars/token |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    by_seat: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_seat.setdefault(str(row["seat"]), []).append(row)
    for seat, group in by_seat.items():
        applied = group[0].get("applied_settings") or {}
        prompts = [
            int((r.get("context_fit") or {}).get("actual_prompt_tokens") or 0) for r in group
        ]
        ratios = [
            float((r.get("context_fit") or {}).get("chars_per_token_observed") or 0) for r in group
        ]
        out.append(
            f"| `{seat}` | {applied.get('num_ctx_requested')} | "
            f"{applied.get('num_ctx_applied')} | {applied.get('temperature')} | "
            f"{applied.get('answer_budget')} | {applied.get('reasoning_allowance')} | "
            f"{min(prompts)}/{max(prompts)} | "
            f"{round(statistics.mean([r for r in ratios if r]), 2) if any(ratios) else '—'} |"
        )
    return "\n".join(out)


def main() -> int:
    directories = [Path(a) for a in sys.argv[1:]]
    if not directories:
        root = REPO / "reports" / "compliance" / "acceptance"
        directories = sorted(p for p in root.iterdir() if p.is_dir())
    rows: list[dict[str, Any]] = []
    for directory in directories:
        rows.extend(load(directory))
    reader = [r for r in rows if r.get("adapter") == "reader"]
    legacy = [r for r in rows if r.get("adapter") == "legacy"]

    print("## Per-case summary\n")
    print(case_summary(reader))
    print("\n## Applied settings, per seat\n")
    print(applied_settings(reader))
    print("\n## Every cell\n")
    print(cell_table(reader))
    if legacy:
        print("\n## Legacy adapter (`compliance_gaps`), same cases\n")
        print("| case | status | rows | section ids | wall s |")
        print("| --- | --- | --- | --- | --- |")
        for row in legacy:
            comparable = row.get("comparable") or {}
            print(
                f"| `{row['case']}` | {row.get('legacy_status') or row.get('error', '')} | "
                f"{comparable.get('row_count')} | {len(comparable.get('section_ids') or [])} | "
                f"{(row.get('payload') or {}).get('_wall_s')} |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
