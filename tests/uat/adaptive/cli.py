"""Adaptive UAT — offline agent/operator CLI (TASK_UAT_ADAPTIVE_OVERHAUL_V1).

Execution runs through the main driver's OWUI path (`portal5_uat_driver.py
--adaptive`). This CLI covers the offline steps around it — authoring (agent),
assessment (agent), and the operator review packet — none of which need a
browser.

Authoring (agent, independent of the system under test):
  --emit-worksheets [--space ID ...]   write per-space authoring worksheets
  --ingest-worksheets                  validate filled worksheets + freeze suites

Assessment (agent, first pass):
  --assess-pending [--corpus C]        dump challenges awaiting agent assessment (JSON)
  --assess-apply FILE [--corpus C]     record a batch of agent assessments

Operator review:
  --packet [CORPUS]                    build the HTML review packet + rollup
  --ingest VERDICTS_JSON [--corpus C]  merge operator verdicts + re-roll

With no corpus given, corpus-based actions default to the newest uat_*.jsonl.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tests.uat.adaptive import assess
from tests.uat.adaptive.generate import (
    emit_all_worksheets,
    ingest_all_worksheets,
)
from tests.uat.adaptive.review import (
    ingest_verdicts,
    rollup_markdown,
    write_review_packet,
)

_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = _ROOT / "tests" / "uat_corpus"


def _latest_corpus() -> Path | None:
    if not CORPUS_DIR.exists():
        return None
    files = sorted(CORPUS_DIR.glob("uat_*.jsonl"))
    return files[-1] if files else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Portal 5 Adaptive UAT — offline tooling")
    p.add_argument(
        "--emit-worksheets",
        action="store_true",
        help="Write per-space authoring worksheets for the agent to fill.",
    )
    p.add_argument(
        "--space",
        action="append",
        metavar="ID",
        help="Restrict --emit-worksheets to space id(s) (repeatable).",
    )
    p.add_argument(
        "--ingest-worksheets",
        action="store_true",
        help="Validate filled worksheets and freeze the suites.",
    )
    p.add_argument(
        "--assess-pending",
        action="store_true",
        help="Dump adaptive challenges awaiting agent assessment (JSON).",
    )
    p.add_argument(
        "--assess-apply",
        metavar="AGENT_JSON",
        help="Record a batch of agent assessments into the corpus.",
    )
    p.add_argument(
        "--packet",
        nargs="?",
        const="",
        metavar="CORPUS_JSONL",
        help="Build the review packet + rollup (default: newest corpus).",
    )
    p.add_argument(
        "--ingest",
        metavar="VERDICTS_JSON",
        help="Merge exported operator verdicts into the corpus and re-roll.",
    )
    p.add_argument(
        "--corpus",
        metavar="JSONL",
        help="Explicit corpus path for corpus-based actions (default: newest).",
    )
    return p


def _resolve(explicit: str | None) -> Path:
    corpus = Path(explicit) if explicit else _latest_corpus()
    if not corpus or not corpus.exists():
        raise SystemExit("adaptive: no corpus found (run `portal5_uat_driver.py --adaptive` first)")
    return corpus


def main() -> None:
    args = build_parser().parse_args()

    # ── authoring (agent) ───────────────────────────────────────────────────
    if args.emit_worksheets:
        paths = emit_all_worksheets(space_filter=tuple(args.space or ()))
        print(f"Wrote {len(paths)} authoring worksheet(s) to tests/uat_adaptive/worksheets/")
        print('Fill each entry\'s "prompt" (and "followup" for continuity), reviewing the')
        print("authoring_brief + design docs, then: --ingest-worksheets")
        return
    if args.ingest_worksheets:
        out = ingest_all_worksheets()
        total = sum(out.values())
        print(f"Froze {total} agent-authored challenge(s) across {len(out)} space(s).")
        return

    # ── assessment (agent) ──────────────────────────────────────────────────
    if args.assess_pending:
        corpus = _resolve(args.corpus)
        items = assess.pending(corpus)
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return
    if args.assess_apply:
        corpus = _resolve(args.corpus)
        batch = json.loads(Path(args.assess_apply).read_text())
        for a in batch:
            assess.record(
                a["test_id"],
                a.get("scores", {}),
                a.get("verdict", ""),
                a.get("rationale", ""),
                corpus=corpus,
            )
        print(f"Recorded {len(batch)} agent assessment(s) into {corpus.name}.")
        return

    # ── operator review ─────────────────────────────────────────────────────
    if args.ingest:
        corpus = _resolve(args.corpus)
        ingest_verdicts(corpus, Path(args.ingest))
        md = rollup_markdown(corpus)
        print(f"Verdicts merged into {corpus.name}; rolled up -> {md}")
        return

    corpus = _resolve(args.packet if args.packet else None)
    packet = write_review_packet(corpus)
    md = rollup_markdown(corpus)
    print("Adaptive review packet built.")
    print(f"  Corpus:  {corpus}")
    print(f"  Packet:  {packet}   <- open in a browser, confirm/override, Export verdicts JSON")
    print(f"  Rollup:  {md}")
    print("  Then:    python3 tests/portal5_uat_adaptive.py --ingest verdicts_<run>.json")
