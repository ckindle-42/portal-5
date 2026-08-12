#!/usr/bin/env python3
"""Intent-aligned evaluation driver — TASK_MODEL_INTENT_EVAL_V1.

Runs each pending model through the probe that matches its INTENT (the job of the
workspace it would serve), against the CURRENT INCUMBENT of that workspace, and
reports a delta table. This is the comparison the earlier decision sheet lacked:
"does this candidate beat the model we already run for this job?" — not "how does
it score in isolation on a generic prompt."

Design note (honest): only reasoning/mtp/research probes and the security
candidate-eval carry a built-in baseline. The other probes score solo. So this
driver runs the SAME probe for both candidate and incumbent and diffs their
result JSONs at the analysis layer — a uniform delta regardless of whether the
probe has native baseline support.

This driver does NOT run inference itself. It (1) resolves each intent's incumbent
from portal.yaml, (2) emits the exact probe commands to run (candidate + incumbent
through the same harness), and (3) once results exist, diffs them into a decision
table. Split into plan/analyze so the long inference sweep is a separate, resumable
step. PROMOTE_POLICY=confirm: reports deltas, changes no fleet config.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTAL_YAML = REPO_ROOT / "config" / "portal.yaml"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
REPORTS = REPO_ROOT / "reports"

# intent domain -> (workspace whose model_hint is the incumbent, probe command stem)
INTENT_MAP: dict[str, tuple[str, str]] = {
    "coding": ("auto-coding", "bench_repair"),
    "reasoning": ("auto-reasoning", "bench_reasoning_probe"),
    "research": ("auto-research", "bench_research_probe"),
    "vision": ("auto-vision", "bench_vision_probe"),
    "security": ("auto-security", "candidate-eval"),
    "general": ("auto-daily", "bench_capability"),
    "long-context": ("auto-research", "bench_long_context_probe"),
    "math": ("auto-math", "bench_reasoning_probe"),
    "compliance": ("auto-compliance", "bench_compliance_probe"),
    "spl": ("auto-spl", "bench_spl_probe"),
    "cad": ("auto-cad", "bench_cad_probe"),
    "data": ("auto-data", "bench_data_probe"),
    "tools": ("tools-specialist", "bench_tool_use_probe"),
    "mtp-speculative": ("auto-reasoning", "bench_mtp_probe"),
    "abliterated": ("auto-general-uncensored", "bench_refusal_preservation_probe"),
}

# probe stem -> results filename prefix (for the diff step)
PROBE_PREFIX = {
    "bench_reasoning_probe": "reasoning_probe",
    "bench_research_probe": "research_probe",
    "bench_vision_probe": "vision_probe",
    "bench_long_context_probe": "long_context_probe",
    "bench_mtp_probe": "mtp_probe",
    "bench_refusal_preservation_probe": "refusal_preservation_probe",
    "bench_tool_use_probe": "tool_use_probe",
    "bench_cad_probe": "cad_probe",
    "bench_spl_probe": "spl_probe",
    "bench_compliance_probe": "compliance_probe",
    "bench_data_probe": "data_probe",
    "bench_capability": "capability",
    "bench_repair": "repair",
    "candidate-eval": "cand",
}


def resolve_incumbent(workspace: str) -> str:
    try:
        d = yaml.safe_load(PORTAL_YAML.read_text()) or {}
    except Exception:
        return ""
    return (d.get("workspaces", {}).get(workspace, {}) or {}).get("model_hint", "")


def load_intent_assignments() -> dict[str, str]:
    """Read the tag->intent map produced by the planning step (Part 3a)."""
    p = REPORTS / "intent_assignments.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def cmd_plan() -> int:
    """Emit the ordered probe commands: for each intent domain, one candidate run
    plus one incumbent run through the same harness."""
    assignments = load_intent_assignments()
    if not assignments:
        print("No reports/intent_assignments.json — write it first (tag -> intent domain).")
        return 1
    by_intent: dict[str, list[str]] = {}
    for tag, intent in assignments.items():
        by_intent.setdefault(intent, []).append(tag)

    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    seen_incumbent: set[str] = set()
    for intent, tags in sorted(by_intent.items()):
        ws, probe = INTENT_MAP.get(intent, ("", "bench_capability"))
        inc = resolve_incumbent(ws)
        lines.append(f"# ===== intent: {intent}  (incumbent workspace {ws} -> {inc}) =====")
        if probe == "candidate-eval":
            for t in tags:
                lines.append(
                    f"python3 -m portal.modules.security.core candidate-eval "
                    f"--candidate '{t}' --slot solo --force --lab-exec"
                )
            continue
        cand_models = " ".join(f"--model '{t}'" for t in tags)
        # incumbent through the same probe, once per intent
        inc_flag = f"--model '{inc}'" if inc and inc not in seen_incumbent else ""
        if inc:
            seen_incumbent.add(inc)
        if probe == "bench_repair":
            lines.append(f"python3 tests/benchmarks/bench_repair.py --models {','.join(tags)}")
        else:
            lines.append(f"python3 tests/benchmarks/{probe}.py {cand_models} {inc_flag}".rstrip())
        lines.append("")
    out = REPORTS / "intent_eval_run.sh"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out.relative_to(REPO_ROOT)} — {len(by_intent)} intent groups, "
          f"{len(assignments)} models. Run it, then: intent_eval.py analyze")
    return 0


def _latest(prefix: str) -> dict | None:
    fs = sorted(glob.glob(str(RESULTS_DIR / f"{prefix}_*.json")))
    if not fs:
        return None
    try:
        return json.loads(Path(fs[-1]).read_text())
    except Exception:
        return None


def cmd_analyze() -> int:
    """Diff candidate vs incumbent per intent, emit the decision table."""
    assignments = load_intent_assignments()
    incumbents = {intent: resolve_incumbent(ws) for intent, (ws, _) in INTENT_MAP.items()}

    # index every result row by model across the relevant probe files
    rows: list[dict] = []
    for intent in sorted({i for i in assignments.values()}):
        ws, probe = INTENT_MAP.get(intent, ("", "bench_capability"))
        prefix = PROBE_PREFIX.get(probe, probe)
        data = _latest(prefix)
        if not data:
            rows.append({"intent": intent, "note": f"no {prefix}_*.json results yet"})
            continue
        results = data.get("results", []) if isinstance(data, dict) else data
        by_model = {r.get("model"): r for r in results if isinstance(r, dict)}
        inc = incumbents.get(intent, "")
        inc_q = (by_model.get(inc) or {}).get("quality_score")
        cand_tags = [t for t, i in assignments.items() if i == intent]
        for t in cand_tags:
            r = by_model.get(t)
            if not r:
                rows.append({"intent": intent, "candidate": t, "note": "no result row"})
                continue
            cq = r.get("quality_score")
            delta = (round(cq - inc_q, 3) if cq is not None and inc_q is not None else None)
            rows.append({
                "intent": intent, "candidate": t, "incumbent": inc,
                "cand_quality": cq, "incumbent_quality": inc_q,
                "delta_vs_incumbent": delta, "cand_tps": r.get("avg_tps"),
                "prompt_category": r.get("prompt_category"),
            })

    # render
    print(f"\n{'='*104}")
    print("INTENT-ALIGNED EVALUATION — candidate vs incumbent (delta = candidate - incumbent quality)")
    print(f"{'='*104}")
    print(f"{'intent':14s} {'candidate':46s} {'cand_q':>7s} {'inc_q':>6s} {'Δ':>7s} {'tps':>7s}")
    print("-" * 104)
    for r in sorted(rows, key=lambda x: (x.get("intent", ""), -(x.get("delta_vs_incumbent") or -9))):
        if r.get("note"):
            print(f"{r.get('intent',''):14s} {r.get('candidate','(all)')[:46]:46s}  -- {r['note']}")
            continue
        d = r.get("delta_vs_incumbent")
        ds = f"{d:+.3f}" if d is not None else "  n/a"
        print(f"{r['intent']:14s} {r['candidate'][:46]:46s} {str(r['cand_quality']):>7s} "
              f"{str(r['incumbent_quality']):>6s} {ds:>7s} {str(r['cand_tps']):>7s}")

    out = REPORTS / "INTENT_EVAL_DECISION.json"
    out.write_text(json.dumps({"rows": rows}, indent=2))
    print(f"\nWrote {out.relative_to(REPO_ROOT)}")
    print("\nBEATS incumbent (positive Δ) = swap candidate. MATCHES + smaller/faster = swap on cost.")
    print("TRAILS = keep-as-bench or drop. Operator decides — PROMOTE_POLICY=confirm.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Intent-aligned candidate-vs-incumbent eval driver.")
    ap.add_argument("mode", choices=["plan", "analyze"], help="plan = emit run script; analyze = diff results")
    args = ap.parse_args(argv)
    return cmd_plan() if args.mode == "plan" else cmd_analyze()


if __name__ == "__main__":
    raise SystemExit(main())
