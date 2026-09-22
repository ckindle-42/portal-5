#!/usr/bin/env python3
"""CLOSEOUT_V1 P8 / TASK_COMPLIANCE_PROVE_THE_MODULE_V1 §P5 - the three
product questions, asked on the deployed surface, across the family.

This is the module's reason for existing, asked out loud:

  1. Where are we not covered?
  2. Where do we exceed what the standard requires?
  3. Where does the standard grant latitude we are not using?

Question 1 has a stored relation behind it (absence of IMPLEMENTS) and can be
cross-checked against compliance_coverage. Questions 2 and 3 have no stored
relation - DETERMINATION_RELATIONS is (IMPLEMENTS, EVIDENCES, REFERENCES) - so
they are answered by reading the material in conversation. That asymmetry is
recorded on every row rather than smoothed over.

§P5: every question is asked in its NATURAL wording — the one that used to
trigger the router's nerc_cip_requirement narrowing
(_select_explicit_required_tool, fixed in §P4.1). Three prior measurements
passed by rewording around the bug (the "commit me to more than the standard
asks" dodge, preserved at closeout/p8/product_questions_run1_blocked_by_router.json
as the wording that died). This script no longer carries a reworded fallback —
the natural wording IS the question.

Reuses WorkspaceThread from scripts/compliance_acceptance.py: one deployed
conversation per question, through the router the config actually declares.

Exit codes:
    0 - all three questions answered with resolving citations, on every standard
    1 - at least one question failed (the close is refused)
    3 - could not reach the deployed surface at all
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402
from compliance_acceptance import WorkspaceThread, router_base_url  # noqa: E402

from portal.modules.compliance.core.answer_contract import (  # noqa: E402
    AnswerContract,
    build_contract,
)
from portal.modules.compliance.core.repository import Repository  # noqa: E402

# One anchor requirement per standard — chosen to span the family: the
# proven case, two healthy/high-corroboration standards, and the two dead
# standards §P2 diagnosed (CIP-003-8: 35 refusals; CIP-002-5.1a: zero
# determinations, the store's only genuine no_operator_document case besides
# CIP-014-3).
DEFAULT_ANCHORS = {
    "CIP-007-6": "CIP-007-6 R2",
    "CIP-004-7": "CIP-004-7 R4",
    "CIP-010-4": "CIP-010-4 R1",
    "CIP-003-8": "CIP-003-8 R1",
    "CIP-002-5.1a": "CIP-002-5.1a R1",
}


def _question_specs(ref: str) -> list[dict]:
    return [
        {
            "key": "coverage_gap",
            "question": (
                f"For {ref}, which Parts do my documents not cover? For each "
                "Part with no implementing section of mine, say so plainly "
                "and cite the Part. For each Part that is covered, cite the "
                "section of mine that covers it."
            ),
            "requires_side": "operator",
            "has_stored_relation": True,
            "cross_check": "compliance_coverage",
        },
        {
            "key": "exceedance",
            "question": (
                f"For {ref}, where do my documents commit me to more than "
                "the standard requires? Quote the standard's requirement "
                "and my document's stronger commitment side by side, and "
                "cite both."
            ),
            "requires_side": "operator",
            "has_stored_relation": False,
            "cross_check": None,
        },
        {
            "key": "unused_latitude",
            "question": (
                f"For {ref}, where does the standard leave a choice or an "
                "allowance that my documents do not take up? Cite the "
                "standard's own words granting the latitude, and say what "
                "my documents do instead."
            ),
            "requires_side": "regulatory",
            "has_stored_relation": False,
            "cross_check": None,
        },
    ]


def _requirement_contract(repo, requirement: str) -> AnswerContract:
    """The union contract over every Part of one requirement — this script
    asks about the requirement as a whole (e.g. CIP-007-6 R2), not one Part,
    so no single ``reading_material.render`` call covers the citations an
    answer may use. Built the same way ``render`` builds its own: from the
    population's own rows, never from a regex over the id."""
    from portal.modules.compliance.core import reading_material
    from portal.modules.compliance.core.cip_register import node_index
    from portal.modules.compliance.core.reading_assembly import parse_ref

    parsed = parse_ref(requirement)
    standard = parsed.standard if parsed else requirement
    parts = sorted(
        k for k in node_index() if k == requirement or k.startswith(f"{requirement} Part ")
    )
    if not parts:
        parts = [requirement]

    fixed = reading_material.fixed_body(repo, standard)
    sections: list[dict] = []
    addresses: dict[str, str] = {requirement: requirement}
    for part_ref in parts:
        material = reading_material.render(
            repo, part_ref, fixed=fixed if "error" not in fixed else None
        )
        if "error" in material:
            continue
        part_contract: AnswerContract = material["contract"]
        for section_id, token in part_contract.by_section_id.items():
            sections.append(
                {"section_id": section_id, "side": token.kind, "document_title": token.document}
            )
        addresses.update(part_contract.addresses)
    return build_contract(requirement, requirement, sections, addresses=addresses)


def _ask_one(
    session: httpx.Client,
    router: str,
    workspace: str,
    repo,
    standard: str,
    ref: str,
    timeout: float,
    out_dir: pathlib.Path,
) -> list[dict]:
    contract = _requirement_contract(repo, ref)
    rows: list[dict] = []
    for spec in _question_specs(ref):
        thread = WorkspaceThread(session, workspace, router)
        try:
            record = thread.turn(spec["question"], timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - a dead turn is a recorded failure
            rows.append(
                {
                    "standard": standard,
                    "requirement": ref,
                    **{k: spec[k] for k in ("key", "requires_side", "has_stored_relation")},
                    "question": spec["question"],
                    "verdict": "FAIL",
                    "reason": f"turn raised {type(exc).__name__}: {exc}",
                }
            )
            continue

        answer = str(record.get("answer") or "")
        (out_dir / "transcripts" / f"{standard}__{spec['key']}.json").write_text(
            json.dumps(record, indent=2, default=str)
        )

        cited = contract.cited(answer)
        ids = cited["resolved"] + cited["unresolved"]
        sides = set(cited["by_side"])
        # LOAD_AND_CONVERSE_V1 §P5: grounding is per CLAIM, not per token — an
        # answer whose every claim carries a resolving citation passes; a claim
        # standing only on a citation that resolves to nothing fails. The
        # mistyped-restatement case (CIP-007-6 unused_latitude) no longer voids
        # a grounded answer, and the strict half is unchanged: an unresolved id
        # with no resolving counterpart anywhere still fails, and no unresolved
        # id is ever mapped to a near neighbour to make it resolve.
        claims = contract.cited_claims(answer)

        checks = {
            "answered": bool(answer.strip())
            and not record.get("turn_budget_exceeded")
            and record.get("http_status") in (200, None),
            "cited_something": bool(ids),
            "grounding_per_claim": claims["grounded"],
            "required_side_present": spec["requires_side"] in sides,
        }
        verdict = "PASS" if all(checks.values()) else "FAIL"
        failed = [k for k, v in checks.items() if not v]

        rows.append(
            {
                "standard": standard,
                "requirement": ref,
                **{
                    k: spec[k]
                    for k in ("key", "requires_side", "has_stored_relation", "cross_check")
                },
                "question": spec["question"],
                "answer": answer,
                "answer_chars": len(answer),
                "wall_s": record.get("wall_s"),
                "first_token_s": record.get("first_token_s"),
                "cited_ids": ids,
                "resolved_ids": cited["resolved"],
                "unresolved_ids": cited["unresolved"],
                "grounding": {
                    "n_claims": claims["n_claims"],
                    "n_ungrounded": claims["n_ungrounded"],
                    "unsupported_lines": claims["unsupported_lines"],
                },
                "pipeline_errors": record.get("pipeline_errors") or {},
                "sides_cited": sorted(sides),
                "checks": checks,
                "verdict": verdict,
                "reason": "all checks passed"
                if verdict == "PASS"
                else f"failed: {', '.join(failed)}",
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="compliance-reading")
    ap.add_argument("--standards", default="CIP-007-6", help="comma-separated standard ids")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    (args.out_dir / "transcripts").mkdir(parents=True, exist_ok=True)

    try:
        router = router_base_url()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot resolve the router base url: {exc}", file=sys.stderr)
        return 3

    standards = [s.strip() for s in args.standards.split(",") if s.strip()]
    unknown = [s for s in standards if s not in DEFAULT_ANCHORS]
    if unknown:
        print(f"FAIL: no anchor requirement configured for {unknown}", file=sys.stderr)
        return 3

    repo = Repository()
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10.0)) as session:
            for standard in standards:
                ref = DEFAULT_ANCHORS[standard]
                rows.extend(
                    _ask_one(
                        session,
                        router,
                        args.workspace,
                        repo,
                        standard,
                        ref,
                        args.timeout,
                        args.out_dir,
                    )
                )
    finally:
        repo.close()

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "workspace": args.workspace,
        "router": router,
        "standards": standards,
        "anchors": {s: DEFAULT_ANCHORS[s] for s in standards},
        "n_questions": len(rows),
        "n_passed": passed,
        "rows": rows,
        "relation_asymmetry_note": (
            "coverage_gap has a stored relation behind it (absence of IMPLEMENTS) "
            "and is cross-checkable against compliance_coverage. exceedance and "
            "unused_latitude have no stored relation: DETERMINATION_RELATIONS is "
            "(IMPLEMENTS, EVIDENCES, REFERENCES). Those two answers are readings, "
            "with a reading's reliability, and the closing report says so."
        ),
        "wording_note": (
            "Every question above uses the natural wording that used to trigger "
            "_select_explicit_required_tool's nerc_cip_requirement narrowing "
            "(fixed in TASK_COMPLIANCE_PROVE_THE_MODULE_V1 §P4.1). Run 1 died "
            "at hop 1 on exactly these strings for CIP-007-6 R2; preserved at "
            "reports/compliance/closeout/p8/product_questions_run1_blocked_by_router.json."
        ),
        "verdict": "PASS" if passed == len(rows) else "FAIL",
    }
    out = args.out_dir / "product_questions_family.json"
    out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {out}")
    print(f"{passed}/{len(rows)} passed")
    for r in rows:
        print(f"  [{r['verdict']}] {r['standard']:14s} {r['key']:16s} {r['reason']}")
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
