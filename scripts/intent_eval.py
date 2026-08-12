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
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTAL_YAML = REPO_ROOT / "config" / "portal.yaml"
RESULTS_DIR = REPO_ROOT / "tests" / "benchmarks" / "results"
REPORTS = REPO_ROOT / "reports"
SECURITY_CANDIDATES_DIR = REPO_ROOT / "tests" / "benchmarks" / "results" / "candidates"

SECURITY_TOOL_TEMPLATE_BLOCKED = {
    "hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M",
    "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0",
    "hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M",
    "cybersecqwen-4b-toolfix:latest",
}

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


# Alias: resolve_incumbent works for any workspace, not just intent incumbents.
_workspace_model_hint = resolve_incumbent


def _load_bench_repair_results() -> list[dict]:
    """bench_repair.py (coding intent) writes a markdown matrix, not a JSON file
    matching the {"results":[{"model","quality_score"}]} shape every other probe
    uses — cmd_analyze()'s generic _latest() glob can never find it. Parse the
    matrix table directly instead; "quality_score" here = one-shot pass rate
    (raw capability, comparable across workspaces the way the other probes' solo
    quality_score is)."""
    md_files = sorted(REPORTS.glob("CODING_BENCH_REPAIR*.md"))
    if not md_files:
        return []
    text = md_files[-1].read_text()
    row_re = re.compile(
        r"^\|\s*`([^`]+)`\s*\|\s*\S+\s*\|\s*`([^`]+)`\s*\|\s*([\d.]+)%\s*\(\d+\)\s*\|"
        r"\s*([\d.]+)%\s*\(\d+\)\s*\|",
        re.MULTILINE,
    )
    results = []
    for ws, model_hint, one_shot_pct, _repair_pct in row_re.findall(text):
        results.append(
            {
                "model": model_hint,
                "quality_score": round(float(one_shot_pct) / 100, 3),
                "avg_tps": None,
                "prompt_category": "coding_repair",
                "workspace": ws,
            }
        )
    return results


def _load_bench_capability_results() -> list[dict]:
    """bench_capability.py (general intent) has no --model flag (--workspace only)
    and writes results/v11_capability_<workspace>_<ts>.json in a nested
    {"results":[{"role","workspace","results":[ProbeResult...]}]} shape — not the
    flat {"model","quality_score"} shape cmd_analyze() expects, and under a
    "v11_capability_" prefix the generic glob never matches. Load every
    v11_capability_bench-*.json (latest per workspace, skipping .bak files),
    average each workspace's C1-C5 capability_score into one quality_score, and
    map workspace -> model_hint via portal.yaml so results key the same way
    every other probe's "model" field does."""
    files = sorted(RESULTS_DIR.glob("v11_capability_bench-*.json"))
    by_workspace: dict[str, Path] = {}
    for f in files:
        if f.suffix == ".bak" or ".bak" in f.name:
            continue
        m = re.match(r"v11_capability_(bench-[a-z0-9.\-]+)_\d{8}T\d{6}Z\.json$", f.name)
        if not m:
            continue
        ws = m.group(1)
        # dict preserves insertion order; sorted() above means later files win
        by_workspace[ws] = f

    results: list[dict] = []
    for ws, f in by_workspace.items():
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        arm_scores: dict[str, float] = {}
        for block in data.get("results", []):
            role = block.get("role")
            probe_results = block.get("results", [])
            scores = [
                r["capability_score"]
                for r in probe_results
                if r.get("capability_score") is not None
            ]
            if not scores:
                continue
            arm_scores[role] = round(sum(scores) / len(scores), 3)
        if "candidate" not in arm_scores:
            continue
        hint = _workspace_model_hint(ws) or ws
        results.append(
            {
                "model": hint,
                "quality_score": arm_scores["candidate"],
                "incumbent_quality": arm_scores.get("baseline"),
                "avg_tps": None,
                "prompt_category": "general_capability",
                "workspace": ws,
            }
        )
    return results


def _load_candidate_eval_results() -> list[dict]:
    """candidate-eval (security intent) writes to
    portal/modules/security/core/results/candidates/cand_*.json — a directory
    cmd_analyze() never looked at (it only globs RESULTS_DIR under
    tests/benchmarks/results/), and in a per-scenario shape, not
    {"model","quality_score"}. Load every cand_*.json (latest timestamp per
    candidate tag wins — this also self-corrects for stray --dry-run artifacts,
    which sort earlier than a real --lab-exec run for the same candidate), and
    reduce to quality_score = mean(unique_coverage) across scenarios that
    actually ran (skips SKIPped/None scenarios), which is this probe's
    coverage-of-the-intended-chain metric — the closest single-number analog to
    the other probes' quality_score. Candidates with no file at all (failed
    intake) are correctly left absent, which cmd_analyze() already reports
    honestly as "no result row"."""
    if not SECURITY_CANDIDATES_DIR.exists():
        return []
    files = sorted(SECURITY_CANDIDATES_DIR.glob("cand_*.json"))
    by_candidate: dict[str, Path] = {}
    for f in files:
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        cand = data.get("candidate", "")
        if not cand:
            continue
        by_candidate[cand] = f  # sorted() -> later timestamp overwrites, wins

    results: list[dict] = []
    for cand, f in by_candidate.items():
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        cand_results = data.get("candidate_results", [])
        incumbent_results = data.get("incumbent_results", [])
        scenario_deltas = [
            r for r in data.get("deltas", []) if r.get("scenario") != "__aggregate__"
        ]
        comparable = {r.get("scenario") for r in scenario_deltas}
        coverages = [
            r["unique_coverage"]
            for r in cand_results
            if r.get("scenario") in comparable and r.get("unique_coverage") is not None
        ]
        wins = sum(1 for r in cand_results if r.get("lab_success"))
        scored = sum(1 for r in cand_results if r.get("unique_coverage") is not None)
        if not coverages:
            continue
        incumbent_coverages = [
            r["unique_coverage"]
            for r in incumbent_results
            if r.get("scenario") in comparable and r.get("unique_coverage") is not None
        ]
        aggregate_delta = next(
            (r for r in data.get("deltas", []) if r.get("scenario") == "__aggregate__"),
            None,
        )
        results.append(
            {
                "model": cand,
                "quality_score": round(sum(coverages) / len(coverages), 3),
                "incumbent_quality": (
                    round(sum(incumbent_coverages) / len(incumbent_coverages), 3)
                    if incumbent_coverages
                    else None
                ),
                "avg_tps": None,
                "prompt_category": "security_chain_coverage",
                "lab_wins": f"{wins}/{scored}",
                "native_delta": aggregate_delta,
            }
        )
    return results


def load_intent_assignments() -> dict[str, str]:
    """Read the tag->intent map produced by the planning step (Part 3a)."""
    p = REPORTS / "intent_assignments.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _missing_result_note(intent: str, candidate: str) -> str:
    if intent == "security" and candidate in SECURITY_TOOL_TEMPLATE_BLOCKED:
        return "BLOCKED — tool-template incompatible at intake"
    return "no result row"


def _render_rows(rows: list[dict]) -> None:
    print(f"\n{'=' * 104}")
    print(
        "INTENT-ALIGNED EVALUATION — candidate vs incumbent (delta = candidate - incumbent quality)"
    )
    print(f"{'=' * 104}")
    print(f"{'intent':14s} {'candidate':46s} {'cand_q':>7s} {'inc_q':>6s} {'Δ':>7s} {'tps':>7s}")
    print("-" * 104)
    for row in sorted(
        rows, key=lambda x: (x.get("intent", ""), -(x.get("delta_vs_incumbent") or -9))
    ):
        if row.get("note"):
            print(
                f"{row.get('intent', ''):14s} {row.get('candidate', '(all)')[:46]:46s}  -- {row['note']}"
            )
            continue
        delta = row.get("delta_vs_incumbent")
        delta_text = f"{delta:+.3f}" if delta is not None else "  n/a"
        print(
            f"{row['intent']:14s} {row['candidate'][:46]:46s} {str(row['cand_quality']):>7s} "
            f"{str(row['incumbent_quality']):>6s} {delta_text:>7s} {str(row['cand_tps']):>7s}"
        )


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
    print(
        f"Wrote {out.relative_to(REPO_ROOT)} — {len(by_intent)} intent groups, "
        f"{len(assignments)} models. Run it, then: intent_eval.py analyze"
    )
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
    for intent in sorted(set(assignments.values())):
        ws, probe = INTENT_MAP.get(intent, ("", "bench_capability"))
        prefix = PROBE_PREFIX.get(probe, probe)
        if probe == "bench_repair":
            results = _load_bench_repair_results()
            data = {"results": results} if results else None
        elif probe == "bench_capability":
            results = _load_bench_capability_results()
            data = {"results": results} if results else None
        elif probe == "candidate-eval":
            results = _load_candidate_eval_results()
            data = {"results": results} if results else None
        else:
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
                rows.append(
                    {"intent": intent, "candidate": t, "note": _missing_result_note(intent, t)}
                )
                continue
            cq = r.get("quality_score")
            paired_inc_q = r.get("incumbent_quality", inc_q)
            delta = (
                round(cq - paired_inc_q, 3) if cq is not None and paired_inc_q is not None else None
            )
            rows.append(
                {
                    "intent": intent,
                    "candidate": t,
                    "incumbent": inc,
                    "cand_quality": cq,
                    "incumbent_quality": paired_inc_q,
                    "delta_vs_incumbent": delta,
                    "cand_tps": r.get("avg_tps"),
                    "prompt_category": r.get("prompt_category"),
                    "native_delta": r.get("native_delta"),
                }
            )

    _render_rows(rows)

    out = REPORTS / "INTENT_EVAL_DECISION.json"
    out.write_text(json.dumps({"rows": rows}, indent=2))
    print(f"\nWrote {out.relative_to(REPO_ROOT)}")
    print(
        "\nBEATS incumbent (positive Δ) = swap candidate. MATCHES + smaller/faster = swap on cost."
    )
    print("TRAILS = keep-as-bench or drop. Operator decides — PROMOTE_POLICY=confirm.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Intent-aligned candidate-vs-incumbent eval driver.")
    ap.add_argument(
        "mode", choices=["plan", "analyze"], help="plan = emit run script; analyze = diff results"
    )
    args = ap.parse_args(argv)
    return cmd_plan() if args.mode == "plan" else cmd_analyze()


if __name__ == "__main__":
    raise SystemExit(main())
