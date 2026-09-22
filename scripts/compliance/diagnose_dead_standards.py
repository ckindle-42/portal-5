#!/usr/bin/env python3
"""TASK_COMPLIANCE_PROVE_THE_MODULE_V1 P2 - diagnose the dead standards.

Classifies every Part-level requirement in the named standards into one of
four causes, from data already in the store — never a new threshold, never a
guess:

  no_operator_document  no candidate section was ever proposed for this
                         requirement's parent identity (links payload has no
                         proposed edges and no rejected-candidate record for
                         it), and the requirement's population (regulatory +
                         operator + notes) has zero operator-side entries.
  below_threshold        candidates were retrieved and scored but none
                         cleared DEFAULT_THRESHOLD (links payload's
                         ``requirements_with_no_candidate`` names a best_score
                         for the parent).
  empty_population        requirement_scope.population(...) returns zero
                         operator-side entries for this requirement even
                         though a projection proposed edges for its parent —
                         the parent's candidates never reached this specific
                         Part.
  reading_failure          the population is non-empty (material was in front
                         of the model) and this requirement is not
                         determined/corroborated in relationship_assertions —
                         the read produced nothing admissible. Reasons are
                         pulled from the existing refusal adjudication
                         (reports/compliance/.../refusal_adjudication*.json)
                         when the requirement's parent appears there.

Then, for every requirement in cause 1 or 2, the agent reads the operator
corpus directly (a step this script cannot do — it emits the requirement
list and its own best-effort section search so the agent's read has a
starting point) and records any recall miss the reranker never proposed.
This script does NOT change DEFAULT_THRESHOLD or admit anything.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import requirement_scope  # noqa: E402
from portal.modules.compliance.core.cip_register import Register  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402


def _latest_autosync() -> pathlib.Path | None:
    d = REPO_ROOT / "reports/compliance/autosync"
    files = sorted(d.glob("*.json"))
    return files[-1] if files else None


def _latest_refusal_adjudication() -> pathlib.Path | None:
    candidates = sorted(
        REPO_ROOT.glob("reports/compliance/**/refusal_adjudication*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _classify_ref(
    repo: Any, ref: str, link_entry: dict[str, Any], refusal_by_ref: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    parent = ref.split(" Part ")[0]
    no_candidate_entry = next(
        (
            e
            for e in link_entry.get("requirements_with_no_candidate", []) or []
            if e.get("ref") in (ref, parent)
        ),
        None,
    )

    pop = requirement_scope.population(repo, ref, include_notes=True)
    n_operator = len(pop.get("operator") or [])
    n_regulatory = len(pop.get("regulatory") or [])

    # Already answered — not dead for this requirement specifically.
    determined = repo._conn.execute(
        """SELECT COUNT(*) FROM relationship_assertions
           WHERE src_ref = ? AND valid_to IS NULL
             AND (status = 'machine_determined' OR derivation LIKE '%reading%')""",
        (ref,),
    ).fetchone()[0]

    refusals = refusal_by_ref.get(ref, []) or refusal_by_ref.get(parent, [])

    if determined:
        cause = "answered"
    elif no_candidate_entry is not None:
        cause = "below_threshold"
    elif n_operator == 0 and link_entry.get("edges_recorded", 0) == 0:
        cause = "no_operator_document"
    elif n_operator == 0:
        cause = "empty_population"
    else:
        cause = "reading_failure"

    return {
        "ref": ref,
        "cause": cause,
        "n_operator_population": n_operator,
        "n_regulatory_population": n_regulatory,
        "no_candidate_best_score": (no_candidate_entry or {}).get("best_score"),
        "refusal_categories": sorted({r["category"] for r in refusals}),
        "n_refusals": len(refusals),
    }


def _diagnose_standard(
    repo: Any,
    standard: str,
    reqs: list[str],
    link_entry: dict[str, Any],
    refusal_by_ref: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    causes = {
        "no_operator_document": 0,
        "below_threshold": 0,
        "empty_population": 0,
        "reading_failure": 0,
    }
    per_req = [_classify_ref(repo, ref, link_entry, refusal_by_ref) for ref in reqs]
    for r in per_req:
        if r["cause"] in causes:
            causes[r["cause"]] += 1
    recall_misses = [
        {
            "standard": standard,
            "ref": r["ref"],
            "cause": r["cause"],
            "reranker_best_score": r["no_candidate_best_score"],
            "note": "candidate for agent recall-miss read (§P2 body)",
        }
        for r in per_req
        if r["cause"] in ("no_operator_document", "below_threshold")
    ]
    standard_result = {
        "standard": standard,
        "n_requirements": len(reqs),
        "causes": causes,
        "n_answered_in_window": sum(1 for r in per_req if r["cause"] == "answered"),
        "requirements": per_req,
    }
    return standard_result, recall_misses


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--standards", required=True, help="comma-separated standard ids")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument(
        "--links-report",
        type=pathlib.Path,
        default=None,
        help="a JSON with a ``links`` payload (family_links.py output). Default: the "
        "latest autosync report, which only carries the standards a lifecycle "
        "change touched — a family-wide diagnosis wants the family-wide report",
    )
    args = ap.parse_args()

    standards = [s.strip() for s in args.standards.split(",") if s.strip()]

    links_path = args.links_report or _latest_autosync()
    source_doc = json.loads(links_path.read_text()) if links_path else {}
    links = source_doc.get("links", source_doc.get("standards_links", {}))

    refusal_path = _latest_refusal_adjudication()
    refusal_data = json.loads(refusal_path.read_text()) if refusal_path else {"categories": {}}
    refusal_by_ref: dict[str, list[dict[str, Any]]] = {}
    for cat, rows in refusal_data.get("categories", {}).items():
        for r in rows:
            ref = str(r.get("requirement") or "")
            refusal_by_ref.setdefault(ref, []).append({"category": cat, **r})

    reg = Register.load()

    repo = Repository()
    try:
        results: list[dict[str, Any]] = []
        recall_misses: list[dict[str, Any]] = []
        for standard in standards:
            reqs = sorted({n.id for n in reg.nodes if n.standard == standard})
            link_entry = links.get(standard) or {}
            standard_result, misses = _diagnose_standard(
                repo, standard, reqs, link_entry, refusal_by_ref
            )
            results.append(standard_result)
            recall_misses.extend(misses)
    finally:
        repo.close()

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "links_source": str(links_path) if links_path else None,
        "refusal_adjudication_source": str(refusal_path) if refusal_path else None,
        "standards": results,
        "n_recall_misses": len(recall_misses),
        "recall_misses": recall_misses,
        "method": (
            "Classification is mechanical from data already in the store: "
            "links.<parent>.requirements_with_no_candidate (below_threshold), "
            "requirement_scope.population operator-side count (empty_population "
            "when zero and a projection exists; no_operator_document when zero "
            "and no projection was ever recorded for the parent), and presence "
            "in relationship_assertions (reading_failure = population non-empty "
            "but nothing admitted). recall_misses lists the requirements the "
            "agent should read the corpus for directly per §P2's body; this "
            "script does not perform that read itself."
        ),
        "verdict": "RECORDED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {args.out}")
    for s in results:
        c = s["causes"]
        print(
            f"{s['standard']:16s} reqs={s['n_requirements']:3d} "
            f"no_operator_document={c['no_operator_document']:3d} "
            f"below_threshold={c['below_threshold']:3d} "
            f"empty_population={c['empty_population']:3d} "
            f"reading_failure={c['reading_failure']:3d} "
            f"answered={s['n_answered_in_window']:3d}"
        )
    print(f"\nrecall-miss candidates for agent reading: {len(recall_misses)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
