#!/usr/bin/env python3
"""WFE canary — one live row per workload before a long campaign may start.

realuse_v1 burned four campaign attempts on setup failures that each showed in
exactly one live row: a 0 s BLOCKED on a missing tool, "file not found" from
unstaged fixtures, a conformance abort on a polluted arm list, and reused rows
re-graded to PASS. Unit tests and dry-runs passed every time. This gate runs
those rows FIRST, in a separate `<id>_canary` campaign, and classifies each:

  SETUP   the harness failed the row, not the model — 0 s BLOCKED, "requires
          tools the harness does not offer", a fixture/file not found or
          ENOENT in the note or tool output, a reused/re-graded row, a
          conformance or preflight abort, HARNESS_ERROR, or a row that never
          ran.
  MODEL   anything else — the seat answered and was measured.

Exit 0 only when every selected row ran and none is SETUP. Reached through
`wfe_campaign.sh <id> ... --canary` (job specs: a `canary: <step>` step).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from tests.wfe import campaign as camp
from tests.wfe.realuse_paths import named_paths
from tests.wfe.runner import load_suite, required_tools

SETUP = "SETUP"
MODEL = "MODEL"
#: A canary row never reuses or re-grades: a copied row proves nothing live.
_REUSE_MARKS = ("reused_from", "regraded_outcome", "original_outcome", "rescore", "original")
_TOOL_NOTE = "requires tools the harness does not offer"
_MISSING_FILE = ("file not found", "enoent")
#: A tool that could not run at all is the harness/stack failing, never the model: realuse
#: autocoding canary 10-30 classed seven `OCI runtime create failed` sandbox calls as MODEL.
_TOOL_INFRA = (
    "oci runtime",
    "error response from daemon",
    "docker not found",
    "docker_unavailable",
    "path outside the evaluation namespace",
    "returned an mcp tool error",
)
#: A 0-second row never reached a model — the instrument refused it.
_UNRUN_STATES = frozenset({"PENDING", "MISSING", "SKIPPED_DECIDED", "NO_ROW"})


def canary_campaign_id(cid: str) -> str:
    """`<id>_canary`, idempotent so a re-dispatch cannot nest suffixes."""
    return cid if cid.endswith("_canary") else f"{cid}_canary"


def _task_exercise(task: dict) -> tuple[bool, bool]:
    """(exercises fixtures, exercises tool grounding) for one task."""
    if task is None:
        return False, False
    return bool(named_paths(task)), bool(required_tools(task))


def select_rows(plan_path: Path, tier: str, workspace: str | None = None) -> list[dict]:
    """One incumbent row per workload, preferring tasks that exercise fixtures
    AND tool grounding, then tool grounding, then fixtures, then the first
    home task. A workload with no eligible row gets a NO_ROW stub so the gate
    reports it instead of skipping it."""
    matrix = camp.expand_matrix(plan_path, 1, False, None, None, None, workspace, tier)
    incumbent = [r for r in matrix if r.get("arm_role") == "incumbent"]
    by_ws: dict[str, list[dict]] = {}
    for r in incumbent:
        by_ws.setdefault(r["workspace"], []).append(r)
    plan = yaml.safe_load(plan_path.read_text()) or {}
    out: list[dict] = []
    tasks: dict = {}
    for ws in sorted(plan.get("workloads") or {}):
        pool = [r for r in by_ws.get(ws, []) if r.get("is_home")] or by_ws.get(ws, [])
        if not pool:
            out.append(_no_row_stub(plan_path, plan, ws))
            continue
        best, best_key = pool[0], _task_exercise(_task_of(pool[0], tasks))
        for r in pool[1:]:
            key = _task_exercise(_task_of(r, tasks))
            if key > best_key:
                best, best_key = r, key
        out.append(best)
    return out


def _task_of(row: dict, cache: dict) -> dict | None:
    sp = row.get("suite_path")
    if not sp:
        return None
    if sp not in cache:
        try:
            cache[sp] = {t["id"]: t for t in load_suite(sp)}
        except Exception:  # noqa: BLE001 — an unreadable suite must not kill selection
            cache[sp] = {}
    return cache[sp].get(row.get("task_id"))


def _no_row_stub(plan_path: Path, plan: dict, ws: str) -> dict:
    from tests.wfe.campaign import arm_spec

    entry = ((plan.get("workloads") or {}).get(ws) or {}).get("arms", {}).get("incumbent")
    arm = arm_spec(entry)[0] if entry else ""
    return {
        "run_id": f"{ws}|{arm}|canary|no-row|r0",
        "workspace": ws,
        "arm": arm,
        "model": arm,
        "overrides": {},
        "arm_role": "incumbent",
        "tier": "canary",
        "suite": "",
        "suite_path": "",
        "task_id": "-",
        "repeat": 0,
        "is_home": True,
        "state": "NO_ROW",
        "note": "no eligible incumbent task in the plan's home suite",
    }


def _note_text(row: dict) -> str:
    return str(row.get("notes") or row.get("note") or "")


def _first_note(row: dict) -> str:
    text = _note_text(row).strip()
    line = text.splitlines()[0] if text else ""
    return " ".join(line.split())[:160]


def _tool_outputs(row: dict) -> str:
    return " ".join(str(e.get("output") or "") for e in row.get("tool_call_log") or [])


def _is_zero_second(row: dict) -> bool:
    wall = (row.get("economics") or {}).get("wall_s")
    return not row.get("turns") and not wall


def classify_row(row: dict) -> str:
    """SETUP or MODEL for one canary row (manifest stub merged with its row file)."""
    outcome = str(row.get("outcome") or row.get("state") or "PENDING")
    if any(row.get(mark) for mark in _REUSE_MARKS):
        return SETUP
    if outcome == "HARNESS_ERROR" or outcome in _UNRUN_STATES:
        return SETUP
    note = _note_text(row)
    if camp._PREFLIGHT_BLOCK in note or _TOOL_NOTE in note:
        return SETUP
    blob = f"{note} {_tool_outputs(row)}".lower()
    if any(sig in blob for sig in _MISSING_FILE + _TOOL_INFRA):
        return SETUP
    if outcome == "BLOCKED" and _is_zero_second(row):
        return SETUP
    return MODEL


def _conformance_findings(arms: set[str], workspaces: set[str]) -> list[str]:
    """The wfe_campaign.sh conformance gate, narrowed to the canary's arms."""
    if os.environ.get("WFE_SKIP_CONFORMANCE") == "1":
        return []
    from tests.wfe import settings_audit

    ordered = sorted(arms)
    spaces = {ws.split("::")[0] for ws in workspaces}
    bad: list = [
        v
        for v in settings_audit.run_audit()["violations"]
        if v["severity"] in ("WARN", "FAIL") and v["workspace"].split("::")[0] in spaces
    ]
    for audited in (
        settings_audit.audit_tags(ordered),
        settings_audit.audit_renderer_gate(ordered),
    ):
        bad += [v for v in audited["violations"] if v["severity"] in ("WARN", "FAIL")]
    return [
        f"{v['severity']} {v['workspace']}: {v['kind']} — {str(v['detail'])[:200]}" for v in bad
    ]


def _fixture_failures(selected: list[dict]) -> list[str]:
    """Stage and resolve every fixture path the selected tasks name."""
    from tests.wfe import realuse_paths

    tasks = [t for t in (_task_of(r, {}) for r in selected) if t is not None]
    if not tasks:
        return []
    from tests.wfe.eval_mode import OUTPUT_ROOT

    _, failures = realuse_paths.audit(tasks, output_root=OUTPUT_ROOT, repo=camp.REPO)
    return failures


def _print_table(records: list[dict]) -> None:
    cols = ("workload", "task", "outcome", "class", "first note")
    widths = [len(c) for c in cols]
    table = [
        (
            r["workspace"],
            str(r.get("task_id")),
            str(r.get("outcome") or r.get("state") or "PENDING"),
            r["class"],
            r["note"],
        )
        for r in records
    ]
    for row in table:
        widths = [max(w, len(v)) for w, v in zip(widths, row, strict=True)]
    print(
        f"{'workload':<{widths[0]}}  {'task':<{widths[1]}}  {'outcome':<{widths[2]}}  "
        f"{'class':<{widths[3]}}  first note"
    )
    for row in table:
        print("  ".join(f"{v:<{w}}" for v, w in zip(row, widths, strict=True)).rstrip())


def _records_for(cd: Path, selected: list[dict]) -> list[dict]:
    manifest = camp.load_manifest(cd)
    stubs = {r["run_id"]: r for r in manifest["rows"]}
    out = []
    for r in selected:
        stub = stubs.get(r["run_id"], r)
        path = camp._row_path(cd, r["run_id"])
        measured = json.loads(path.read_text()) if path.is_file() else {}
        merged = {**stub, **measured}
        out.append(
            {
                "workspace": merged.get("workspace"),
                "task_id": merged.get("task_id"),
                "outcome": merged.get("outcome") or merged.get("state") or "PENDING",
                "class": classify_row(merged),
                "note": _first_note(merged),
            }
        )
    return out


def _gate_table(cid: str, selected: list[dict], outcome: str, reason: str) -> int:
    _print_table(
        [
            {
                "workspace": r["workspace"],
                "task_id": r["task_id"],
                "outcome": outcome,
                "class": SETUP,
                "note": reason,
            }
            for r in selected
        ]
    )
    print(f"CANARY {cid}: SETUP ({len(selected)} of {len(selected)} row(s)) — {reason}")
    return 1


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tests.wfe.canary")
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--plan", default=str(camp.REPO / "tests/wfe/workloads.yaml"))
    ap.add_argument("--tier", default="confirm", choices=("screen", "confirm", "realuse"))
    ap.add_argument("--workspace")
    ap.add_argument("--budget-s", type=int, default=1800)
    ap.add_argument("--max-turns", type=int, default=16)
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def run_canary(argv: list[str] | None = None) -> int:
    ap = _parser()
    args, extra = ap.parse_known_args(argv)
    if [tok for tok in extra if tok != "--judge"]:
        ap.error(f"unrecognized arguments: {' '.join(extra)}")
    cid = canary_campaign_id(args.campaign_id)
    plan = Path(args.plan)
    selected = select_rows(plan, args.tier, args.workspace)
    if not selected:
        print(f"CANARY {cid}: SETUP — no incumbent row selected (plan {plan})")
        return 1
    if args.dry_run:
        for r in selected:
            print(
                f"  {r['workspace']}  {r['task_id']}  arm={r['arm']}  "
                f"mode={r.get('tool_mode') or 'sandbox'}"
            )
        print(f"CANARY {cid}: dry run — {len(selected)} row(s) selected")
        return 0
    if not camp.ollama_reachable():
        return _gate_table(cid, selected, "ABORT", "chat engine unreachable")
    if failures := _fixture_failures(selected):
        return _gate_table(cid, selected, "FIXTURES", failures[0])
    if findings := _conformance_findings(
        {r["arm"] for r in selected}, {r["workspace"] for r in selected}
    ):
        return _gate_table(cid, selected, "CONFORMANCE", findings[0])
    try:
        cd = camp.open_campaign(cid, plan, selected, append=True)
        camp.gate_execution(cd)
    except camp.GateRefused as e:
        print(f"CANARY {cid}: SETUP — gate refused: {e}")
        return 1
    for arm in sorted({r["arm"] for r in selected}):
        camp.execute_arm(
            cd,
            arm,
            args.max_turns,
            args.budget_s,
            None,
            False,
            args.notify,
            rerun_failed=True,
            halt=True,
            curtail=False,
            fresh_incumbent=True,
        )
    records = _records_for(cd, selected)
    _print_table(records)
    setup = [r for r in records if r["class"] == SETUP]
    print(
        f"CANARY {cid}: {'SETUP' if setup else 'PASS'} "
        f"({len(setup)} setup row(s) of {len(records)})"
    )
    return 1 if setup else 0


def _cli() -> int:
    try:
        return run_canary()
    except camp.GateRefused as e:
        print(e, file=sys.stderr)
        return camp.EXIT_GATE


if __name__ == "__main__":
    raise SystemExit(_cli())
