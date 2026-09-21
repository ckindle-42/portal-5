#!/usr/bin/env python3
"""CLOSEOUT_V1 P6 / CONTRACT_AND_CLOSE_V1 P4 - sort every sweep refusal.

  model_side_error   - the model paired across the jurisdiction line: named a
                       regulatory section where an operator section belongs,
                       or the reverse. A reading defect. (CIP-003-8: 18/20.)
  non_verbatim_quote - the quoted sentence is not a literal substring of the
                       section, at whatever containment ratio. No threshold
                       is applied here - see ``threshold_note`` in the
                       receipt. A6.3's checker_strictness / quote_discipline
                       split came from READING the quotes by hand; both cases
                       emit the identical rejection reason string, so no rule
                       here reproduces that split without fitting a floor to
                       A6.3's count after the fact.
  address_form        - well-formed once normalised to the register's own
                       spelling (``R2.4`` -> ``R2 Part 2.4``); the model was
                       right and the parser was strict. Re-offered to
                       ``record_determination`` with the normalised address.
  register_gap        - well-formed, normalises cleanly, and still names no
                       requirement this store's register tracks. A corpus
                       finding, not a model or checker defect.
  unclassified        - a refusal whose reason matches no rule. Counted and
                       listed in full, never silently folded into a bucket.

Admission is untouched except for ``address_form``: a pairing rejected only
because the requirement id was spelled in the standard's own shorthand is
re-offered to ``record_determination`` with the normalised address, and
admitted if it passes every other check the sweep already applies. Nothing
else here writes to the store.

Exit codes: 0 always.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Any

#: The bands a mechanically-derived split falls into. Recorded, not
#: thresholded - see the receipt's ``threshold_note``.
_CONTAINMENT_BANDS = ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0")

_THRESHOLD_NOTE = (
    "No threshold is applied. A6.3 separated CIP-004-7's 15 refusals into 8 "
    "checker-strictness and 7 model-discipline BY READING THE QUOTES - both "
    "emit the identical reason string, so no rule reproduces that split. "
    "Choosing a floor to match A6.3's count would be fitting, not "
    "calibrating. The bands below are the evidence a checker-relaxation task "
    "needs to choose a floor against a re-read sample; that task owns the "
    "decision."
)


def _band(ratio: float) -> str:
    idx = min(int(ratio * 5), 4)
    return _CONTAINMENT_BANDS[idx]


def _section_text(repo: Any, section_id: str) -> str:
    """Verbatim section text via the module's own accessor (adaptation,
    recorded): source_sections stores char spans, not a text column - the
    task's ``SELECT text`` returned nothing for every row, which would have
    silently dropped all 25 sentence-bearing refusals into unclassified."""
    try:
        from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

        resolved = resolve_sections(repo, [parent_section_id(section_id)])
        entry = resolved.get(parent_section_id(section_id)) or {}
        return str(entry.get("text") or "")
    except Exception:  # noqa: BLE001 - an unreadable section yields no text, never a guess
        return ""


def _section_jurisdiction(repo: Any, section_id: str) -> str:
    try:
        from portal.modules.compliance.core.section_index import parent_section_id, resolve_sections

        resolved = resolve_sections(repo, [parent_section_id(section_id)])
        entry = resolved.get(parent_section_id(section_id)) or {}
        return str(entry.get("jurisdiction") or "")
    except Exception:  # noqa: BLE001 - an unreadable section resolves to no side, never a guess
        return ""


def _classify(repo: Any, outcome: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    from portal.modules.compliance.core.answer_contract import _SECTION_TOKEN
    from portal.modules.compliance.core.jurisdiction import is_regulatory_side
    from portal.modules.compliance.core.reading_assembly import parse_ref
    from portal.modules.compliance.core.text_match import quote_containment

    reason = str(outcome.get("reason", ""))
    # record_determination's own rejection dict carries "requirement_id" only
    # on SOME branches (it is the thing that failed to parse on others); the
    # sweep's own "ref" for the reading that produced this outcome is the
    # address that was actually asked about, and is the fallback.
    requirement_id = str(outcome.get("requirement_id") or outcome.get("ref") or "")
    section_id = str(outcome.get("section_id", ""))
    if not section_id:
        # A receipt sourced from before the jurisdiction-crossing rejection
        # carried its own section_id: the id is still in the reason string
        # ("section 'isection-...' is US jurisdiction — ..."), so it is
        # recovered rather than lost to unclassified.
        found = _SECTION_TOKEN.search(reason)
        section_id = found.group(0) if found else ""
    sentence = str(outcome.get("sentence", ""))
    detail: dict[str, Any] = {}

    # 1. jurisdiction crossing - decided on the STORE's own jurisdiction for
    # this section, never a prefix guess or a regex over the reason's prose.
    if section_id and is_regulatory_side(_section_jurisdiction(repo, section_id)):
        return ("model_side_error", "paired a regulatory section as the operator side", detail)
    if "not found" in reason.lower() or "does not resolve" in reason.lower():
        return ("model_side_error", reason, detail)

    # 2. address form - the standard's own shorthand, rejected by a stricter
    # parser than the standard uses. Re-offered with the normalised address;
    # the caller decides admission.
    if "is not a regulatory address" in reason and requirement_id:
        parsed = parse_ref(requirement_id)
        if parsed is not None:
            detail = {"normalized_requirement_id": str(parsed)}
            return ("address_form", f"normalizes to {parsed!s}", detail)

    # 3. register gap - well-formed, normalizes, and still names nothing the
    # register tracks. A corpus finding, not a reading or checker defect.
    if "is not in the register" in reason and requirement_id:
        parsed = parse_ref(requirement_id)
        if parsed is not None:
            return (
                "register_gap",
                f"{parsed!s} is well-formed and absent from the register",
                detail,
            )

    # 4. quote present vs absent - one measure, no threshold applied here.
    if sentence and section_id:
        body = _section_text(repo, section_id)
        if body:
            measure = quote_containment(sentence, body)
            detail = {
                "containment_ratio": measure["ratio"],
                "containment_band": _band(measure["ratio"]),
                "verbatim": measure["verbatim"],
                "backend": measure["backend"],
            }
            if not measure["verbatim"]:
                return (
                    "non_verbatim_quote",
                    f"quoted sentence not a verbatim substring (containment {measure['ratio']:.2f})",
                    detail,
                )

    return ("unclassified", reason or "no reason recorded", detail)


def _refusals_from_store(repo: Any, sweep_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every rejection this sweep recorded, read back from the store.

    Adaptation, recorded: the task walked the sweep ARTIFACT for
    ``determinations.outcomes``, but the artifact holds per-ref COUNTS only —
    the outcomes persist in ``reading_runs.closure_json`` (the 9077422 fix is
    precisely that they persist THERE). The artifact's per-ref ``run_id`` pins
    the exact retained runs, so nothing outside this sweep can leak in.
    """
    refusals: list[dict[str, Any]] = []
    for standard in sweep_data.get("standards", []):
        for row in standard.get("rows", []):
            run_id = str(row.get("run_id") or "")
            if not run_id:
                continue
            rows = repo._conn.execute(
                "SELECT subject_ref, closure_json FROM reading_runs WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            for subject_ref, closure_json in rows:
                try:
                    closure = json.loads(closure_json or "{}")
                except json.JSONDecodeError:
                    continue
                det = closure.get("determinations") or {}
                for o in det.get("outcomes") or []:
                    if isinstance(o, dict) and o.get("action") == "rejected":
                        refusals.append(
                            {**o, "standard": standard.get("standard", ""), "ref": subject_ref}
                        )
    return refusals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from portal.modules.compliance.core.repository import Repository

    sweep_data = json.loads(args.sweep.read_text())

    repo = Repository()
    try:
        refusals = _refusals_from_store(repo, sweep_data)
        buckets: dict[str, list[dict[str, Any]]] = {
            "model_side_error": [],
            "non_verbatim_quote": [],
            "address_form": [],
            "register_gap": [],
            "unclassified": [],
        }
        for r in refusals:
            cat, why, detail = _classify(repo, r)
            buckets[cat].append(
                {
                    "standard": r.get("standard"),
                    "requirement": r.get("ref"),
                    "section_id": r.get("section_id"),
                    "relation_type": r.get("relation_type"),
                    "sentence": r.get("sentence"),
                    "original_reason": r.get("reason"),
                    "classification_reason": why,
                    **detail,
                }
            )

        # address_form is the one category this script re-offers: the pairing
        # was rejected only because the requirement id was spelled in the
        # standard's own shorthand, and re-parsing it now succeeds. Re-run it
        # through record_determination with the normalised address; every
        # other check (register membership, verbatim quote, jurisdiction)
        # still applies, so this admits nothing the sweep would not have.
        from portal.modules.compliance.core import candidate_links

        for entry in buckets["address_form"]:
            normalized = entry.get("normalized_requirement_id")
            section_id = entry.get("section_id")
            if not normalized or not section_id:
                entry["reoffer"] = {
                    "action": "skipped",
                    "reason": "missing normalized address or section",
                }
                continue
            entry["reoffer"] = candidate_links.record_determination(
                repo,
                requirement_id=normalized,
                section_id=section_id,
                relation_type=str(entry.get("relation_type") or ""),
                answer_id=f"adjudicate-address-form-{section_id}",
                sentence=str(entry.get("sentence") or ""),
                read_ref=str(entry.get("requirement") or ""),
            )
    finally:
        repo.close()

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "sweep_receipt": str(args.sweep),
        "quote_measure": "token_set_containment (text_match.quote_containment)",
        "threshold_note": _THRESHOLD_NOTE,
        "n_refusals": len(refusals),
        "totals": {k: len(v) for k, v in buckets.items()},
        "categories": buckets,
        "admission_note": (
            "Only address_form pairings are re-offered to record_determination, with "
            "the normalised address in place of the standard's shorthand — every other "
            "check the sweep already applies still governs admission. Nothing else here "
            "writes to the store. non_verbatim_quote is a candidate set for a future "
            "checker-relaxation task, not a backlog of edges waiting to be let in."
        ),
        "verdict": "RECORDED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {args.out}")
    for k, v in receipt["totals"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
