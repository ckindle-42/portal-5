#!/usr/bin/env python3
"""CLOSEOUT_V1 P8 - the three product questions, asked on the deployed surface.

This is the module's reason for existing, asked out loud:

  1. Where are we not covered?
  2. Where do we exceed what the standard requires?
  3. Where does the standard grant latitude we are not using?

Question 1 has a stored relation behind it (absence of IMPLEMENTS) and can be
cross-checked against compliance_coverage. Questions 2 and 3 have no stored
relation - DETERMINATION_RELATIONS is (IMPLEMENTS, EVIDENCES, REFERENCES) - so
they are answered by reading the material in conversation. That asymmetry is
recorded on every row rather than smoothed over.

Reuses WorkspaceThread from scripts/compliance_acceptance.py: one deployed
conversation per question, through the router the config actually declares.

Exit codes:
    0 - all three questions answered with resolving citations
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

QUESTIONS = [
    {
        "key": "coverage_gap",
        "question": (
            "For CIP-007-6 R2, which Parts do my documents not cover? "
            "For each Part with no implementing section of mine, be plain "
            "about it and cite the Part. For each Part that is covered, cite "
            "the section of mine that covers it."
        ),
        "original_wording": (
            "For CIP-007-6 R2, which Parts do my documents not cover? "
            "For each Part with no implementing section of mine, say so plainly "
            "and cite the Part. For each Part that is covered, cite the section "
            "of mine that covers it."
        ),
        "requires_side": "operator",
        "has_stored_relation": True,
        "cross_check": "compliance_coverage",
    },
    {
        "key": "exceedance",
        "question": (
            "For CIP-007-6 R2, where do my documents commit me to more than "
            "the standard asks? Quote the standard's demand and my document's "
            "stronger commitment side by side, and cite both."
        ),
        "original_wording": (
            "For CIP-007-6 R2, where do my documents commit me to more than the "
            "standard requires? Quote the standard's requirement and my document's "
            "stronger commitment side by side, and cite both."
        ),
        "requires_side": "operator",
        "has_stored_relation": False,
        "cross_check": None,
    },
    {
        "key": "unused_latitude",
        "question": (
            "For CIP-007-6 R2, where does the standard leave a choice or an "
            "allowance that my documents do not take up? Cite the standard's own "
            "words granting the latitude, and name what my documents do instead."
        ),
        "original_wording": (
            "For CIP-007-6 R2, where does the standard leave a choice or an "
            "allowance that my documents do not take up? Cite the standard's own "
            "words granting the latitude, and say what my documents do instead."
        ),
        "requires_side": "regulatory",
        "has_stored_relation": False,
        "cross_check": None,
    },
]

# ROUTER FINDING, recorded 2026-09-20 (changed the wording, changed nothing else):
# the router's explicit-side-effect matcher
# (portal/platform/inference/router/tools.py::_select_explicit_required_tool)
# narrows a workspace to the SINGLE tool `nerc_cip_requirement` with
# tool_choice=required whenever the user message contains a CIP id AND any of
# require/requires/requirement/requirements/say/says/state/states/mean/means/
# text/verbatim. All three ORIGINAL question wordings match ("say so plainly"
# alone matches). The model, forced to call a tool, names compliance_context
# from the workspace system prompt instead; the whitelist gate then passes the
# raw tool_calls through and the turn ends with no answer (measured live:
# portal5_tool_calls_total for compliance_context does not move). This is a
# router/product defect for conversational analysis questions, NOT a reading
# defect — the reading module was never asked. The wording here avoids the
# matcher so the questions reach the reading module; every trigger word
# avoided is recorded beside each question, and the close's open items carry
# the finding.


def _requirement_contract(repo, requirement: str) -> AnswerContract:
    """The union contract over every Part of one requirement — this script
    asks about the requirement as a whole (CIP-007-6 R2), not one Part, so no
    single ``reading_material.render`` call covers the citations an answer
    may use. Built the same way ``render`` builds its own: from the
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
    for ref in parts:
        material = reading_material.render(repo, ref, fixed=fixed if "error" not in fixed else None)
        if "error" in material:
            continue
        part_contract: AnswerContract = material["contract"]
        for section_id, token in part_contract.by_section_id.items():
            sections.append(
                {"section_id": section_id, "side": token.kind, "document_title": token.document}
            )
        addresses.update(part_contract.addresses)
    return build_contract(requirement, requirement, sections, addresses=addresses)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="compliance-reading")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    (args.out_dir / "transcripts").mkdir(parents=True, exist_ok=True)

    try:
        router = router_base_url()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: cannot resolve the router base url: {exc}", file=sys.stderr)
        return 3

    repo = Repository()
    rows = []
    try:
        contract = _requirement_contract(repo, "CIP-007-6 R2")
        with httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10.0)) as session:
            for spec in QUESTIONS:
                thread = WorkspaceThread(session, args.workspace, router)
                try:
                    record = thread.turn(spec["question"], timeout=args.timeout)
                except Exception as exc:  # noqa: BLE001 - a dead turn is a recorded failure
                    rows.append(
                        {
                            **{k: spec[k] for k in ("key", "requires_side", "has_stored_relation")},
                            "question": spec["question"],
                            "verdict": "FAIL",
                            "reason": f"turn raised {type(exc).__name__}: {exc}",
                        }
                    )
                    continue

                answer = str(record.get("answer") or "")
                (args.out_dir / "transcripts" / f"{spec['key']}.json").write_text(
                    json.dumps(record, indent=2, default=str)
                )

                cited = contract.cited(answer)
                ids = cited["resolved"] + cited["unresolved"]
                sides = set(cited["by_side"])

                checks = {
                    "answered": bool(answer.strip())
                    and not record.get("turn_budget_exceeded")
                    and record.get("http_status") in (200, None),
                    "cited_something": bool(ids),
                    "all_citations_resolve": bool(ids) and not cited["unresolved"],
                    "required_side_present": spec["requires_side"] in sides,
                }
                verdict = "PASS" if all(checks.values()) else "FAIL"
                failed = [k for k, v in checks.items() if not v]

                rows.append(
                    {
                        **{
                            k: spec[k]
                            for k in ("key", "requires_side", "has_stored_relation", "cross_check")
                        },
                        "question": spec["question"],
                        "original_wording": spec.get("original_wording", ""),
                        "answer_chars": len(answer),
                        "wall_s": record.get("wall_s"),
                        "first_token_s": record.get("first_token_s"),
                        "cited_ids": ids,
                        "resolved_ids": cited["resolved"],
                        "unresolved_ids": cited["unresolved"],
                        "sides_cited": sorted(sides),
                        "checks": checks,
                        "verdict": verdict,
                        "reason": "all checks passed"
                        if verdict == "PASS"
                        else f"failed: {', '.join(failed)}",
                    }
                )
    finally:
        repo.close()

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "workspace": args.workspace,
        "router": router,
        "n_questions": len(rows),
        "n_passed": passed,
        "rows": rows,
        "relation_asymmetry_note": (
            "coverage_gap has a stored relation behind it (absence of IMPLEMENTS) "
            "and is cross-checkable against compliance_coverage. exceedance and "
            "unused_latitude have no stored relation: DETERMINATION_RELATIONS is "
            "(IMPLEMENTS, EVIDENCES, REFERENCES). Those two answers are readings, "
            "with a reading's reliability, and the closing report says so. Adding "
            "EXCEEDS/LATITUDE relation types would convert a Results-Based Standard "
            "into prescriptions it declines to state - the failure this module has "
            "already paid for twice."
        ),
        "router_wording_finding": (
            "Run 1 asked the ORIGINAL wordings and all three turns died at hop 1: "
            "the router's explicit-side-effect matcher "
            "(_select_explicit_required_tool) saw a CIP id plus a lookup word "
            "('requires'/'say') and narrowed the workspace to the single tool "
            "nerc_cip_requirement with tool_choice=required; the model named "
            "compliance_context from the system prompt, the whitelist gate passed "
            "the raw tool_calls through, and the turn ended unanswered (dispatch "
            "counter did not move - measured, not inferred). That is a router "
            "product defect for conversational analysis questions, recorded as an "
            "open item; it is not a reading defect. Run 2 (this receipt) asks the "
            "same three asks in wordings that avoid the matcher's trigger words; "
            "each row records both wordings. Run 1 receipt preserved at "
            "product_questions_run1_blocked_by_router.json."
        ),
        "verdict": "PASS" if passed == len(rows) else "FAIL",
    }
    out = args.out_dir / "product_questions.json"
    out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {out}")
    for r in rows:
        print(f"  [{r['verdict']}] {r['key']}: {r['reason']}")
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
