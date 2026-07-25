"""Corpus-replay bench — validates BUILD_PROGRAM_BLUE_ORCHESTRATION_V3
(Mentor/Budgets/Barrier-tools) and the Council of Agreement against REAL
telemetry already ingested into lab Splunk (corpus injection Lanes A/B —
see docs/security/corpus_injection.md), with no live red exploitation and
no Caldera emulation.

Corpus events carry no `episode_id` (see SplunkBackend.query_episode's
docstring), so the per-episode query path can't reach them. Instead this
pulls raw, technique-labeled telemetry directly via
``SplunkBackend.query(technique_id, window)`` — the same method the
canned SPL detections use — and wraps it into a synthetic ``Episode``
whose ground truth is the technique the corpus subset is labeled with.
Blue never sees that label (I8); it only gets the raw telemetry, exactly
like a captured live episode.

Found live 2026-07-25 (curated 3-run smoke pass, see coding_task/):
  - Barrier tools (V3C) fire correctly end-to-end against real corpus
    telemetry (request_more / emit_verdict as genuine tool_calls).
  - granite4.1:30b confused T1558.004 (AS-REP roasting) with sibling
    T1558.003 (Kerberoasting) on real corpus data — reproduces
    KNOWN_LIMITATIONS.md's P5-SEC-BLUE-MITRE-001 on new data.
  - hf.co/HeYujie/Qwen3.5-27B-abliterated-GGUF degenerated into an
    ~8000-token evidence-abandoning loop as a council member — see
    blue_orchestrate._COUNCIL_UNFIT_MODELS.
  - Mentor (V3A) never fired: granite4.1:30b converges in 1 tool round,
    never reaching _MENTOR_STALL_TRIGGER. This module's WEAK_MODEL arm
    exists specifically to validate Mentor firing against a model that
    actually stalls.

Run directly: python3 -m portal.modules.security.core.corpus_replay_bench
Env vars:
    CORPUS_BENCH_TECHNIQUES  comma-separated technique-ID subset (default: all curated)
    CORPUS_BENCH_OUT         checkpoint path override
CLI flags:
    --resume PATH   resume from an existing checkpoint (skips completed cells)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from threading import Lock

from portal.modules.security.core.agentic_blue_eval import Episode, score_findings_tiered
from portal.modules.security.core.blue_orchestrate import (
    _COUNCIL_UNFIT_MODELS,
    SectionSpec,
    run_blue_orchestration,
)
from portal.modules.security.core.siem.spl_backend import SplunkBackend

# Curated technique set — verified live 2026-07-25 to have real corpus hits
# (Lane A BOTS + Lane B ATT&CK data). Re-verify with
# CorpusReplayBench.discover_curated_techniques() if the corpus changes.
CURATED_TECHNIQUES: dict[str, str] = {
    "T1190": "web:access",
    "T1611": "linux:auditd",
    "T1552.005": "web:access",
    "T1558.003": "windows:security",
    "T1558.004": "windows:security",
    "T1110.003": "windows:security",
    "T1053.005": "windows:security",
    "T1595": "web:access",
    "T1083": "web:access",
    "T1078": "web:access",
    "T1557": "windows:security",
    "T1550.002": "windows:security",
    "T1003.003": "windows:security",
    "T1047": "windows:security",
    "T1189": "web:access",
    "T1557.001": "windows:security",
    "T1552": "web:access",
}

# Strong baseline (best live recall per prior GATE-D sweeps).
TOOL_MODEL = "granite4.1:8b"
REASONING_MODEL = "granite4.1:30b"
EXPERT_MODEL = "granite4.1:8b"
MENTOR_MODEL = "granite4.1:8b"

# Deliberately weaker/smaller model for the dedicated Mentor-firing
# validation arm — the strong baseline above converges in 1 tool round and
# never reaches _MENTOR_STALL_TRIGGER (found live 2026-07-25); Mentor needs
# a model that actually stalls to be exercised at all.
WEAK_REASONING_MODEL = "hf.co/Nguuma/security-slm-unsloth-1.5b:latest"

# Council roster — deliberately excludes _COUNCIL_UNFIT_MODELS (data, not
# eviction; see blue_orchestrate.py). Add candidates here as they're vetted.
COUNCIL_MODELS = [m for m in ("granite4.1:30b", "cogito:32b") if m not in _COUNCIL_UNFIT_MODELS]

OUT_PATH = Path(
    os.environ.get(
        "CORPUS_BENCH_OUT",
        str(
            Path(__file__).resolve().parent / "results" / "checkpoints" / "corpus_replay_bench.json"
        ),
    )
)

_write_lock = Lock()


def _load_spl_detections() -> dict:
    import yaml

    spl_path = Path(__file__).resolve().parent / "siem" / "spl_detections.yaml"
    with spl_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _corpus_episode(technique_id: str, sourcetype: str) -> Episode | None:
    """Pull real corpus telemetry for technique_id via the same SplunkBackend
    method the canned SPL detections use. Returns None if the corpus has no
    (or no longer has) hits for this technique — a live-data drift signal,
    not a code bug."""
    backend = SplunkBackend()
    detections = _load_spl_detections()
    raw_spl = detections[technique_id]["spl"].split("|")[0].strip()
    search = f"search {raw_spl} evidence_origin=corpus:* | head 8"
    rows = backend._run_search(search, "0", "now")
    if not rows:
        return None
    lines = [r["fields"].get("_raw", "") for r in rows if r["fields"].get("_raw")]
    if not lines:
        return None
    label = re.sub(r"[^A-Za-z0-9]+", "_", technique_id).strip("_").lower()
    return Episode(
        scenario=f"corpus_{label}",
        target_host="lab-corpus-splunk",
        techniques=[technique_id],
        telemetry={sourcetype: lines},
        captured_at=time.time(),
    )


def discover_curated_techniques() -> dict[str, str]:
    """Live re-probe of every canned-SPL technique against the corpus,
    inferring sourcetype from each technique's own SPL. Re-run this and
    diff against CURATED_TECHNIQUES if the corpus has changed materially."""
    backend = SplunkBackend()
    detections = _load_spl_detections()
    found: dict[str, str] = {}
    for tid, spec in detections.items():
        raw_spl = spec["spl"].split("|")[0].strip()
        search = f"search {raw_spl} evidence_origin=corpus:* | head 8"
        try:
            rows = backend._run_search(search, "0", "now")
        except Exception:
            rows = []
        if not rows:
            continue
        m = re.search(r'sourcetype="?([\w:.-]+)"?', raw_spl)
        found[tid] = m.group(1) if m else "unknown"
    return found


def _load_checkpoint(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _backup_and_checkpoint(record: dict, results: list[dict], path: Path) -> None:
    """Thread-safe incremental write. Backs up the existing checkpoint file
    before the FIRST write of a run (not on every cell) — matches the
    Checkpoint Backup Discipline: never clear/overwrite a multi-hour
    checkpoint without a timestamped .bak first."""
    with _write_lock:
        key = (record.get("label"), record.get("mode"), record.get("model_arm"))
        results[:] = [
            r for r in results if (r.get("label"), r.get("mode"), r.get("model_arm")) != key
        ]
        results.append(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results, indent=2, default=str))


def _run_cell(
    *,
    label: str,
    technique_id: str,
    sourcetype: str,
    mode: str,
    model_arm: str,
    reasoning_model: str,
    mentor: bool,
    budgets: dict[str, int] | None,
    barrier_roles: set[str],
) -> dict:
    episode = _corpus_episode(technique_id, sourcetype)
    if episode is None:
        return {
            "label": label,
            "technique_expected": technique_id,
            "mode": mode,
            "model_arm": model_arm,
            "status": "skipped_no_corpus_data",
        }

    if mode == "orchestrated":
        sections = [
            SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
            SectionSpec(
                role="reasoning",
                model=reasoning_model,
                use_barrier_tools="reasoning" in barrier_roles,
            ),
            SectionSpec(
                role="expert", model=EXPERT_MODEL, use_barrier_tools="expert" in barrier_roles
            ),
        ]
    else:  # council
        sections = [SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True)]
        sections += [
            SectionSpec(role="reasoning", model=m, use_barrier_tools="reasoning" in barrier_roles)
            for m in COUNCIL_MODELS
        ]
        sections.append(SectionSpec(role="expert", model=EXPERT_MODEL))
    if mentor:
        sections.append(SectionSpec(role="mentor", model=MENTOR_MODEL))

    started = time.monotonic()
    result = run_blue_orchestration(
        episode,
        sections=sections,
        max_rounds=6,
        budgets=budgets,
        quorum=0.5,
    )
    elapsed = round(time.monotonic() - started, 1)
    scoring = score_findings_tiered(set(result.technique_ids), set(episode.techniques))
    mentor_entries = [t for t in result.trace if t.get("section") == "mentor"]

    return {
        "label": label,
        "technique_expected": technique_id,
        "mode": mode,
        "model_arm": model_arm,
        "status": "done",
        "verdict": result.verdict,
        "technique_ids": result.technique_ids,
        "match_grade": result.match_grade,
        "similar_to": result.similar_to,
        "ungrounded_claims": result.ungrounded_claims,
        "rounds": result.rounds,
        "elapsed_s": elapsed,
        "mentor_invocations": len(mentor_entries),
        "scoring_recall": scoring["overall"]["recall"],
        "trace": result.trace,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Corpus-replay V3 validation bench")
    parser.add_argument("--resume", metavar="PATH", help="Resume from an existing checkpoint")
    parser.add_argument(
        "--techniques", metavar="T1,T2", help="Comma-separated technique subset (default: all)"
    )
    parser.add_argument(
        "--skip-weak-arm",
        action="store_true",
        help="Skip the dedicated Mentor-firing validation arm (WEAK_REASONING_MODEL)",
    )
    args = parser.parse_args()

    out_path = Path(args.resume) if args.resume else OUT_PATH
    results = _load_checkpoint(out_path)
    if results:
        backup = out_path.with_name(f"{out_path.stem}_{time.strftime('%Y%m%dT%H%M%SZ')}.json.bak")
        shutil.copy(out_path, backup)
        print(f"Resuming {len(results)} completed cells from {out_path} (backed up to {backup})")

    done_keys = {(r.get("label"), r.get("mode"), r.get("model_arm")) for r in results}

    env_techniques = os.environ.get("CORPUS_BENCH_TECHNIQUES")
    if args.techniques:
        technique_subset = [t.strip() for t in args.techniques.split(",") if t.strip()]
    elif env_techniques:
        technique_subset = [t.strip() for t in env_techniques.split(",") if t.strip()]
    else:
        technique_subset = list(CURATED_TECHNIQUES.keys())

    cells: list[dict] = []
    for tid in technique_subset:
        sourcetype = CURATED_TECHNIQUES.get(tid)
        if not sourcetype:
            print(f"  SKIP {tid}: not in CURATED_TECHNIQUES")
            continue
        label = re.sub(r"[^A-Za-z0-9]+", "_", tid).strip("_").lower()

        # Arm 1: orchestrated, strong model, full V3 (mentor+budgets+barrier).
        #
        # Found live 2026-07-25 (first full 51-cell sweep): hunter=4 exhausts
        # after exactly 2 hunt-gather cycles (round count hits 4 mid-loop,
        # inside the "wants_more and not stalled: if _budget_exhausted():
        # break" branch in _run_three_section) -- before the Hunter's 3rd
        # call, so the stall cap (3 consecutive no-hypothesis rounds) never
        # gets a chance to fire and the Expert never gets a single turn.
        # 14/17 cells ended UNRESOLVED at exactly round=4 with wants_more
        # still True. This is a bench-budget miscalibration, not a V3
        # defect -- raised to give the Hunter room to actually reach a
        # conclusion or the stall handoff.
        cells.append(
            {
                "label": label,
                "technique_id": tid,
                "sourcetype": sourcetype,
                "mode": "orchestrated",
                "model_arm": "strong_full_v3",
                "reasoning_model": REASONING_MODEL,
                "mentor": True,
                "budgets": {"hunter": 10, "expert": 2},
                "barrier_roles": {"reasoning", "expert"},
            }
        )
        # Arm 2: council, strong roster (unfit models excluded), mentor+barrier.
        # Same fix: hunter=3 was too tight (found live 2026-07-25).
        cells.append(
            {
                "label": label,
                "technique_id": tid,
                "sourcetype": sourcetype,
                "mode": "council",
                "model_arm": "council_strong",
                "reasoning_model": REASONING_MODEL,
                "mentor": True,
                "budgets": {"hunter": 8},
                "barrier_roles": {"reasoning"},
            }
        )
        # Arm 3: orchestrated, WEAK model, mentor -- validates Mentor actually
        # fires against a model that stalls (the strong model never does).
        # Given a weaker model, more room to actually stall into the mentor
        # trigger and still reach a conclusion afterward.
        if not args.skip_weak_arm:
            cells.append(
                {
                    "label": label,
                    "technique_id": tid,
                    "sourcetype": sourcetype,
                    "mode": "orchestrated",
                    "model_arm": "weak_mentor_validation",
                    "reasoning_model": WEAK_REASONING_MODEL,
                    "mentor": True,
                    "budgets": {"hunter": 10},
                    "barrier_roles": set(),  # weak model unlikely to support tool calls reliably
                }
            )

    total = len(cells)
    print(f"Corpus-replay bench: {total} cells queued ({len(technique_subset)} techniques)")

    for i, cell in enumerate(cells, 1):
        key = (cell["label"], cell["mode"], cell["model_arm"])
        if key in done_keys:
            print(f"[{i}/{total}] SKIP (already done): {key}")
            continue
        print(f"[{i}/{total}] RUN: {key}")
        record = _run_cell(
            label=cell["label"],
            technique_id=cell["technique_id"],
            sourcetype=cell["sourcetype"],
            mode=cell["mode"],
            model_arm=cell["model_arm"],
            reasoning_model=cell["reasoning_model"],
            mentor=cell["mentor"],
            budgets=cell["budgets"],
            barrier_roles=cell["barrier_roles"],
        )
        _backup_and_checkpoint(record, results, out_path)
        status = record.get("status")
        if status == "done":
            print(
                f"    -> verdict={record['verdict']} techniques={record['technique_ids']} "
                f"mentor_invocations={record['mentor_invocations']} "
                f"recall={record['scoring_recall']} elapsed={record['elapsed_s']}s"
            )
        else:
            print(f"    -> {status}")

    print(f"\nDone. {len(results)} cells checkpointed at {out_path}")


if __name__ == "__main__":
    sys.exit(main())
