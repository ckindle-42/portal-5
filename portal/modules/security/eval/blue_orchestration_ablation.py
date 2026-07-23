"""GATE-D full-corpus 1-vs-2-vs-3-section blue-orchestration ablation.

TASK-SEC-GATED-ABLATION-TO-COUNCIL-V1 Part I Phase 2: run three arms across
the whole captured corpus, in --replay-captured-red mode (no live red),
classify each (arm, scenario) via ablation_attribution.classify, aggregate
via summarize, and emit ABLATION_DECISION.json + a human report.

Arms:
  1section — blue._run_blue_chain_test(mode="discovery") with the reasoning
             model alone (the null hypothesis: no section split at all).
  2section — blue_orchestrate.run_blue_orchestration(sections=[tool, merged]).
  3section — blue_orchestrate.run_blue_orchestration(sections=[tool, reasoning,
             expert]) — the locked V2 trio.

Sequential only (CLAUDE.md: never run more than one bench/eval at a time —
VRAM/model-eviction contention gives bad data from concurrent runs).
Per-scenario checkpointed so a mid-corpus failure doesn't lose completed work.

Raw per-rep results (verdict, technique_ids, final evidence, returned tool
content, trace, instrument schema, ...) are persisted to a JSONL sidecar
(<out>.raw.jsonl) separately from classified outcomes.  ``--rescore`` makes
instrument development cheap, but is exploratory: a corpus inspected while
changing the scorer is development data, not independent confirmation.
Legacy schema-v1 multi-section traces omitted returned tool content and are
therefore ATTRIBUTION_UNKNOWN rather than retrospectively forced into a causal
retrieval/handoff class.

Run: python -m portal.modules.security.eval.blue_orchestration_ablation --reps 3
Rescore only (no live calls): python -m portal.modules.security.eval.blue_orchestration_ablation \
    --rescore ABLATION_DECISION.raw.jsonl --out ABLATION_DECISION.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from portal.modules.security.core._data import RESULTS_DIR
from portal.modules.security.core.agentic_blue_eval import load_episode
from portal.modules.security.core.blue import _run_blue_chain_test
from portal.modules.security.core.blue_orchestrate import SectionSpec, run_blue_orchestration
from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.siem.capture_store import list_captures
from portal.modules.security.eval.ablation_attribution import (
    ATTRIBUTION_SCHEMA_VERSION,
    DEGEN_ERR,
    DEGEN_RECALL,
    DOMINANT,
    DOMINANT_MARGIN,
    MAX_ATTRIBUTION_UNKNOWN,
    SPLIT_MARGIN,
    ArmScenarioOutcome,
    classify,
    decide_route,
    summarize,
)

# Locked V2 trio (b576439) — see task Appendix.
TOOL_MODEL = "granite4.1:8b-ctx8k"
REASONING_MODEL = "granite4.1:30b"
EXPERT_MODEL = "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0"
# 2-section "V1 shape": one generalist both hunts and concludes. Reuse the
# reasoning model in that dual role — no separate merged-model config exists
# for this arm (config/portal.yaml's blueteam-orchestrated variant only
# carries the 3-section trio), and reasoning-model-as-merged is the natural
# midpoint between 1section (no split) and 3section (full split).
MERGED_MODEL = REASONING_MODEL

# Council of Agreement roster (GATE-D ablation Part II-A, C4) — matches
# config/portal.yaml's blueteam-council variant defaults exactly, so a CLI
# --blue-mode council run and this ablation arm measure the same roster.
COUNCIL_MODELS = [REASONING_MODEL, "mistral-small3.2:24b", "qwen3.6:27b-q4_K_M"]
COUNCIL_ARBITER = EXPERT_MODEL
COUNCIL_QUORUM = 0.5

ARMS = ["1section", "2section", "3section"]
DEFAULT_OUT = Path("ABLATION_DECISION.json")


def _pending_instrument_validation() -> dict:
    """Fail-closed validation state for exploratory runs and old rescores."""
    return {
        "schema_version": ATTRIBUTION_SCHEMA_VERSION,
        "scorer_frozen": False,
        "scorer_hash": "",
        "development_corpus_id": "",
        "live_audit": {"status": "PENDING", "n": 0, "agreement": 0.0},
        "confirmatory": {"status": "PENDING", "independent": False, "corpus_id": ""},
        "oracle_evidence": {
            "status": "PENDING",
            "n": 0,
            "retrieval_mediated": False,
        },
    }


def _load_validation_manifest(path: str) -> dict:
    if not path:
        return _pending_instrument_validation()
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict):
        raise ValueError("validation manifest must be a JSON object")
    return data


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _backup_existing(path: Path) -> Path | None:
    """Unconditional backup-before-write (CLAUDE.md Checkpoint Backup Discipline)."""
    if not path.exists():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(f"{path.stem}_{stamp}{path.suffix}.bak")
    shutil.copy2(path, bak)
    print(f"Checkpoint backup: {path} -> {bak}")
    return bak


def _raw_path_for(out_path: Path) -> Path:
    return out_path.with_suffix(".raw.jsonl")


def _append_raw(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_raw(path: Path) -> list[dict]:
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _run_1section_raw(scenario_name: str, ground_truth: list[str], reps: int) -> list[dict]:
    """Gather raw (arm, scenario) reps for the 1-section arm — no classification."""
    sc = SCENARIOS[scenario_name]
    records = []
    for _ in range(reps):
        try:
            res = _run_blue_chain_test(
                model=REASONING_MODEL,
                scenario=sc,
                dry_run=False,
                lab_exec=False,
                query_live=False,
                mode="discovery",
            )
            technique_ids = [
                d.get("technique_id") for d in res.get("reported", []) if d.get("technique_id")
            ]
            verdict = "CONFIRMED" if technique_ids else "RULED_OUT"
            records.append(
                {
                    "arm": "1section",
                    "scenario": scenario_name,
                    "verdict": verdict,
                    "technique_ids": technique_ids,
                    "trace": res.get("trace", []),
                    "ground_truth": ground_truth,
                    "final_evidence": [
                        d.get("evidence", "") for d in res.get("reported", []) if d.get("evidence")
                    ],
                    "instrument_schema_version": ATTRIBUTION_SCHEMA_VERSION,
                    "match_grade": "NONE",
                    "similar_to": [],
                    "error": None,
                }
            )
        except Exception as exc:
            records.append(
                {
                    "arm": "1section",
                    "scenario": scenario_name,
                    "ground_truth": ground_truth,
                    "error": str(exc),
                }
            )
    return records


def _run_orchestrated_raw(
    arm: str, scenario_name: str, episode, ground_truth: list[str], reps: int
) -> list[dict]:
    """Gather raw (arm, scenario) reps for the 2/3-section/council arms — no classification."""
    extra_kwargs: dict = {}
    if arm == "2section":
        sections = [
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            SectionSpec(role="merged", model=MERGED_MODEL),
        ]
    elif arm == "council":
        sections = [
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            *(SectionSpec(role="reasoning", model=m) for m in COUNCIL_MODELS),
            SectionSpec(role="expert", model=COUNCIL_ARBITER),
        ]
        extra_kwargs["quorum"] = COUNCIL_QUORUM
    else:
        sections = [
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            SectionSpec(role="reasoning", model=REASONING_MODEL),
            SectionSpec(role="expert", model=EXPERT_MODEL),
        ]
    records = []
    for _ in range(reps):
        try:
            result = run_blue_orchestration(episode, sections=sections, **extra_kwargs)
            records.append(
                {
                    "arm": arm,
                    "scenario": scenario_name,
                    "verdict": result.verdict,
                    "technique_ids": result.technique_ids,
                    "trace": result.trace,
                    "ground_truth": ground_truth,
                    "final_evidence": result.evidence,
                    "instrument_schema_version": ATTRIBUTION_SCHEMA_VERSION,
                    "match_grade": result.match_grade,
                    "similar_to": result.similar_to,
                    "error": None,
                }
            )
        except Exception as exc:
            records.append(
                {
                    "arm": arm,
                    "scenario": scenario_name,
                    "ground_truth": ground_truth,
                    "error": str(exc),
                }
            )
    return records


def _classify_raw_record(record: dict) -> ArmScenarioOutcome | None:
    """Apply the CURRENT classify() to one raw record. None if it errored."""
    if record.get("error") is not None:
        return None
    return classify(
        arm=record["arm"],
        scenario=record["scenario"],
        verdict=record["verdict"],
        technique_ids=record["technique_ids"],
        ground_truth=set(record["ground_truth"]),
        trace=record["trace"],
        match_grade=record.get("match_grade", "NONE"),
        similar_to=record.get("similar_to"),
        grounding_verified=record.get("instrument_schema_version") == ATTRIBUTION_SCHEMA_VERSION,
    )


def _outcome_to_dict(o: ArmScenarioOutcome) -> dict:
    return {
        "arm": o.arm,
        "scenario": o.scenario,
        "outcome": o.outcome,
        "detail": o.detail,
        "grounded_tp": o.grounded_tp,
        "hallucinated": o.hallucinated,
        "ground_truth": o.ground_truth,
        "completion_state": o.completion_state,
        "retrieval_state": o.retrieval_state,
        "citation_state": o.citation_state,
        "secondary_failures": o.secondary_failures,
        "attribution_sources": o.attribution_sources,
    }


def _summary_to_dict(s) -> dict:
    return {
        "arm": s.arm,
        "n": s.n,
        "hits": s.hits,
        "novelty": s.novelty,
        "real_recall": s.real_recall,
        "miss_hist": s.miss_hist,
        "miss_counts": s.miss_counts,
        "miss_n": s.miss_n,
        "scenario_miss_counts": s.scenario_miss_counts,
        "scenario_miss_n": s.scenario_miss_n,
        "hallucination_rate": s.hallucination_rate,
        "nonconv_rate": s.nonconv_rate,
        "false_positive_rate": s.false_positive_rate,
        "attribution_unknown_rate": s.attribution_unknown_rate,
        "retrieval_state_hist": s.retrieval_state_hist,
        "secondary_failure_hist": s.secondary_failure_hist,
    }


def _decide_honest_blocked(error_rate: float, arms: dict) -> tuple[bool, str | None]:
    if error_rate > DEGEN_ERR:
        return True, f"error_rate {error_rate:.3f} > {DEGEN_ERR} — instrument or run is degenerate"
    all_low = all(a["real_recall"] < DEGEN_RECALL for a in arms.values())
    if all_low:
        max_dominant = max(
            (max(a["miss_hist"].values()) if a["miss_hist"] else 0.0) for a in arms.values()
        )
        if max_dominant < DOMINANT:
            return (
                True,
                "all arms real_recall < DEGEN_RECALL and no dominant miss class — inconclusive",
            )
    return False, None


def _write_report(path: Path, decision: dict) -> None:
    lines = [
        f"# Blue-Orchestration Ablation Report ({decision['generated_at']})",
        "",
        f"HEAD: `{decision['head']}`  reps={decision['reps']}  corpus_n={decision['corpus_n']}  "
        f"error_rate={decision['error_rate']}",
        "",
        "## Per-arm summary",
        "",
        "| arm | n | hits | novelty | real_recall | false_positive_rate | "
        "attribution_unknown_rate | nonconv_rate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for arm, s in decision["arms"].items():
        lines.append(
            f"| {arm} | {s['n']} | {s['hits']} | {s['novelty']} | {s['real_recall']} | "
            f"{s['false_positive_rate']} | {s['attribution_unknown_rate']} | "
            f"{s['nonconv_rate']} |"
        )
    lines += ["", "## Miss histograms (fraction of misses)", ""]
    for arm, s in decision["arms"].items():
        lines.append(f"- **{arm}**: {s['miss_hist']}")
    lines += [
        "",
        f"**best_multi_arm**: {decision['best_multi_arm']}  ",
        f"**split_proven** (3section beats 1section by >= {SPLIT_MARGIN} AND novelty > 0): "
        f"{decision['split_proven']}  ",
        f"**honest_blocked**: {decision['honest_blocked']}"
        + (f" — {decision['block_reason']}" if decision["block_reason"] else ""),
        f"**instrument_validation**: {decision['instrument_validation']}  ",
        f"**route**: {decision['route']} — {decision['route_reason']}  ",
        "",
        "A route of `INDETERMINATE` is mandatory for exploratory rescoring, "
        "unobservable retrieval payloads, unconfirmed scorer revisions, or unstable "
        f"dominance (threshold={DOMINANT}, margin={DOMINANT_MARGIN}, "
        f"max_unknown={MAX_ATTRIBUTION_UNKNOWN}).",
        "",
    ]
    path.write_text("\n".join(lines))


def _build_decision(
    all_records: list[dict],
    reps: int,
    corpus_n: int,
    out_path: Path,
    instrument_validation: dict | None = None,
) -> dict:
    """Classify every raw record with the CURRENT classify() and build the
    decision dict + report. No live calls — pure reclassification."""
    attempted = len(all_records)
    errored = sum(1 for r in all_records if r.get("error") is not None)

    present_arms = list(ARMS)
    if any(r["arm"] == "council" for r in all_records):
        # Additive-only: council is extra reporting data, never wired into
        # best_multi_arm/split_proven below — those stay 1/2/3section-only (I7).
        present_arms.append("council")

    arms_summary: dict[str, dict] = {}
    for arm in present_arms:
        arm_outcomes = [
            o
            for o in (_classify_raw_record(r) for r in all_records if r["arm"] == arm)
            if o is not None
        ]
        arms_summary[arm] = _summary_to_dict(summarize(arm, arm_outcomes))

    best_multi_arm = (
        "3section"
        if arms_summary["3section"]["real_recall"] >= arms_summary["2section"]["real_recall"]
        else "2section"
    )
    split_proven = (
        arms_summary["3section"]["real_recall"]
        >= arms_summary["1section"]["real_recall"] + SPLIT_MARGIN
        and arms_summary["3section"]["novelty"] > 0
    )
    error_rate = round(errored / attempted, 3) if attempted else 1.0
    honest_blocked, block_reason = _decide_honest_blocked(error_rate, arms_summary)

    decision = {
        "head": _git_head(),
        "generated_at": datetime.now(UTC).isoformat(),
        "reps": reps,
        "corpus_n": corpus_n,
        "error_rate": error_rate,
        "raw_instrument_schema_versions": sorted(
            {
                int(r.get("instrument_schema_version", 1))
                for r in all_records
                if r.get("error") is None
            }
        ),
        "arms": arms_summary,
        "best_multi_arm": best_multi_arm,
        "split_proven": split_proven,
        "honest_blocked": honest_blocked,
        "block_reason": block_reason,
        "instrument_validation": instrument_validation or _pending_instrument_validation(),
    }
    route, route_reason = decide_route(decision)
    decision["route"] = route
    decision["route_reason"] = route_reason

    out_path.write_text(json.dumps(decision, indent=2))
    print(f"\nDecision written -> {out_path}")

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / f"ABLATION_REPORT_{ts}.md"
    _write_report(report_path, decision)
    print(f"Report written -> {report_path}")
    print(json.dumps(decision, indent=2))

    if honest_blocked:
        print(f"\nHONEST_BLOCKED: {block_reason}")
    return decision


def _rescore(
    raw_path: Path, out_path: Path, reps: int, instrument_validation: dict | None = None
) -> int:
    """Reclassify every raw record on disk with the CURRENT classify() logic.
    No Ollama/pipeline calls — pure, fast, replayable scoring."""
    if not raw_path.exists():
        print(f"ERROR: raw results file not found: {raw_path}")
        return 1
    all_records = _load_raw(raw_path)
    scenarios = sorted({r["scenario"] for r in all_records})
    print(
        f"Rescoring {len(all_records)} raw records across {len(scenarios)} scenarios "
        f"(no live calls)..."
    )
    _backup_existing(out_path)
    decision = _build_decision(
        all_records,
        reps=reps,
        corpus_n=len(scenarios),
        out_path=out_path,
        instrument_validation=instrument_validation,
    )
    return 1 if decision["route"] in {"BLOCKED", "INDETERMINATE"} else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=int(os.environ.get("SWEEP_SCENARIOS_REPS", "3")))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--scenarios", default="")
    ap.add_argument(
        "--rescore",
        default="",
        help="Path to a raw .raw.jsonl file — reclassify with the current "
        "classify() logic and emit a fresh decision, with no live model calls.",
    )
    ap.add_argument(
        "--include-council",
        action="store_true",
        help="Opt-in: also run the 'council' arm (Council of Agreement, C4 POC). "
        "Never on by default — it's a 4th arm's worth of live model calls, and a "
        "bare full-corpus invocation must not silently 4x in cost.",
    )
    ap.add_argument(
        "--validation-manifest",
        default="",
        help="JSON manifest recording a frozen scorer, blinded live audit, independent "
        "confirmatory corpus, and oracle-evidence intervention. Without it, results "
        "are exploratory and route=INDETERMINATE.",
    )
    args = ap.parse_args()

    out_path = Path(args.out)
    instrument_validation = _load_validation_manifest(args.validation_manifest)

    if args.rescore:
        return _rescore(
            Path(args.rescore),
            out_path,
            args.reps,
            instrument_validation=instrument_validation,
        )

    reps = args.reps
    _backup_existing(out_path)

    if args.scenarios:
        scenarios = [s.strip() for s in args.scenarios.split(",")]
    else:
        scenarios = [s for s in SCENARIOS if list_captures(s)]

    arms = [*ARMS, "council"] if args.include_council else ARMS
    print(f"Ablation: {len(scenarios)} captured scenarios x {len(arms)} arms x {reps} reps")
    print(f"Scenarios: {scenarios}")

    raw_path = _raw_path_for(out_path)
    _backup_existing(raw_path)
    all_records: list[dict] = []
    if raw_path.exists():
        all_records = _load_raw(raw_path)
        print(f"Resuming from raw checkpoint: {len(all_records)} records already recorded")
    done_keys = {(r["arm"], r["scenario"]) for r in all_records}

    t0 = time.monotonic()
    for scenario_name in scenarios:
        episode = load_episode(scenario_name)
        if episode is None:
            print(f"SKIP {scenario_name}: no captured episode")
            continue
        ground_truth = sorted(episode.techniques)

        for arm in arms:
            if (arm, scenario_name) in done_keys:
                print(f"[skip] {arm} x {scenario_name} (checkpointed)")
                continue
            print(f"[run] {arm} x {scenario_name} ({reps} reps)...", flush=True)
            if arm == "1section":
                records = _run_1section_raw(scenario_name, ground_truth, reps)
            else:
                records = _run_orchestrated_raw(arm, scenario_name, episode, ground_truth, reps)

            for rec in records:
                _append_raw(raw_path, rec)
                all_records.append(rec)
                if rec.get("error") is not None:
                    print(f"    ERROR: {rec['error'][:150]}")
                else:
                    outcome = _classify_raw_record(rec)
                    print(f"    -> {outcome.outcome}")

    wall_s = round(time.monotonic() - t0, 1)
    print(f"\nAblation corpus run complete in {wall_s}s ({wall_s / 60:.1f}min)")

    decision = _build_decision(
        all_records,
        reps=reps,
        corpus_n=len(scenarios),
        out_path=out_path,
        instrument_validation=instrument_validation,
    )
    return 1 if decision["route"] in {"BLOCKED", "INDETERMINATE"} else 0


if __name__ == "__main__":
    sys.exit(main())
