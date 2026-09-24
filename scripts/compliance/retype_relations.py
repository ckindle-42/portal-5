#!/usr/bin/env python3
"""MODULE_COMPLETE_V1 §P1 — act on adjudicated wrong relations; supersede, never delete.

A WRONG_RELATION verdict is a known-correct relation sitting on a known-wrong
edge. The store only accumulates, so nothing here deletes: the wrong edge is
REVOKED (review_state REVOKED, the deciding reason recorded on the row) and the
corrected edge is written as its own determination carrying the SAME citation —
the quote's provenance was verified when it was first stored and the re-type
changes the relation, not the reading it rests on. The revoked original and the
corrected edge both remain.

    uv run python scripts/compliance/retype_relations.py \\
        --receipt reports/compliance/module_complete/p1/entailment_gap.json \\
        --out reports/compliance/module_complete/p1/retyped.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.candidate_links import record_determination  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

RUN_ID = "module_complete_p1_retype"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipt", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    receipt = json.loads(args.receipt.read_text())
    entries = receipt["retype"]
    repo = Repository()
    results: list[dict[str, object]] = []
    try:
        from portal.modules.compliance.core.temporal import now_iso

        for entry in entries:
            assertion_id = entry["assertion_id"]
            correct = entry["correct"]
            reason = entry["reason"]
            row = repo._conn.execute(
                """SELECT relation_type, src_ref, dst_ref, status, review_state, citations_json
                     FROM relationship_assertions WHERE assertion_id = ?""",
                (assertion_id,),
            ).fetchone()
            if row is None:
                results.append({"assertion_id": assertion_id, "action": "missing"})
                continue
            if correct in (None, ""):
                results.append(
                    {
                        "assertion_id": assertion_id,
                        "action": "skipped",
                        "why": "no correct relation named",
                    }
                )
                continue
            if row["relation_type"] == correct:
                results.append(
                    {"assertion_id": assertion_id, "action": "skipped", "why": f"already {correct}"}
                )
                continue
            citations = json.loads(row["citations_json"] or "[]")
            first = citations[0] if citations else {}
            sentence = str(first.get("sentence") or "")
            answer_id = str(first.get("answer_id") or RUN_ID)
            section_id = str(row["dst_ref"])
            requirement_id = str(row["src_ref"])
            record = {
                "assertion_id": assertion_id,
                "requirement_id": requirement_id,
                "section_id": section_id,
                "was": row["relation_type"],
                "correct": correct,
                "revoked": False,
                "written": None,
            }
            if args.dry_run:
                results.append(record | {"action": "dry_run"})
                continue
            with repo._lock, repo._conn:
                repo._conn.execute(
                    """UPDATE relationship_assertions
                          SET review_state = 'REVOKED', status = 'revoked',
                              decided_by = ?, decided_at = ?, rationale = ?, version = version + 1
                        WHERE assertion_id = ?""",
                    (
                        "module_complete_p1 adjudication",
                        now_iso(),
                        f"REVOKED on adjudication: the reading determined {row['relation_type']} but the "
                        f"adjudication re-read found {correct}. Reason: {reason} Superseded by a "
                        f"corrected {correct} edge carrying the same citation; this row is retained, "
                        "never deleted.",
                        assertion_id,
                    ),
                )
            record["revoked"] = True
            written = record_determination(
                repo,
                requirement_id=requirement_id,
                section_id=section_id,
                relation_type=correct,
                answer_id=answer_id,
                sentence=sentence,
                confidence=1.0,
                read_ref=requirement_id,
                run_id=RUN_ID,
            )
            record["written"] = written
            results.append(record)
    finally:
        repo.close()

    done = [r for r in results if r.get("revoked")]
    out = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "receipt": str(args.receipt),
        "n_entries": len(entries),
        "n_retyped": len(done),
        "rows": results,
        "verdict": "RETYPED" if done else "NOTHING_TO_DO",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(f"retyped {len(done)} of {len(entries)}; WROTE {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
