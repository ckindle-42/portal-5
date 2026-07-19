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

Run: python -m portal.modules.security.eval.blue_orchestration_ablation --reps 3
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
from portal.modules.security.eval.ablation_attribution import classify, summarize

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

ARMS = ["1section", "2section", "3section"]
DEFAULT_OUT = Path("ABLATION_DECISION.json")

SPLIT_MARGIN = 0.10
DEGEN_ERR = 0.20
DEGEN_RECALL = 0.05
DOMINANT = 0.40


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


def _run_1section(scenario_name: str, ground_truth: set[str], reps: int) -> list[dict]:
    sc = SCENARIOS[scenario_name]
    outcomes = []
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
            out = classify(
                arm="1section",
                scenario=scenario_name,
                verdict=verdict,
                technique_ids=technique_ids,
                ground_truth=ground_truth,
                trace=res.get("trace", []),
            )
            outcomes.append({"outcome": out, "error": None})
        except Exception as exc:
            outcomes.append({"outcome": None, "error": str(exc)})
    return outcomes


def _run_orchestrated(
    arm: str, scenario_name: str, episode, ground_truth: set[str], reps: int
) -> list[dict]:
    if arm == "2section":
        sections = [
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            SectionSpec(role="merged", model=MERGED_MODEL),
        ]
    else:
        sections = [
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            SectionSpec(role="reasoning", model=REASONING_MODEL),
            SectionSpec(role="expert", model=EXPERT_MODEL),
        ]
    outcomes = []
    for _ in range(reps):
        try:
            result = run_blue_orchestration(episode, sections=sections)
            out = classify(
                arm=arm,
                scenario=scenario_name,
                verdict=result.verdict,
                technique_ids=result.technique_ids,
                ground_truth=ground_truth,
                trace=result.trace,
                match_grade=result.match_grade,
                similar_to=result.similar_to,
            )
            outcomes.append({"outcome": out, "error": None})
        except Exception as exc:
            outcomes.append({"outcome": None, "error": str(exc)})
    return outcomes


def _outcome_to_dict(o) -> dict:
    return {
        "arm": o.arm,
        "scenario": o.scenario,
        "outcome": o.outcome,
        "detail": o.detail,
        "grounded_tp": o.grounded_tp,
        "hallucinated": o.hallucinated,
        "ground_truth": o.ground_truth,
    }


def _summary_to_dict(s) -> dict:
    return {
        "arm": s.arm,
        "n": s.n,
        "hits": s.hits,
        "novelty": s.novelty,
        "real_recall": s.real_recall,
        "miss_hist": s.miss_hist,
        "hallucination_rate": s.hallucination_rate,
        "nonconv_rate": s.nonconv_rate,
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


def _write_report(path: Path, decision: dict, all_outcomes: list[dict]) -> None:
    lines = [
        f"# Blue-Orchestration Ablation Report ({decision['generated_at']})",
        "",
        f"HEAD: `{decision['head']}`  reps={decision['reps']}  corpus_n={decision['corpus_n']}  "
        f"error_rate={decision['error_rate']}",
        "",
        "## Per-arm summary",
        "",
        "| arm | n | hits | novelty | real_recall | hallucination_rate | nonconv_rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, s in decision["arms"].items():
        lines.append(
            f"| {arm} | {s['n']} | {s['hits']} | {s['novelty']} | {s['real_recall']} | "
            f"{s['hallucination_rate']} | {s['nonconv_rate']} |"
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
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=int(os.environ.get("SWEEP_SCENARIOS_REPS", "3")))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--scenarios", default="")
    args = ap.parse_args()

    reps = args.reps
    out_path = Path(args.out)
    _backup_existing(out_path)

    if args.scenarios:
        scenarios = [s.strip() for s in args.scenarios.split(",")]
    else:
        scenarios = [s for s in SCENARIOS if list_captures(s)]

    print(f"Ablation: {len(scenarios)} captured scenarios x {len(ARMS)} arms x {reps} reps")
    print(f"Scenarios: {scenarios}")

    all_outcomes: list[dict] = []
    attempted = 0
    errored = 0

    checkpoint_path = out_path.with_suffix(".outcomes.json")
    if checkpoint_path.exists():
        all_outcomes = json.loads(checkpoint_path.read_text())
        print(f"Resuming from checkpoint: {len(all_outcomes)} outcomes already recorded")
    done_keys = {(o["arm"], o["scenario"]) for o in all_outcomes}

    t0 = time.monotonic()
    for scenario_name in scenarios:
        episode = load_episode(scenario_name)
        if episode is None:
            print(f"SKIP {scenario_name}: no captured episode")
            continue
        ground_truth = set(episode.techniques)

        for arm in ARMS:
            if (arm, scenario_name) in done_keys:
                print(f"[skip] {arm} x {scenario_name} (checkpointed)")
                continue
            print(f"[run] {arm} x {scenario_name} ({reps} reps)...", flush=True)
            if arm == "1section":
                results = _run_1section(scenario_name, ground_truth, reps)
            else:
                results = _run_orchestrated(arm, scenario_name, episode, ground_truth, reps)

            for r in results:
                attempted += 1
                if r["error"] is not None:
                    errored += 1
                    print(f"    ERROR: {r['error'][:150]}")
                    continue
                all_outcomes.append(_outcome_to_dict(r["outcome"]))
                print(f"    -> {r['outcome'].outcome}")

            checkpoint_path.write_text(json.dumps(all_outcomes, indent=2))

    wall_s = round(time.monotonic() - t0, 1)
    print(f"\nAblation corpus run complete in {wall_s}s ({wall_s / 60:.1f}min)")

    error_rate = round(errored / attempted, 3) if attempted else 1.0

    arms_summary: dict[str, dict] = {}
    for arm in ARMS:
        from portal.modules.security.eval.ablation_attribution import ArmScenarioOutcome

        arm_outcomes = [
            ArmScenarioOutcome(
                o["arm"],
                o["scenario"],
                o["outcome"],
                o["detail"],
                o["grounded_tp"],
                o["hallucinated"],
                o["ground_truth"],
            )
            for o in all_outcomes
            if o["arm"] == arm
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

    honest_blocked, block_reason = _decide_honest_blocked(error_rate, arms_summary)

    decision = {
        "head": _git_head(),
        "generated_at": datetime.now(UTC).isoformat(),
        "reps": reps,
        "corpus_n": len(scenarios),
        "error_rate": error_rate,
        "arms": arms_summary,
        "best_multi_arm": best_multi_arm,
        "split_proven": split_proven,
        "honest_blocked": honest_blocked,
        "block_reason": block_reason,
    }

    out_path.write_text(json.dumps(decision, indent=2))
    print(f"\nDecision written -> {out_path}")

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / f"ABLATION_REPORT_{ts}.md"
    _write_report(report_path, decision, all_outcomes)
    print(f"Report written -> {report_path}")

    print(json.dumps(decision, indent=2))

    if honest_blocked:
        print(f"\nHONEST_BLOCKED: {block_reason}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
