"""The reading judgment — one pass that reads both sides and judges per duty.

The architecture this replaces asked three sealed models three decomposed
questions and gated each on the last:

    alignment  "is candidate X the SAME duty as the governing Part?"
    council    "does this PRE-ANALYZED packet satisfy the unit?"
    reporter   "characterise coverage; do not re-judge, never reverse"

The first question is the one that fails, and it fails because it is malformed.
Acceptance case 10 supplies the proof. Its L22 reads "SMEs shall complete that
patch-applicability evaluation once every 40 calendar days" — a cadence fragment
constraining a duty stated in a sibling clause, not a duty of its own. Asked
SAME-or-DIFFERENT about it, two of three seats answered DIFFERENT *while
emitting a correct 35/40 operand binding*: a sane answer to a question with no
correct answer. Quorum then resolved L22 to DIFFERENT, ``_allowed_internal_ids``
struck it from the citable set, the reporter's WEAKER_COMMITMENT gap cited the
one document the gap is about, and the Part came back UNRESOLVED with empty
``covered`` and ``gaps`` — discarding a council determination of PARTIAL/GAP
that was already correct.

Measured on that same case with the same three models, asked to read instead
(reports/compliance/READING_JUDGMENT_V1.md): every seat returned
``documentary_coverage: PARTIAL`` with a WEAKER_COMMITMENT gap, and two of three
were correct on every citation. The seats were never the defect.

So duty enumeration happens *as part of reading the Part*, and no candidate is
ever classified on its own. The deterministic layer that follows is demoted from
verdict authority to evidence verification: it proves a cited span exists in the
pinned source and that a claimed quantity is really there. A verification
failure marks the **citation** unverified and names it; it downgrades the
verdict only when the unverifiable claim is the one the verdict rests on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    CoveredCommitment,
    ExplanationUncertainty,
    GroundedGap,
    SourceSlice,
)

__all__ = [
    "DutyFinding",
    "ReadingJudgment",
    "build_reading_packet",
    "read_and_judge",
    "verify_judgment",
]

_FINDINGS = ("COVERED", "PARTIAL", "MISSING")
_GAP_KINDS = ("OMISSION", "WEAKER_COMMITMENT", "CONTRADICTION", "OUTDATED_LANGUAGE")
_COVERAGE = ("FULL", "PARTIAL", "NONE", "UNRESOLVED")

# A read of a Part plus its candidates, per-duty findings and cited ids. The
# 900-token council budget was sized for a one-sentence rationale.
_READING_BUDGET = 8192


READING_SYSTEM = """You are a compliance analyst. You are given one governing requirement in full and the operator's candidate material in full. Read both and decide whether the operator's material satisfies the requirement and its evident intent.

Work in this order.

1. READ THE GOVERNING REQUIREMENT — its text, its parent lead-in, the definitions and references it depends on, and the standard's own Measures. ENUMERATE EVERY MANDATORY DUTY IT IMPOSES. One entry per duty, each carrying the governing slice ids that establish it.
   References are supplied so you can resolve terms the Part uses. A reference is CONTEXT, never a duty: never enumerate a duty from a reference, and never judge the operator against a reference's own obligations.

2. READ THE OPERATOR'S CANDIDATE MATERIAL in full.

3. JUDGE EACH ENUMERATED DUTY: "COVERED", "PARTIAL" or "MISSING", citing the candidate slice ids that support the finding, and where a quantity is involved the exact operand text from each side.

4. DERIVE "documentary_coverage" from the per-duty findings, with a rationale naming which duties drove it.

5. For every duty that is not COVERED, emit a gap.

HOW TO READ:
- A different deadline on the same duty is WEAKER OR STRICTER COVERAGE OF THAT DUTY, never a different duty. 40 days against a required 35 is PARTIAL with a WEAKER_COMMITMENT gap. 30 days against a required 35 is COVERED — stricter is never a violation.
- Candidate clauses are read TOGETHER. One clause may state an activity and another its cadence; a cadence clause referring to "that evaluation" implements the activity named in a sibling clause. Never judge a fragment in isolation.
- A clause may implement only part of a duty and still cover that part.
- Material about a different activity, a different standard or a disjoint population is simply not evidence for this Part. Say so and move on — it is not a contradiction and it creates no uncertainty.
- One adequate policy or procedure can suffice. Neither both document classes nor a percentage of matching wording is required.
- A term alignment described as dated, or as last checked or aligned at some past time, is not current alignment: the mapping is stale, so the duty is PARTIAL with an OUTDATED_LANGUAGE gap even when the substantive duty is otherwise satisfied.
- Do not infer a commitment from silence. Do not invent obligations the Part does not impose.
- An OMISSION gap asserts that NOTHING supplied addresses the duty. That is a claim about the completeness of the search, which you cannot see: it is carried by a completeness receipt. Emit an OMISSION only by selecting a supplied allowed_boundary_proof_ids value into the gap's "boundary_proof_id", leaving its counterevidence empty. If no boundary proof id is supplied, absence is not provable — record the duty as MISSING and say in "uncertainties" that the search boundary was not proven complete. Never invent a boundary id.

documentary_coverage:
- "FULL" only when EVERY enumerated duty is COVERED with at least one cited candidate slice id.
- "PARTIAL" when at least one duty is COVERED or PARTIAL and at least one is not COVERED.
- "NONE" when no duty is COVERED or PARTIAL.
- "UNRESOLVED" only when you cannot read the material supplied.

Cite slice ids only, taken from the supplied selectable ids. Never write a quoted span, an ellipsis or a character offset; the application emits the stored text for the ids you select.

Return ONE JSON object:
{"duties":[{"duty_id":"d1","statement":"...","governing_slice_ids":["..."],"finding":"COVERED|PARTIAL|MISSING","candidate_slice_ids":["..."],"governing_operand":"","candidate_operand":"","rationale":"..."}],"documentary_coverage":"FULL|PARTIAL|NONE|UNRESOLVED","rationale":"...","gaps":[{"duty_id":"d1","kind":"OMISSION|WEAKER_COMMITMENT|CONTRADICTION|OUTDATED_LANGUAGE","missing_commitment":"...","governing_slice_ids":["..."],"internal_counterevidence_slice_ids":["..."]}],"uncertainties":[{"reason":"...","source_slice_ids":["..."]}]}"""


@dataclass
class DutyFinding:
    """One mandatory duty the Part imposes, and how the operator's material met it."""

    duty_id: str
    statement: str
    finding: str  # COVERED | PARTIAL | MISSING
    governing_slice_ids: list[str] = field(default_factory=list)
    candidate_slice_ids: list[str] = field(default_factory=list)
    governing_operand: str = ""
    candidate_operand: str = ""
    rationale: str = ""
    unverified_citations: list[str] = field(default_factory=list)
    unverified_operands: list[str] = field(default_factory=list)

    @property
    def verified_support(self) -> bool:
        """At least one candidate citation that actually resolved."""
        return bool(set(self.candidate_slice_ids) - set(self.unverified_citations))


@dataclass
class ReadingJudgment:
    """The product of one reading pass, after verification."""

    documentary_coverage: str = "UNRESOLVED"
    rationale: str = ""
    duties: list[DutyFinding] = field(default_factory=list)
    covered: list[CoveredCommitment] = field(default_factory=list)
    gaps: list[GroundedGap] = field(default_factory=list)
    uncertainties: list[ExplanationUncertainty] = field(default_factory=list)
    valid: bool = False
    failure: str = ""
    downgraded_from: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


# ── packet ──────────────────────────────────────────────────────────────────


def build_reading_packet(request: AssessmentRequest) -> dict[str, Any]:
    """Both sides in full, with references marked as context rather than duties.

    Two structural choices are load-bearing, each isolated by single-factor
    ablation on the live case-10 packet (THINKING_CONFOUND_V1.md §4):

    * A reference-closure entry is a **different duty**. Presented among the
      governing slices and in ``selectable_slice_ids``, it reads as co-equal
      governing material, and granite anchored the candidate against it rather
      than against the Part. Here references are a separate, clearly labelled
      block and are never selectable as duty evidence.
    * The applicability ``scope`` block flipped mistral. Duty coverage is not an
      applicability question, and applicability is already decided upstream, so
      the packet carries a one-line note instead of the decision surface.
    """
    governing = request.governing
    candidates = list(request.candidate_set.records) if request.candidate_set else []

    gov_slices = [
        s for s in (governing.source_slices if governing else []) if s.role != "reference"
    ]
    ref_slices = [
        s for s in (governing.source_slices if governing else []) if s.role == "reference"
    ]

    packet: dict[str, Any] = {
        "governing": {
            "ref": governing.ref if governing else request.requirement_id,
            "part_text": governing.part_text if governing else "",
            "lead_in": governing.lead_in if governing else "",
            "definitions": list(governing.definitions) if governing else [],
            # NOT selectable, and named so the model cannot mistake it for a duty
            "references_for_term_resolution_only": [
                {
                    **r,
                    "note": "context for resolving a term in the Part; not a duty under assessment",
                }
                for r in (list(governing.references) if governing else [])
            ],
            "measures": getattr(governing, "measures", "") if governing else "",
            "selectable_slice_ids": [s.slice_id for s in gov_slices],
            "source_slices": [
                {"slice_id": s.slice_id, "ref": s.ref, "role": s.role, "text": s.text}
                for s in gov_slices
            ],
        },
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "document_id": c.document_id,
                "locator": c.locator,
                "text": c.text,
                "selectable_slice_ids": ([c.source_slice.slice_id] if c.source_slice else []),
            }
            for c in candidates
        ],
        "scope_note": (
            "applicability for this Part is already decided upstream; "
            "do not re-decide it and do not treat it as evidence"
        ),
        # An OMISSION asserts that NOTHING in the corpus addresses the duty.
        # That is a claim about the search boundary, which the reader cannot
        # see, so it is carried by a completeness receipt. Empty here means the
        # boundary was not proven complete and absence is therefore unprovable.
        "allowed_boundary_proof_ids": (
            [boundary_proof_id(request)] if boundary_proof_id(request) else []
        ),
    }
    if ref_slices:
        packet["governing"]["reference_texts"] = [
            {"ref": s.ref, "text": s.text} for s in ref_slices
        ]
    return packet


def boundary_proof_id(request: AssessmentRequest) -> str:
    """The completed-boundary receipt id, or "" when absence cannot be proven."""
    from portal.modules.compliance.core.assessment_report import _boundary_proof_id

    return str(_boundary_proof_id(request))


def _slice_index(request: AssessmentRequest) -> dict[str, SourceSlice]:
    index: dict[str, SourceSlice] = {}
    if request.governing:
        for s in request.governing.source_slices:
            index[s.slice_id] = s
    if request.candidate_set:
        for c in request.candidate_set.records:
            if c.source_slice is not None:
                index[c.source_slice.slice_id] = c.source_slice
    return index


# ── verification (never veto) ───────────────────────────────────────────────

_NUMBER = re.compile(r"(?<![\d.])(\d+)(?![\d.])")


def _operand_is_in_source(operand: str, texts: list[str]) -> bool:
    """Every number claimed in the operand must appear in some pinned source.

    Deliberately narrow. The claim under test is "the source really says this
    quantity", so only the digits are checked; paraphrase around them is the
    model's job and is not evidence of fabrication.
    """
    numbers = _NUMBER.findall(operand or "")
    if not numbers:
        return True
    blob = " ".join(texts)
    return all(re.search(rf"(?<![\d.]){n}(?![\d.])", blob) for n in numbers)


def _verify_duties(
    obj: dict[str, Any], index: dict[str, SourceSlice]
) -> tuple[list[DutyFinding], list[ExplanationUncertainty]]:
    """Resolve each duty's citations and quantity claims against the pinned sources."""
    duties: list[DutyFinding] = []
    uncertainties: list[ExplanationUncertainty] = []

    for i, raw_duty in enumerate(obj.get("duties") or [], start=1):
        finding = str(raw_duty.get("finding") or "").upper()
        if finding not in _FINDINGS:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=f"duty {i} returned an unknown finding {finding!r}; duty dropped",
                    code="READING_DUTY_INVALID",
                )
            )
            continue
        gov_ids = [str(x) for x in (raw_duty.get("governing_slice_ids") or [])]
        cand_ids = [str(x) for x in (raw_duty.get("candidate_slice_ids") or [])]
        unresolved = [x for x in gov_ids + cand_ids if x not in index]

        duty = DutyFinding(
            duty_id=str(raw_duty.get("duty_id") or f"d{i}"),
            statement=str(raw_duty.get("statement") or ""),
            finding=finding,
            governing_slice_ids=gov_ids,
            candidate_slice_ids=cand_ids,
            governing_operand=str(raw_duty.get("governing_operand") or ""),
            candidate_operand=str(raw_duty.get("candidate_operand") or ""),
            rationale=str(raw_duty.get("rationale") or ""),
            unverified_citations=unresolved,
        )

        # Quantity claims are checked against the text of the ids the duty cites.
        gov_texts = [index[x].text for x in gov_ids if x in index]
        cand_texts = [index[x].text for x in cand_ids if x in index]
        if duty.governing_operand and not _operand_is_in_source(duty.governing_operand, gov_texts):
            duty.unverified_operands.append(
                f"governing operand not in source: {duty.governing_operand!r}"
            )
        if duty.candidate_operand and not _operand_is_in_source(duty.candidate_operand, cand_texts):
            duty.unverified_operands.append(
                f"candidate operand not in source: {duty.candidate_operand!r}"
            )

        for ref in unresolved:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=f"duty {duty.duty_id} cites {ref!r}, which is not in the packet",
                    code="READING_CITATION_UNVERIFIED",
                )
            )
        for note in duty.unverified_operands:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=f"duty {duty.duty_id}: {note}",
                    source_slice_ids=[x for x in gov_ids + cand_ids if x in index],
                    code="READING_OPERAND_UNVERIFIED",
                )
            )
        duties.append(duty)
    return duties, uncertainties


def verify_judgment(
    obj: dict[str, Any],
    request: AssessmentRequest,
) -> ReadingJudgment:
    """Check the reading against the pinned sources. Name failures; do not veto.

    An unresolvable citation marks *that citation* unverified. A fabricated
    quantity drops *that operand*. Neither voids a duty finding, and neither
    voids the verdict — unless the verdict rests on nothing that verified, which
    is the one case where UNRESOLVED is the honest answer.
    """
    index = _slice_index(request)
    coverage = str(obj.get("documentary_coverage") or "UNRESOLVED").upper()
    if coverage not in _COVERAGE:
        return ReadingJudgment(
            documentary_coverage="UNRESOLVED",
            valid=False,
            failure=f"reading returned an unknown documentary_coverage {coverage!r}",
            raw={"response": obj},
        )

    duties, uncertainties = _verify_duties(obj, index)

    if not duties:
        return ReadingJudgment(
            documentary_coverage="UNRESOLVED",
            valid=False,
            failure="the reading enumerated no duty for this Part",
            uncertainties=uncertainties,
            raw={"response": obj},
        )

    covered = [
        CoveredCommitment(
            commitment=d.statement,
            governing_slice_ids=[x for x in d.governing_slice_ids if x in index],
            internal_slice_ids=[x for x in d.candidate_slice_ids if x in index],
        )
        for d in duties
        if d.finding in ("COVERED", "PARTIAL") and d.verified_support
    ]

    gaps: list[GroundedGap] = []
    by_duty = {d.duty_id: d for d in duties}
    for i, raw_gap in enumerate(obj.get("gaps") or [], start=1):
        kind = str(raw_gap.get("kind") or "").upper()
        if kind not in _GAP_KINDS:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=f"gap {i} has an unknown kind {kind!r}; gap dropped",
                    code="READING_GAP_INVALID",
                )
            )
            continue
        counter = [str(x) for x in (raw_gap.get("internal_counterevidence_slice_ids") or [])]
        gov = [str(x) for x in (raw_gap.get("governing_slice_ids") or [])]
        bad = [x for x in counter + gov if x not in index]
        for ref in bad:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=f"gap {i} cites {ref!r}, which is not in the packet",
                    code="READING_CITATION_UNVERIFIED",
                )
            )
        gaps.append(
            GroundedGap(
                gap_id=str(raw_gap.get("gap_id") or f"g{i}"),
                kind=kind,
                missing_commitment=str(raw_gap.get("missing_commitment") or ""),
                # unverified ids are dropped from the citation, not the gap
                governing_slice_ids=[x for x in gov if x in index],
                internal_counterevidence_slice_ids=[x for x in counter if x in index],
                boundary_proof_id=str(raw_gap.get("boundary_proof_id") or ""),
            )
        )
        duty = by_duty.get(str(raw_gap.get("duty_id") or ""))
        if duty is not None and duty.finding == "COVERED":
            uncertainties.append(
                ExplanationUncertainty(
                    reason=(
                        f"gap {i} is raised against duty {duty.duty_id}, which the reading "
                        "marked COVERED"
                    ),
                    code="READING_GAP_INCONSISTENT",
                )
            )

    for raw_unc in obj.get("uncertainties") or []:
        uncertainties.append(
            ExplanationUncertainty(
                reason=str(raw_unc.get("reason") or ""),
                source_slice_ids=[
                    str(x) for x in (raw_unc.get("source_slice_ids") or []) if str(x) in index
                ],
                code=str(raw_unc.get("code") or "READING_UNCERTAINTY"),
            )
        )

    unprovable = _unprovable_absences(gaps, boundary_proof_id(request))
    for note in unprovable:
        uncertainties.append(ExplanationUncertainty(reason=note, code="READING_BOUNDARY_UNPROVEN"))
    if unprovable:
        # The reading may be right that nothing addresses the duty, but it cannot
        # be *shown* from an incomplete search. U04, not a NONE verdict.
        return ReadingJudgment(
            documentary_coverage="UNRESOLVED",
            rationale=str(obj.get("rationale") or ""),
            duties=duties,
            covered=covered,
            gaps=[],
            uncertainties=uncertainties,
            valid=False,
            failure=unprovable[0],
            downgraded_from=coverage,
            raw={"response": obj},
        )

    final, downgraded = _derive_coverage(coverage, duties)
    return ReadingJudgment(
        documentary_coverage=final,
        rationale=str(obj.get("rationale") or ""),
        duties=duties,
        covered=covered,
        gaps=gaps,
        uncertainties=uncertainties,
        valid=final != "UNRESOLVED",
        downgraded_from=downgraded,
        raw={"response": obj},
    )


def _unprovable_absences(gaps: list[GroundedGap], allowed: str) -> list[str]:
    """An OMISSION without the completed boundary receipt proves nothing.

    Absence of evidence is a claim about the *search*, not about the documents,
    and a reader cannot see the search boundary. A partial top-k cannot ground
    it (acceptance case 13), so the honest answer is U04_RETRIEVAL_INCOMPLETE
    rather than a NONE verdict that reads as "the operator has no such control".
    """
    problems = []
    for gap in gaps:
        if gap.kind != "OMISSION":
            continue
        if not allowed or gap.boundary_proof_id != allowed:
            problems.append(
                f"gap {gap.gap_id} claims an OMISSION without the completed "
                "boundary receipt; absence is not provable from this search"
            )
        elif gap.internal_counterevidence_slice_ids:
            problems.append(
                f"gap {gap.gap_id} is an OMISSION citing internal counterevidence; "
                "a source that does not mention a duty is not a quote proving absence"
            )
    return problems


def _derive_coverage(claimed: str, duties: list[DutyFinding]) -> tuple[str, str]:
    """Enforce §5's FULL definition, finally checkable because duties are enumerated.

    `assessment_report._consistency_error` had exactly one FULL check —
    ``decision == "SUPPORTED"`` — and nothing verified the brief's actual rule,
    that *all applicable mandatory duties in the whole Part are satisfied*. With
    the duties enumerated the rule is mechanical, and this is what settles the
    false-FULL family (cases 08, 16).
    """
    if all(not d.verified_support and d.finding != "MISSING" for d in duties):
        # nothing the reading relied on survived verification
        return "UNRESOLVED", claimed

    every_duty_covered = all(d.finding == "COVERED" and d.verified_support for d in duties)
    if claimed == "FULL" and not every_duty_covered:
        uncovered = [d.duty_id for d in duties if d.finding != "COVERED"]
        unsupported = [
            d.duty_id for d in duties if d.finding == "COVERED" and not d.verified_support
        ]
        if uncovered or unsupported:
            return ("PARTIAL" if any(d.finding != "MISSING" for d in duties) else "NONE"), "FULL"
    if claimed != "FULL" and every_duty_covered:
        # the reading undersold itself; keep its own answer rather than promote
        return claimed, ""
    return claimed, ""


# ── entry point ─────────────────────────────────────────────────────────────


def read_and_judge(
    request: AssessmentRequest,
    context: AssessmentContext,
    *,
    transport: Any = None,
    model: str = "",
) -> ReadingJudgment:
    """One reasoning pass over both sides, then verification of what it cited."""
    packet = build_reading_packet(request)
    user = json.dumps(packet, indent=2, ensure_ascii=False, default=str)

    fn = transport or context.report_fn or context.seat_fn
    chosen = (
        model
        or context.report_model
        or (str(context.seats[0].get("model", "")) if context.seats else "")
    )
    if fn is None:
        from portal.modules.compliance.core.reading_transport import chat

        def fn(m: str, system: str, u: str) -> str:
            return chat(m, system, u, budget=_READING_BUDGET, fmt="json").content

    try:
        raw = fn(chosen, READING_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - a failed read is unresolved, not a crash
        return ReadingJudgment(
            documentary_coverage="UNRESOLVED",
            valid=False,
            failure=f"reading transport failed: {exc}",
            raw={"request": packet},
        )

    obj = _json_object(raw)
    if obj is None:
        return ReadingJudgment(
            documentary_coverage="UNRESOLVED",
            valid=False,
            failure="the reading returned no JSON object",
            raw={"request": packet, "response": raw[:4000]},
        )

    judgment = verify_judgment(obj, request)
    judgment.raw = {"request": packet, "response": obj}
    return judgment


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
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
