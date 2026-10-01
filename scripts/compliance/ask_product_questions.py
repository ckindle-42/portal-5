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

from portal.modules.compliance.core.repository import Repository  # noqa: E402
from scripts.compliance.truth import _local  # noqa: E402
from scripts.compliance.truth.provenance import (  # noqa: E402
    receipt_provenance,
    store_counts,
    store_guard,
)

# One anchor requirement per standard — chosen to span the family: the
# proven case, two healthy/high-corroboration standards, and the two dead
# standards §P2 diagnosed (CIP-003-8: 35 refusals; CIP-002-5.1a: zero
# determinations, the store's only genuine no_operator_document case besides
# CIP-014-3).
DEFAULT_ANCHORS = {
    "CIP-007-6": "CIP-007-6 R2",
    "CIP-004-7": "CIP-004-7 R4",
    "CIP-010-4": "CIP-010-4 R1",
    # CIP-003-9 governs from 2026-04-01 (READING_TRUTH_V1 P2.5); CIP-003-8 R1 answers
    # survive only as re-judged history, never as a measured question.
    "CIP-003-9": "CIP-003-9 R1",
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


def _checks(repo, spec: dict, record: dict) -> tuple[dict[str, bool], dict]:
    """Citation-integrity checks for one answer, all from the ONE diagnostic
    (``citation_integrity.integrity``): a quote of a section's own words or a
    resolving id is a citation; a requirement address is not (it evidences no
    side); a sub-threshold scare quote is not. These are mechanical
    diagnostics — never a correctness verdict (READING_TRUTH_V1 P5).

    B0 (P6.0) measured the previous checks wrong both ways: ``required_side``
    counted only section-id tokens scoped to the requirement's material, so an
    answer quoting the operator's text failed it, while a bare requirement
    address counted as a regulatory citation."""
    from scripts.compliance.truth.citation_integrity import integrity

    answer = str(record.get("answer") or "")
    result = integrity(repo, answer)
    checks = {
        "answered": bool(answer.strip())
        and not record.get("turn_budget_exceeded")
        and record.get("http_status") in (200, None),
        "cited_something": any(line["grounded"] for line in result["lines"]),
        "grounding_per_claim": result["grounded"],
        "required_side_present": spec["requires_side"] in result["sides_evidenced"],
        "no_fabricated_ids": not result["fabricated_tokens"],
    }
    return checks, result


def _row(repo, standard: str, ref: str, spec: dict, record: dict) -> dict:
    checks, result = _checks(repo, spec, record)
    answer = str(record.get("answer") or "")
    verdict = "PASS" if all(checks.values()) else "FAIL"
    failed = [k for k, v in checks.items() if not v]
    return {
        "standard": standard,
        "requirement": ref,
        **{k: spec[k] for k in ("key", "requires_side", "has_stored_relation", "cross_check")},
        "question": spec["question"],
        "answer": answer,
        "answer_chars": len(answer),
        "wall_s": record.get("wall_s"),
        "first_token_s": record.get("first_token_s"),
        "citation_integrity": {k: v for k, v in result.items() if k != "lines"},
        "pipeline_errors": record.get("pipeline_errors") or {},
        "sides_cited": result["sides_evidenced"],
        "checks": checks,
        "verdict": verdict,
        "reason": "all checks passed" if verdict == "PASS" else f"failed: {', '.join(failed)}",
    }


def _ask_one(
    session: httpx.Client,
    router: str,
    workspace: str,
    repo,
    standard: str,
    ref: str,
    timeout: float,
    out_dir: pathlib.Path,
    only: frozenset[str] = frozenset(),
) -> list[dict]:
    rows: list[dict] = []
    for spec in _question_specs(ref):
        if only and f"{standard}:{spec['key']}" not in only:
            continue
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

        (out_dir / "transcripts" / f"{standard}__{spec['key']}.json").write_text(
            json.dumps(record, indent=2, default=str)
        )
        rows.append(_row(repo, standard, ref, spec, record))
    return rows


def _rescore_receipt(out_dir: pathlib.Path, receipt_name: str, rescore_row) -> int:
    """Recompute every row's mechanical checks from its saved transcript with
    the CURRENT check code, in place. The as-run verdict and checks are kept on
    each row (``as_run``), and the receipt records when, at which commit and
    why it was rescored — the model is not asked again."""
    import subprocess

    path = out_dir / receipt_name
    receipt = json.loads(path.read_text())
    rows = []
    for row in receipt["rows"]:
        as_run = row.get("as_run") or {"verdict": row.get("verdict"), "checks": row.get("checks")}
        new = rescore_row(row)
        rows.append({**(new or row), "as_run": as_run})
    receipt["rows"] = rows
    receipt["n_passed"] = sum(1 for r in rows if r.get("verdict") == "PASS")
    receipt["verdict"] = "PASS" if receipt["n_passed"] == len(rows) else "FAIL"
    receipt["rescored"] = {
        "utc": _dt.datetime.now(_dt.UTC).isoformat(),
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        ).stdout.strip(),
        "reason": "mechanical checks recomputed from saved transcripts with the current check code",
    }
    path.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"RESCORED {path}: {receipt['n_passed']}/{len(rows)} pass")
    return 0


def _rescore(out_dir: pathlib.Path) -> int:
    repo = Repository()

    def rescore_row(row: dict) -> dict | None:
        transcript = out_dir / "transcripts" / f"{row['standard']}__{row['key']}.json"
        if not transcript.is_file():
            return None
        spec = next(s for s in _question_specs(row["requirement"]) if s["key"] == row["key"])
        record = json.loads(transcript.read_text())
        return _row(repo, row["standard"], row["requirement"], spec, record)

    try:
        return _rescore_receipt(out_dir, "product_questions_family.json", rescore_row)
    finally:
        repo.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="compliance-reading")
    ap.add_argument("--standards", default="CIP-007-6", help="comma-separated standard ids")
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument(
        "--only", default="", help="comma-separated <standard>:<key> questions (e.g. one split)"
    )
    ap.add_argument(
        "--rescore", action="store_true", help="recompute checks for an existing --out-dir"
    )
    args = ap.parse_args()

    _bad = _local.refusal(args.out_dir, "--out-dir")
    if _bad:
        raise SystemExit(_bad)
    if args.rescore:
        return _rescore(args.out_dir)
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
    counts_before = store_counts(repo)
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
                        frozenset(q.strip() for q in args.only.split(",") if q.strip()),
                    )
                )
    finally:
        counts_after = store_counts(repo)
        repo.close()

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "workspace": args.workspace,
        "router": router,
        "verdict_basis": "mechanical",
        "provenance": receipt_provenance(args.workspace, harness_file=__file__),
        "store_guard": store_guard(counts_before, counts_after),
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
            "the local runs tree (portal/modules/compliance/data/private/runs)."
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
