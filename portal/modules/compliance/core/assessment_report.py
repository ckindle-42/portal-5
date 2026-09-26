"""Workstream C — the bounded, source-linked coverage explanation
(IMPLEMENTATION_BRIEF §4/§5).

The satisfaction judgment belongs to ``council.run_council``. This stage makes
exactly one explicit call through a separate reporting transport (never a
council seat, never ``council._SEAT_SYSTEM``) to characterise *documentary
coverage* of the unchanged decision: which substantive commitments are covered
and which concrete shortfalls are demonstrated.

The model selects immutable source-slice IDs only. The application emits the
stored text for those IDs; a model-written quote, an ellipsis splice, an
approximate source name or a generated character offset is rejected. The
closed consistency rules are enforced in code, and an invalid or incompatible
report becomes ``UNRESOLVED`` — never silently the more favorable output and
never a gap reconstructed from rationale keywords.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from portal.modules.compliance.core.determination import (
    AlignmentResult,
    AssessmentContext,
    AssessmentRequest,
    CoverageExplanation,
    CoveredCommitment,
    ExplanationUncertainty,
    GroundedGap,
)

__all__ = ["explain"]

_GAP_KINDS = ("OMISSION", "WEAKER_COMMITMENT", "CONTRADICTION", "OUTDATED_LANGUAGE")
_REPORT_COVERAGE = ("FULL", "PARTIAL", "NONE", "UNRESOLVED")
_TEXT_KEYS = ("text", "quote", "verbatim", "quote_text", "snippet", "excerpt")
_OFFSET_KEYS = (
    "char_start",
    "char_end",
    "offset",
    "start_offset",
    "end_offset",
    "doc_char_start",
    "doc_char_end",
)

# The reporter emits covered commitments, grounded gaps and uncertainties with
# exact slice ids — several records, not one verdict. It previously inherited
# the council seat's 900-token budget by reusing that transport.
_REPORT_BUDGET = 8192

_REPORT_SYSTEM = (
    "You are a source-linked reporting analyst. You receive an already-decided "
    "satisfaction result and the exact selectable source slices. You "
    "characterise documentary coverage; you do not re-judge the requirement and "
    "you never reverse the supplied decision.\n"
    "Return ONE JSON object with:\n"
    '- "documentary_coverage": "FULL" | "PARTIAL" | "NONE" | "UNRESOLVED"\n'
    '- "covered": [{"commitment", "governing_slice_ids", "internal_slice_ids"}]\n'
    '- "gaps": [{"gap_id", "kind", "missing_commitment", "governing_slice_ids", '
    '"internal_counterevidence_slice_ids", "boundary_proof_id"}]\n'
    '- "uncertainties": [{"reason", "source_slice_ids", "code"}]\n'
    "kinds are OMISSION, WEAKER_COMMITMENT, CONTRADICTION or OUTDATED_LANGUAGE.\n"
    "RULES:\n"
    "- Select slice ids only. Never write quoted text, an ellipsis splice or a "
    "character offset; the application emits the stored text for the ids you "
    "select.\n"
    "- Use only ids from the supplied selectable slices.\n"
    "- For an OMISSION, select a supplied allowed_boundary_proof_id and leave "
    "internal_counterevidence_slice_ids empty. A source that does not mention a "
    "duty is not an internal quote proving absence. Never invent a boundary id.\n"
    "- Full coverage requires the overall supported result. Partial coverage "
    "requires both a covered commitment and a grounded shortfall. No coverage "
    "requires no supported commitment plus a valid completeness or explicit "
    "contrary basis."
)


def explain(
    request: AssessmentRequest,
    council_result: dict[str, Any],
    alignment: AlignmentResult,
    source_catalog: dict[str, dict[str, Any]],
    context: AssessmentContext,
) -> CoverageExplanation:
    """Characterise one Part's documentary coverage with one bounded call."""
    council = _council_dict(council_result)
    decision = str(council.get("determination", ""))
    transport = context.report_fn or context.seat_fn
    if transport is None:
        # Production supplies no injected transport. Go straight to the shared
        # reasoning transport rather than through ``council._ollama_seat``: the
        # reporter was silently inheriting the council's seat budget, which is
        # sized for a verdict, not for a coverage characterisation.
        from portal.modules.compliance.core.reading_transport import chat

        def transport(model: str, system: str, user: str) -> str:
            return chat(model, system, user, budget=_REPORT_BUDGET, fmt="json").content

    consensus_refs = _agreeing_refs(council)
    governing_ids = _governing_ids(request, source_catalog)
    internal_ids = _allowed_internal_ids(alignment, consensus_refs)
    user_packet = _report_packet(
        request, council, alignment, source_catalog, consensus_refs, governing_ids, internal_ids
    )
    user = json.dumps(user_packet, indent=2, ensure_ascii=False, default=str)
    model = context.report_model or (
        str(context.seats[0].get("workspace") or context.seats[0].get("model", ""))
        if context.seats
        else ""
    )
    try:
        raw = transport(model, _REPORT_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - a failed report is unresolved, not a crash
        return CoverageExplanation(
            documentary_coverage="UNRESOLVED",
            valid=False,
            failure=f"reporting transport failed: {exc}",
            raw={"request": user_packet, "council_decision": decision},
        )

    obj = _json_object(raw)
    raw_trace = {
        "request": user_packet,
        "response": raw,
        "council_decision": decision,
    }
    if obj is None:
        return CoverageExplanation(
            documentary_coverage="UNRESOLVED",
            valid=False,
            failure="report was not a JSON object",
            raw=raw_trace,
        )

    covered, gaps, uncertainties, errors = _validate_report(
        obj, governing_ids, internal_ids, source_catalog
    )
    boundary_id = _boundary_proof_id(request)
    for gap in gaps:
        if gap.boundary_proof_id and gap.boundary_proof_id != boundary_id:
            errors.append("gap cites an unverified boundary proof id")
        if gap.kind == "OMISSION":
            if not boundary_id or gap.boundary_proof_id != boundary_id:
                errors.append("OMISSION requires the supplied completed boundary proof")
            if gap.internal_counterevidence_slice_ids:
                errors.append("OMISSION cannot invent an internal counterevidence quote")
    coverage = str(obj.get("documentary_coverage", "")).upper()
    if coverage not in _REPORT_COVERAGE:
        errors.append(f"invalid documentary_coverage {coverage!r}")
    else:
        rule_error = _consistency_error(coverage, decision, covered, gaps, request)
        if rule_error:
            errors.append(rule_error)

    if errors:
        return CoverageExplanation(
            documentary_coverage="UNRESOLVED",
            covered=covered,
            gaps=gaps,
            uncertainties=uncertainties,
            valid=False,
            failure="; ".join(errors),
            raw={**raw_trace, "errors": errors},
        )
    return CoverageExplanation(
        documentary_coverage=coverage,
        covered=covered,
        gaps=gaps,
        uncertainties=uncertainties,
        valid=True,
        raw=raw_trace,
    )


# ── reporting packet ────────────────────────────────────────────────────────


def _boundary_proof_id(request: AssessmentRequest) -> str:
    from portal.modules.compliance.core.boundary import verified_completeness

    if request.candidate_set is None or request.snapshot is None:
        return ""
    receipt = request.candidate_set.acquisition_receipt.get("boundary_receipt") or {}
    if not verified_completeness(receipt) or request.snapshot.completeness != "COMPLETE":
        return ""
    if set(receipt["examined_sections"]) != {r.chunk_id for r in request.candidate_set.records}:
        return ""
    payload = {"snapshot": request.snapshot.fingerprint, "receipt": receipt}
    return (
        "boundary-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
    )


def _report_packet(
    request: AssessmentRequest,
    council: dict[str, Any],
    alignment: AlignmentResult,
    source_catalog: dict[str, dict[str, Any]],
    consensus_refs: set[str] | None,
    governing_ids: set[str],
    internal_ids: set[str],
) -> dict[str, Any]:
    governing = request.governing
    operative = [
        {
            "candidate_ref": record.candidate_ref,
            "relation": record.relation,
            "candidate_slice_ids": list(record.candidate_slice_ids),
            "activity": record.activity,
            "object": record.object,
            "trigger": record.trigger,
        }
        for record in alignment.records
        if record.relation == "SAME"
    ]
    return {
        "task": "source_linked_explanation",
        "satisfaction_decision": council.get("determination", ""),
        "agreeing_citations": sorted(consensus_refs or []),
        "governing": {
            "ref": governing.ref if governing else request.requirement_id,
            "part_text": governing.part_text if governing else "",
            "lead_in": governing.lead_in if governing else "",
            "governing_slice_ids": sorted(governing_ids),
        },
        "operative_commitments": operative,
        "arithmetic": _arithmetic(alignment),
        "selectable_source_slice_ids": sorted(source_catalog),
        "source_catalog": source_catalog,
        "acquisition_receipt": (
            request.candidate_set.acquisition_receipt if request.candidate_set else {}
        ),
        "completeness": request.snapshot.completeness if request.snapshot else "UNKNOWN",
        "allowed_boundary_proof_ids": [_boundary_proof_id(request)]
        if _boundary_proof_id(request)
        else [],
        "permitted_internal_slice_ids": sorted(internal_ids),
    }


def _arithmetic(alignment: AlignmentResult) -> list[dict[str, Any]]:
    from portal.modules.compliance.core.gate import compare_aligned

    out: list[dict[str, Any]] = []
    for record in alignment.records:
        if record.relation != "SAME":
            continue
        for binding in record.constraint_bindings:
            result, explanation = compare_aligned(binding, record)
            out.append(
                {
                    "link_id": record.link_id,
                    "binding_id": binding.binding_id,
                    "result": result,
                    "explanation": explanation,
                }
            )
    return out


# ── validation ──────────────────────────────────────────────────────────────


def _validate_report(
    obj: dict[str, Any],
    governing_ids: set[str],
    internal_ids: set[str],
    source_catalog: dict[str, dict[str, Any]],
) -> tuple[list[CoveredCommitment], list[GroundedGap], list[ExplanationUncertainty], list[str]]:
    if not isinstance(obj.get("covered"), list):
        return [], [], [], ["report is missing the 'covered' list"]
    if not isinstance(obj.get("gaps"), list):
        return [], [], [], ["report is missing the 'gaps' list"]
    if not isinstance(obj.get("uncertainties"), list):
        return [], [], [], ["report is missing the 'uncertainties' list"]
    covered, c_err = _clean_covered(obj["covered"], governing_ids, internal_ids, source_catalog)
    gaps, g_err = _clean_gaps(obj["gaps"], governing_ids, internal_ids, source_catalog)
    uncertain, u_err = _clean_uncertainties(obj["uncertainties"], source_catalog)
    return covered, gaps, uncertain, c_err + g_err + u_err


def _clean_covered(
    items: list[Any],
    governing_ids: set[str],
    internal_ids: set[str],
    source_catalog: dict[str, dict[str, Any]],
) -> tuple[list[CoveredCommitment], list[str]]:
    out: list[CoveredCommitment] = []
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append("covered entry is not an object")
            continue
        commitment = str(item.get("commitment") or "").strip()
        gov = _str_list(item.get("governing_slice_ids"))
        internal = _str_list(item.get("internal_slice_ids"))
        if not commitment or not gov or not internal:
            errors.append("covered entry is missing a commitment or a slice id list")
            continue
        if any(x not in governing_ids for x in gov):
            errors.append("covered entry cites an off-packet governing slice")
            continue
        if any(x not in internal_ids for x in internal):
            errors.append("covered entry cites an off-packet or excluded internal slice")
            continue
        bad = _reconstructed_quote(item, gov + internal, source_catalog)
        if bad:
            errors.append(f"covered entry supplies a model-reconstructed field {bad!r}")
            continue
        out.append(
            CoveredCommitment(
                commitment=commitment,
                governing_slice_ids=gov,
                internal_slice_ids=internal,
            )
        )
    return out, errors


def _clean_gaps(
    items: list[Any],
    governing_ids: set[str],
    internal_ids: set[str],
    source_catalog: dict[str, dict[str, Any]],
) -> tuple[list[GroundedGap], list[str]]:
    out: list[GroundedGap] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append("gap entry is not an object")
            continue
        kind = str(item.get("kind") or "").upper()
        missing = str(item.get("missing_commitment") or "").strip()
        gov = _str_list(item.get("governing_slice_ids"))
        counter = _str_list(item.get("internal_counterevidence_slice_ids"))
        if kind not in _GAP_KINDS:
            errors.append(f"gap entry has invalid kind {kind!r}")
            continue
        if not missing or not gov:
            errors.append("gap entry is missing a commitment or a governing slice id")
            continue
        if any(x not in governing_ids for x in gov):
            errors.append("gap entry cites an off-packet governing slice")
            continue
        if any(x not in internal_ids for x in counter):
            errors.append("gap entry cites an off-packet or excluded counterevidence slice")
            continue
        bad = _reconstructed_quote(item, gov + counter, source_catalog)
        if bad:
            errors.append(f"gap entry supplies a model-reconstructed field {bad!r}")
            continue
        out.append(
            GroundedGap(
                gap_id=str(item.get("gap_id") or "") or f"gap-{index}",
                kind=kind,
                missing_commitment=missing,
                governing_slice_ids=gov,
                internal_counterevidence_slice_ids=counter,
                boundary_proof_id=str(item.get("boundary_proof_id") or ""),
            )
        )
    return out, errors


def _clean_uncertainties(
    items: list[Any], source_catalog: dict[str, dict[str, Any]]
) -> tuple[list[ExplanationUncertainty], list[str]]:
    out: list[ExplanationUncertainty] = []
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append("uncertainty entry is not an object")
            continue
        reason = str(item.get("reason") or "").strip()
        ids = _str_list(item.get("source_slice_ids"))
        if not reason:
            errors.append("uncertainty entry is missing a reason")
            continue
        if any(x not in source_catalog for x in ids):
            errors.append("uncertainty entry cites an off-packet slice")
            continue
        out.append(
            ExplanationUncertainty(
                reason=reason,
                source_slice_ids=ids,
                code=str(item.get("code") or ""),
            )
        )
    return out, errors


def _reconstructed_quote(
    item: dict[str, Any], ids: list[str], source_catalog: dict[str, dict[str, Any]]
) -> str:
    for key in _TEXT_KEYS:
        value = item.get(key)
        if value in (None, ""):
            continue
        combined = " ".join(str(source_catalog.get(i, {}).get("text", "")) for i in ids).strip()
        if str(value).strip() != combined:
            return key
    for key in _OFFSET_KEYS:
        if item.get(key) not in (None, ""):
            return key
    return ""


# ── closed consistency rules ────────────────────────────────────────────────


def _consistency_error(
    coverage: str,
    decision: str,
    covered: list[CoveredCommitment],
    gaps: list[GroundedGap],
    request: AssessmentRequest,
) -> str:
    if coverage == "UNRESOLVED":
        return ""
    if coverage == "FULL" and decision != "SUPPORTED":
        return f"FULL requires a SUPPORTED decision, got {decision!r}"
    if coverage == "PARTIAL" and (
        decision not in ("PARTIAL", "CONTRADICTED") or not covered or not gaps
    ):
        return "PARTIAL requires a PARTIAL/CONTRADICTED decision with covered and gaps"
    if coverage == "NONE":
        return _none_error(decision, covered, gaps, request)
    return ""


def _none_error(
    decision: str,
    covered: list[CoveredCommitment],
    gaps: list[GroundedGap],
    request: AssessmentRequest,
) -> str:
    if decision not in ("ABSENT", "CONTRADICTED"):
        return f"NONE requires an ABSENT/CONTRADICTED decision, got {decision!r}"
    if covered:
        return "NONE cannot report a supported commitment"
    if decision == "ABSENT":
        if _boundary_proof_id(request):
            return ""
        return "NONE by absence requires a completed boundary or a boundary proof id"
    if any(g.kind == "CONTRADICTION" and g.internal_counterevidence_slice_ids for g in gaps):
        return ""
    return "NONE by contradiction requires explicit contrary internal evidence"


# ── provenance helpers ──────────────────────────────────────────────────────


def _council_dict(council_result: Any) -> dict[str, Any]:
    if isinstance(council_result, dict):
        return council_result
    if is_dataclass(council_result) and not isinstance(council_result, type):
        return asdict(council_result)
    return {}


def _agreeing_refs(council: dict[str, Any]) -> set[str] | None:
    opinions = council.get("opinions")
    if not isinstance(opinions, list) or not opinions:
        return None
    decision = str(council.get("determination", ""))
    dissent = {str(x) for x in (council.get("dissent") or [])}
    refs: set[str] = set()
    for opinion in opinions:
        if not isinstance(opinion, dict):
            continue
        if str(opinion.get("seat_id", "")) in dissent:
            continue
        if not opinion.get("valid", False) or opinion.get("dropped"):
            continue
        if str(opinion.get("determination", "")) != decision:
            continue
        refs.update(str(r) for r in (opinion.get("cited_refs") or []))
    return refs


def _allowed_internal_ids(alignment: AlignmentResult, consensus_refs: set[str] | None) -> set[str]:
    allowed: set[str] = set()
    for record in alignment.records:
        if record.relation != "SAME":
            continue
        if consensus_refs is not None and not _matches_consensus(record, consensus_refs):
            continue
        allowed.update(record.candidate_slice_ids)
    return allowed


def _matches_consensus(record: Any, consensus_refs: set[str]) -> bool:
    own = [
        getattr(record, "candidate_ref", ""),
        getattr(record, "document_id", ""),
        getattr(record, "link_id", ""),
        getattr(record, "governing_ref", ""),
    ]
    for value in own:
        if not value:
            continue
        low = value.lower()
        for ref in consensus_refs:
            low_ref = ref.lower()
            if low == low_ref or low in low_ref or low_ref in low:
                return True
    return False


def _governing_ids(
    request: AssessmentRequest, source_catalog: dict[str, dict[str, Any]]
) -> set[str]:
    if request.governing and request.governing.source_slices:
        return {s.slice_id for s in request.governing.source_slices}
    return {
        slice_id
        for slice_id, meta in source_catalog.items()
        if str(meta.get("role", "")) == "governing"
    }


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = "\n".join(stripped.splitlines()[1:])
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(stripped[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
