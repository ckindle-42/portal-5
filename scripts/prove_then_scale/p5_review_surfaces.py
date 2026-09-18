"""PROVE_THEN_SCALE_V1 §P5 — generate the operator's review surfaces.

Not 1,427 rows. Three artifacts:

1. the CONTRADICTION QUEUE — every cross-reading disagreement the store holds,
   found by machine (:func:`contradictions.scan_contradictions`);
2. a DRILL-DOWN example — one sweep answer opened to verbatim text on both
   sides (:func:`contradictions.drill_down`), the shape every answer review
   takes;
3. the STRATIFIED SAMPLE PACKET (P5.3) — the deterministic, stratified
   selection of determined pairs the operator confirms or corrects, one row
   per pair with both sides' text inline. This packet is what makes §P6
   possible: until a human decides its rows, the scorer reports honest-BLOCKED,
   which is the honest state.

Usage: uv run python scripts/prove_then_scale/p5_review_surfaces.py [--sample-n 40]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import (  # noqa: E402
    contradictions,
    evaluation,
)
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.section_index import resolve_sections  # noqa: E402

ART_DIR = REPO_ROOT / "reports" / "compliance" / "prove_then_scale"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-n", type=int, default=40)
    parser.add_argument(
        "--drill-answer",
        default="",
        help="answer_id to drill into (default: newest sweep map answer)",
    )
    args = parser.parse_args()

    repo = Repository()
    try:
        # 1. the contradiction queue
        report = contradictions.scan_contradictions(repo)
        (ART_DIR / "p5_contradictions.json").write_text(json.dumps(report, indent=2, default=str))
        print(
            f"contradictions: {len(report['relation_conflicts'])} relation conflicts, "
            f"{len(report['rejected_contradictions'])} rejected-contradictions, "
            f"{len(report['approved_disagreements'])} approved disagreements "
            f"(n_items={report['n_items']})"
        )

        # 2. drill-down on the newest map answer
        drill = None
        if args.drill_answer:
            drill = contradictions.drill_down(repo, args.drill_answer)
        else:
            row = repo._conn.execute(
                """SELECT run_id FROM reading_runs
                   WHERE question LIKE '[mapping]%' AND answer <> ''
                   ORDER BY asked_at DESC LIMIT 1"""
            ).fetchone()
            if row:
                drill = contradictions.drill_down(repo, run_id=str(row[0]))
        if drill and "error" not in drill:
            (ART_DIR / "p5_drilldown_example.json").write_text(
                json.dumps(drill, indent=2, default=str)
            )
            print(
                f"drill-down: run {drill.get('run_id', '')[:14]} — "
                f"{len(drill.get('citations', []))} citations opened"
            )
        else:
            print(f"drill-down: skipped ({(drill or {}).get('error', 'nothing to open')})")

        # 3. the stratified sample packet
        selection = evaluation.select_sample(repo, n=args.sample_n)
        rows = evaluation.sample_rows(repo)
        resolved = resolve_sections(repo, [r["section_id"] for r in rows])
        packet = []
        for row in rows:
            entry = resolved.get(row["section_id"], {})
            packet.append(
                {
                    "sample_id": row["sample_id"],
                    "requirement_id": row["requirement_id"],
                    "section_id": row["section_id"],
                    "machine_relation": row["machine_relation"],
                    "confidence": row["confidence"],
                    "stratum": f"{row['stratum_standard']}|{row['stratum_relation']}",
                    "decision": row["decision"],
                    "document": str(entry.get("document_title") or ""),
                    "heading": str(entry.get("headings") or ""),
                    "section_text": str(entry.get("text", "")).strip()[:1200],
                    "decide_hint": "CONFIRMED | CORRECTED (with relation) | REJECTED",
                }
            )
        (ART_DIR / "p5_sample_packet.json").write_text(
            json.dumps(
                {
                    "selection": {k: v for k, v in selection.items() if k != "sample_ids"},
                    "n_rows": len(packet),
                    "rows": packet,
                    "how_to_record": (
                        "record_sample_decision(repo, sample_id, decision, "
                        "human_relation=..., decided_by=..., notes=...) — or the review "
                        "surface when one exists; undecided rows keep the scorer at "
                        "honest-BLOCKED, which is the honest state"
                    ),
                },
                indent=2,
                default=str,
            )
        )
        bands = {}
        for row in rows:
            bands[row["confidence_band"]] = bands.get(row["confidence_band"], 0) + 1
        print(
            f"sample packet: {len(packet)} rows | bands {bands} | "
            f"{selection['n_determined_rows']} determined rows in store"
        )

        # 4. the agreement report — honest state until a human decides rows
        ag = evaluation.agreement(repo)
        (ART_DIR / "p6_agreement.json").write_text(json.dumps(ag, indent=2, default=str))
        print(f"agreement: {ag['verdict']} — {ag.get('reason', ag.get('agreement_rate'))}")
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
