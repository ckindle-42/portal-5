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
- CHOOSING THE GAP KIND. Use the operator's own words to decide:
  * CONTRADICTION — the material AUTHORISES or REQUIRES what the Part forbids or conditions. A Part that permits an act only with a named approval, against material letting anyone do it without that approval, is a contradiction: the condition has been removed, not merely loosened.
  * WEAKER_COMMITMENT — the material addresses the duty but commits to LESS than the Part requires: a longer interval, or a mandatory element made optional. The duty survives in weakened form.
  * OUTDATED_LANGUAGE — the material rests on a term alignment described as dated or last checked at some past time.
  * OMISSION — nothing supplied addresses the duty AT ALL. If you can cite candidate material that bears on the duty, the gap is one of the three above, never an OMISSION.
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
    #: citations resolved to a non-operative candidate (traceability row, ToC,
    #: control page, commentary) — demoted, never implementation evidence
    non_operative_citations: list[str] = field(default_factory=list)
    #: citations resolved to a superseded internal revision — stale, demoted
    stale_citations: list[str] = field(default_factory=list)
    #: deterministic quantitative direction after same-duty correspondence
    #: ("" when no quantity applies): EQUIVALENT | MORE_RESTRICTIVE |
    #: LESS_RESTRICTIVE | INCOMPARABLE
    quantity_direction: str = ""

    @property
    def verified_support(self) -> bool:
        """At least one candidate citation that actually resolved AND is
        operative and current — a copied traceability row or a stale revision
        is not support (lesson L18)."""
        demoted = (
            set(self.unverified_citations)
            | set(self.non_operative_citations)
            | set(self.stale_citations)
        )
        return bool(set(self.candidate_slice_ids) - demoted)


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
    #: separated per-duty outcomes (Phase 9): one tag per duty from
    #: ALIGNED | PARTIAL | MISALIGNED | STRICTER | EVIDENCE_ONLY | CONFLICT,
    #: plus the judgment-level conflict/boundary flags. Documentary verdicts
    #: remain the P1 contract's dimensions; this is the finer duty grain.
    outcomes: dict[str, Any] = field(default_factory=dict)


# ── packet ──────────────────────────────────────────────────────────────────


def build_reading_packet(request: AssessmentRequest, *, repository: Any = None) -> dict[str, Any]:
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
        s for s in (governing.source_slices if governing else []) if s.role == "governing"
    ]
    ref_slices = [
        s for s in (governing.source_slices if governing else []) if s.role == "reference"
    ]
    all_governing_slices = governing.source_slices if governing else []
    measure_slices = [s for s in all_governing_slices if s.role == "measure"]
    tb_slices = [s for s in all_governing_slices if s.role == "technical_basis"]

    def _context_block(slices_, role_label, note):
        return [
            {
                "slice_id": s.slice_id,
                "ref": s.ref,
                "role": role_label,
                "locator": s.locator,
                "text": s.text,
                "note": note,
            }
            for s in slices_
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
            # Measures: evidence expectations from the source's own Measures
            # column / M-lead-in. Never an additional unstated duty, and never
            # selectable as duty evidence.
            "measures": _context_block(
                measure_slices,
                "MEASURE",
                "evidence expectation from the source; not an additional duty and "
                "not selectable as duty evidence",
            ),
            # Technical Basis: the source's own interpretive context. Binding
            # text lives in part_text/lead_in only.
            "technical_basis": _context_block(
                tb_slices,
                "TECHNICAL_BASIS",
                "interpretive context from the source's Guidelines and Technical "
                "Basis; not binding text and not selectable as duty evidence",
            ),
            "applicable_systems": governing.applicable_systems if governing else "",
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
    if governing is not None and governing.readiness and not governing.readiness.get("ready", True):
        packet["governing"]["readiness"] = governing.readiness
    if ref_slices:
        packet["governing"]["reference_texts"] = [
            {"ref": s.ref, "text": s.text} for s in ref_slices
        ]
    # Phase 8 candidate closure: source functions, revision ids, mapping
    # metadata, sibling closure, and the declared corpus boundary ride in the
    # packet so a copied traceability row can never present itself to the
    # reader as operative implementation. Without a repository the packet is
    # served unenriched and says so — never silently.
    if repository is not None:
        from portal.modules.compliance.core.candidate_closure import enrich_reading_packet

        enrich_reading_packet(
            repository,
            packet,
            requirement_id=request.requirement_id,
            corpus_dir=str(request.metadata.get("corpus_dir", "") or ""),
        )
    else:
        packet["candidate_closure"] = "not enriched — no canonical repository on the context"
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


def _unverified_operands(duty: DutyFinding, index: dict[str, SourceSlice]) -> list[str]:
    """Quantity claims, checked against the text of the ids the duty itself cites."""
    sides = (
        ("governing", duty.governing_operand, duty.governing_slice_ids),
        ("candidate", duty.candidate_operand, duty.candidate_slice_ids),
    )
    notes = []
    for label, operand, ids in sides:
        if not operand:
            continue
        texts = [index[x].text for x in ids if x in index]
        if not _operand_is_in_source(operand, texts):
            notes.append(f"{label} operand not in source: {operand!r}")
    return notes


def _quantity_from_operand(operand: str) -> tuple[int, str, str | None] | None:
    """(value, unit, qualifier) from an operand phrase, or None. Deliberately
    narrow: the full phrase must carry the literal 'N <unit>' — a spliced or
    unitless operand never yields a quantity (lesson L16)."""
    m = re.search(
        r"(?<![\d.])(\d+)(?![\d.])\)?\s+(?:(calendar|business)\s+)?(hour|day|week|month|year)s?\b",
        operand or "",
        re.I,
    )
    if not m:
        return None
    qualifier = m.group(2).lower() if m.group(2) else None
    return int(m.group(1)), m.group(3).lower().rstrip("s"), qualifier


#: DELETED in BILATERAL_CORPUS_V1 P6.4, with its cause rather than repaired.
#:
#: ``_quantity_direction`` chose its comparator with
#: ``"max_interval" if "every" in duty.governing_operand.lower() else
#: "min_retention"``. A duty phrased "within 35 calendar days" contains no
#: "every", so it was compared as a RETENTION minimum: a 40-day operator
#: interval — a four-working-week shortfall against a 35-day obligation — came
#: out MORE_RESTRICTIVE, which the outcome map turned into STRICTER and then
#: into "unused flexibility". The system reported a shortfall as generosity.
#:
#: This is not a comparator bug to patch. Deciding, from the shape of a phrase,
#: which direction "more" points in, is the prescriptive move §0 names: the
#: standard declines to say whether its interval is a ceiling or a floor in
#: terms a regex can read, and inventing the answer is how the reading came to
#: contradict the text. The comparison is read now, by a model that has the
#: requirement, its Technical Basis and the operator's own words in front of it,
#: and that says in prose which way the difference runs and why.
#:
#: ``DutyFinding.quantity_direction`` stays on the dataclass, permanently empty,
#: because the deprecated outcome map still reads it. Empty means ALIGNED there
#: — the honest default when nothing computed a direction.
_QUANTITY_DIRECTION_DELETED = (
    "BILATERAL_CORPUS_V1 P6.4: the quantity comparator was deleted with its cause. "
    "Direction between a regulatory interval and an operator interval is read, not computed."
)


def _verify_duties(
    obj: dict[str, Any],
    index: dict[str, SourceSlice],
    *,
    candidate_functions: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[DutyFinding], list[ExplanationUncertainty]]:
    """Resolve each duty's citations and quantity claims against the pinned sources."""
    duties: list[DutyFinding] = []
    uncertainties: list[ExplanationUncertainty] = []
    candidate_functions = candidate_functions or {}

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
        # Measures / Technical Basis / references ride in the packet as
        # context, never as duty evidence (foundation §3.2 source roles). A
        # citation that resolves to a context slice is recorded and demoted.
        context_cited = [
            x
            for x in gov_ids
            if x in index and index[x].role not in ("governing", "candidate", "proposed")
        ]

        duty = DutyFinding(
            duty_id=str(raw_duty.get("duty_id") or f"d{i}"),
            statement=str(raw_duty.get("statement") or ""),
            finding=finding,
            governing_slice_ids=gov_ids,
            candidate_slice_ids=cand_ids,
            governing_operand=str(raw_duty.get("governing_operand") or ""),
            candidate_operand=str(raw_duty.get("candidate_operand") or ""),
            rationale=str(raw_duty.get("rationale") or ""),
            unverified_citations=unresolved + context_cited,
        )

        # Phase 9: a candidate slice whose packet source function is
        # non-operative (copied traceability row, ToC, control page,
        # commentary, evidence artifact) is demoted — citing it cannot make
        # a duty covered.
        for cid in cand_ids:
            fn = candidate_functions.get(cid)
            if fn and not fn.get("operative", True):
                duty.non_operative_citations.append(cid)
                uncertainties.append(
                    ExplanationUncertainty(
                        reason=(
                            f"duty {duty.duty_id} cites {cid!r}, whose source function is "
                            f"{fn.get('source_function') or 'unclassified'} — not operative "
                            "implementation"
                        ),
                        source_slice_ids=[cid],
                        code="READING_NON_OPERATIVE_CITED_AS_IMPLEMENTATION",
                    )
                )
            elif fn and fn.get("revision_current") is False:
                duty.stale_citations.append(cid)
                uncertainties.append(
                    ExplanationUncertainty(
                        reason=(
                            f"duty {duty.duty_id} cites {cid!r} from a superseded internal "
                            "revision — it cannot answer the current question"
                        ),
                        source_slice_ids=[cid],
                        code="READING_STALE_REVISION_CITED",
                    )
                )

        duty.unverified_operands.extend(_unverified_operands(duty, index))

        for ref in unresolved:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=f"duty {duty.duty_id} cites {ref!r}, which is not in the packet",
                    code="READING_CITATION_UNVERIFIED",
                )
            )
        for ref in context_cited:
            uncertainties.append(
                ExplanationUncertainty(
                    reason=(
                        f"duty {duty.duty_id} cites {ref!r}, which is a context slice "
                        f"({index[ref].role}), not duty evidence"
                    ),
                    source_slice_ids=[ref],
                    code="READING_CONTEXT_CITED_AS_DUTY",
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
    *,
    packet: dict[str, Any] | None = None,
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

    candidate_functions = {
        str(c.get("candidate_id")): c
        for c in ((packet or {}).get("candidates") or [])
        if isinstance(c, dict)
    }
    duties, uncertainties = _verify_duties(obj, index, candidate_functions=candidate_functions)
    # No computed quantity direction — see _QUANTITY_DIRECTION_DELETED.

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
            governing_slice_ids=[
                x for x in d.governing_slice_ids if x in index and index[x].role == "governing"
            ],
            internal_slice_ids=[x for x in d.candidate_slice_ids if x in index],
        )
        for d in duties
        if d.finding in ("COVERED", "PARTIAL") and d.verified_support
    ]

    gaps, gap_notes = _verify_gaps(obj, index, duties)
    uncertainties.extend(gap_notes)
    uncertainties.extend(_carried_uncertainties(obj, index))

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
    judgment = ReadingJudgment(
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
    judgment.outcomes = _duty_outcomes(judgment)
    return judgment


def _verify_gaps(
    obj: dict[str, Any], index: dict[str, SourceSlice], duties: list[DutyFinding]
) -> tuple[list[GroundedGap], list[ExplanationUncertainty]]:
    """Resolve each gap's citations. An unverified id is dropped, never the gap."""
    gaps: list[GroundedGap] = []
    notes: list[ExplanationUncertainty] = []
    by_duty = {d.duty_id: d for d in duties}

    for i, raw_gap in enumerate(obj.get("gaps") or [], start=1):
        kind = str(raw_gap.get("kind") or "").upper()
        if kind not in _GAP_KINDS:
            notes.append(
                ExplanationUncertainty(
                    reason=f"gap {i} has an unknown kind {kind!r}; gap dropped",
                    code="READING_GAP_INVALID",
                )
            )
            continue
        counter = [str(x) for x in (raw_gap.get("internal_counterevidence_slice_ids") or [])]
        gov = [str(x) for x in (raw_gap.get("governing_slice_ids") or [])]
        for ref in [x for x in counter + gov if x not in index]:
            notes.append(
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
            notes.append(
                ExplanationUncertainty(
                    reason=(
                        f"gap {i} is raised against duty {duty.duty_id}, which the reading "
                        "marked COVERED"
                    ),
                    code="READING_GAP_INCONSISTENT",
                )
            )
    return gaps, notes


def _carried_uncertainties(
    obj: dict[str, Any], index: dict[str, SourceSlice]
) -> list[ExplanationUncertainty]:
    """The reading's own uncertainties, with unresolvable source ids dropped."""
    return [
        ExplanationUncertainty(
            reason=str(raw.get("reason") or ""),
            source_slice_ids=[
                str(x) for x in (raw.get("source_slice_ids") or []) if str(x) in index
            ],
            code=str(raw.get("code") or "READING_UNCERTAINTY"),
        )
        for raw in obj.get("uncertainties") or []
    ]


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
    packet = build_reading_packet(request, repository=getattr(context, "repository", None))
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

    judgment = verify_judgment(obj, request, packet=packet)
    judgment.raw = {"request": packet, "response": obj}
    return judgment


def _duty_outcomes(judgment: ReadingJudgment) -> dict[str, Any]:
    """Separate aligned / partial / misaligned / stricter / conflict /
    evidence-only per duty (slice §6: outcomes are separated, not averaged).
    STRICTER is a distinct satisfied outcome — more restrictive than required,
    with the unused flexibility noted, never a gap."""
    conflict_gaps = {g.gap_id for g in judgment.gaps if g.kind == "CONTRADICTION"}
    per_duty: list[dict[str, Any]] = []
    for duty in judgment.duties:
        if duty.finding in ("COVERED", "PARTIAL") and not duty.verified_support:
            # the finding rests entirely on demoted citations (copied rows,
            # context slices, stale revisions) — it is not established
            outcome = "EVIDENCE_ONLY"
        elif duty.finding == "COVERED":
            if duty.quantity_direction == "MORE_RESTRICTIVE":
                outcome = "STRICTER"
            elif duty.quantity_direction == "LESS_RESTRICTIVE":
                outcome = "PARTIAL"
            else:
                outcome = "ALIGNED"
        elif duty.finding == "PARTIAL":
            outcome = "PARTIAL"
        elif not duty.verified_support and duty.non_operative_citations:
            # nothing operative supports it; only copied/context material was cited
            outcome = "EVIDENCE_ONLY"
        else:
            outcome = "MISALIGNED"
        per_duty.append(
            {
                "duty_id": duty.duty_id,
                "outcome": outcome,
                "quantity_direction": duty.quantity_direction,
            }
        )
    return {
        "duties": per_duty,
        "conflict": bool(conflict_gaps),
        "conflict_gap_ids": sorted(conflict_gaps),
        "unused_flexibility": [d["duty_id"] for d in per_duty if d["outcome"] == "STRICTER"],
    }


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
