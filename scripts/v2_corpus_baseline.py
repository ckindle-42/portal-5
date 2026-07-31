#!/usr/bin/env python3
"""Run the exact pre-V3 blue orchestration against the current 17-cell corpus.

Execute this script with ``PYTHONPATH`` pointing at a detached checkout of the
pre-V3 commit and with that checkout as the working directory.  The script
intentionally supplies only V2 ``SectionSpec`` fields and no Mentor, per-role
budgets, barrier tools, or V4 behavior switches.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

import yaml

from portal.modules.security.core.agentic_blue_eval import Episode, score_findings_tiered
from portal.modules.security.core.blue_orchestrate import (
    SectionSpec,
    run_blue_orchestration,
)
from portal.modules.security.core.siem.spl_backend import SplunkBackend

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

TOOL_MODEL = "bench-granite41-8b"
REASONING_MODEL = "bench-granite41-30b"
EXPERT_MODEL = "bench-granite41-8b"


def _code_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
    ).strip()


def _load_detections() -> dict:
    import portal.modules.security.core.siem.spl_detections as detections_module

    path = Path(detections_module.__file__).with_name("spl_detections.yaml")
    return yaml.safe_load(path.read_text())


def _corpus_episode(technique_id: str, sourcetype: str) -> Episode | None:
    detections = _load_detections()
    raw_spl = detections[technique_id]["spl"].split("|")[0].strip()
    search = f"search {raw_spl} evidence_origin=corpus:* | head 8"
    rows = SplunkBackend()._run_search(search, "0", "now")
    lines = [row["fields"].get("_raw", "") for row in rows if row["fields"].get("_raw")]
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


def _promotion_recall(verdict: str | None, technique_ids: list[str], expected: str) -> float:
    scoreable = set(technique_ids) if verdict == "CONFIRMED" else set()
    return score_findings_tiered(scoreable, {expected})["overall"]["recall"]


def _checkpoint(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Exact-code V2 corpus baseline")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--techniques", help="optional comma-separated subset")
    args = parser.parse_args()

    commit = _code_commit()
    if commit != args.expected_commit:
        raise SystemExit(f"wrong code checkout: expected {args.expected_commit}, running {commit}")

    results = json.loads(args.out.read_text()) if args.out.exists() else []
    done = {
        row["technique_expected"]
        for row in results
        if row.get("status") == "done" and row.get("code_commit") == commit
    }
    techniques = (
        [item.strip() for item in args.techniques.split(",") if item.strip()]
        if args.techniques
        else list(CURATED_TECHNIQUES)
    )

    for index, technique_id in enumerate(techniques, 1):
        if technique_id in done:
            print(f"[{index}/{len(techniques)}] SKIP {technique_id}")
            continue
        print(f"[{index}/{len(techniques)}] RUN {technique_id}", flush=True)
        episode = _corpus_episode(technique_id, CURATED_TECHNIQUES[technique_id])
        if episode is None:
            record = {
                "technique_expected": technique_id,
                "status": "skipped_no_corpus_data",
                "code_commit": commit,
            }
        else:
            started = time.monotonic()
            result = run_blue_orchestration(
                episode,
                sections=[
                    SectionSpec(role="tool", model=TOOL_MODEL, needs_tools=True),
                    SectionSpec(role="reasoning", model=REASONING_MODEL),
                    SectionSpec(role="expert", model=EXPERT_MODEL),
                ],
                max_rounds=6,
            )
            record = {
                "label": re.sub(r"[^A-Za-z0-9]+", "_", technique_id).strip("_").lower(),
                "technique_expected": technique_id,
                "mode": "orchestrated",
                "model_arm": "v2_exact_pre_v3",
                "status": "done",
                "code_commit": commit,
                "verdict": result.verdict,
                "technique_ids": result.technique_ids,
                "scoring_recall": _promotion_recall(
                    result.verdict, result.technique_ids, technique_id
                ),
                "rounds": result.rounds,
                "elapsed_s": round(time.monotonic() - started, 1),
                "trace": result.trace,
            }
        results = [row for row in results if row.get("technique_expected") != technique_id]
        results.append(record)
        _checkpoint(results, args.out)
        print(
            f"  -> {record.get('verdict', record['status'])} "
            f"{record.get('technique_ids', [])} recall={record.get('scoring_recall', 0)}",
            flush=True,
        )

    completed = [row for row in results if row.get("status") == "done"]
    recall = sum(float(row.get("scoring_recall") or 0) for row in completed)
    print(f"Done: {recall:g}/{len(completed)} confirm-only recall; {args.out}")


if __name__ == "__main__":
    main()
