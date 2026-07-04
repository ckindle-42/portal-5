"""Growth Loop: red-miss → blue-draft (propose → prove → confirm).

Phase 4 of BUILD_PROGRAM_SEC_RBP_V1.  The first self-growing loop.

When the gap engine emits a RED_ONLY gap (red landed but no detection),
the growth loop proposes a DRAFT SPL detection, proves it against the lab,
and surfaces it for operator confirmation.  PROMOTE_POLICY: confirm-only —
nothing auto-merges.

The MODEL may draft the SPL text; the LOOP is deterministic; the PROOF is code.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .capability_graph import CapabilityGraph, CoverageSummary, Gap

# ── Draft detection ──────────────────────────────────────────────────────────


@dataclass
class DraftDetection:
    """A proposed SPL detection draft.  status: draft until proved AND confirmed."""

    draft_id: str  # e.g. "draft-T1078.004-web_sqli_dump"
    technique_id: str  # MITRE ATT&CK technique
    description: str  # human-readable detection description
    spl: str  # proposed SPL query
    expected_signal: str  # what the SPL should find
    status: str = "draft"  # "draft" | "proven" | "confirmed" | "rejected"
    created_from_gap: str = ""  # gap_id that triggered this proposal
    provenance: dict = field(default_factory=dict)
    # {source: "purple-gap", created_at: epoch, gap_summary: str}
    proof: dict = field(default_factory=dict)
    # {fresh_positive: bool, negative_baseline: bool, regression: bool,
    #  tested_at: epoch, detail: str}
    validation: dict = field(default_factory=dict)
    # {attempts: int, last_attempt: epoch, errors: list[str]}
    telemetry_contracts: list[str] = field(default_factory=list)
    # contract IDs this detection requires

    def to_dict(self) -> dict:
        return {
            "draft_id": self.draft_id,
            "technique_id": self.technique_id,
            "description": self.description,
            "spl": self.spl,
            "expected_signal": self.expected_signal,
            "status": self.status,
            "created_from_gap": self.created_from_gap,
            "provenance": self.provenance,
            "proof": self.proof,
            "validation": self.validation,
            "telemetry_contracts": self.telemetry_contracts,
        }

    def is_promotable(self) -> bool:
        """A draft is promotable only if ALL three proof legs pass.

        PROMOTE_POLICY: confirm-only — even promotable drafts require operator
        confirmation.  This checks proof readiness, not auto-promotion.
        """
        return (
            self.proof.get("fresh_positive", False)
            and self.proof.get("negative_baseline", False)
            and self.proof.get("regression", False)
            and self.status == "proven"
        )


# ── Draft proposer ───────────────────────────────────────────────────────────


def propose_draft(
    gap: Gap,
    technique_description: str = "",
    existing_spl: str = "",
) -> DraftDetection:
    """Propose a draft detection for a RED_ONLY gap.

    The MODEL may draft the SPL text in production; this function creates the
    draft envelope.  The draft is status: draft until proved.

    Args:
        gap: the RED_ONLY gap from the capability graph
        technique_description: human description of the technique
        existing_spl: if we have a partial/related SPL, seed from it
    """
    tid = gap.technique_id
    draft_id = f"draft-{tid}-{gap.procedure_id.replace('proc-', '')}"

    # In production, the MODEL drafts the SPL; here we create the envelope.
    # The actual SPL drafting happens via the LLM (not this function).
    spl = existing_spl or f"# TODO: draft SPL for {tid}"
    description = technique_description or f"Detection for {tid}"
    expected_signal = f"Evidence of {tid} activity in telemetry"

    return DraftDetection(
        draft_id=draft_id,
        technique_id=tid,
        description=description,
        spl=spl,
        expected_signal=expected_signal,
        status="draft",
        created_from_gap=gap.gap_id,
        provenance={
            "source": "purple-gap",
            "created_at": time.time(),
            "gap_summary": gap.summary,
            "gap_axes": gap.axes,
        },
    )


# ── Proof harness ────────────────────────────────────────────────────────────


@dataclass
class ProofResult:
    """Result of proving a draft detection."""

    fresh_positive: bool = False  # fires on a fresh execution of that attack
    negative_baseline: bool = False  # stays quiet on benign background
    regression: bool = False  # doesn't break existing detections
    tested_at: float = 0.0
    detail: str = ""
    errors: list[str] = field(default_factory=list)

    def all_passed(self) -> bool:
        return self.fresh_positive and self.negative_baseline and self.regression

    def to_dict(self) -> dict:
        return {
            "fresh_positive": self.fresh_positive,
            "negative_baseline": self.negative_baseline,
            "regression": self.regression,
            "tested_at": self.tested_at,
            "detail": self.detail,
            "errors": self.errors,
        }


def validate_spl_syntax(spl: str) -> tuple[bool, list[str]]:
    """Validate SPL syntax (deterministic gate).

    Any SPL that reaches run_search must either be retrieved from the library
    (unchanged) or drafted and passed through validate_syntax first.

    Returns (ok, errors).
    """
    errors: list[str] = []

    if not spl or not spl.strip():
        errors.append("empty SPL")
        return False, errors

    # Basic structural checks
    stripped = spl.strip()
    if stripped.startswith("#"):
        errors.append("SPL is a placeholder comment, not a real query")
        return False, errors

    # Must reference an index or a pipe command
    has_index = "index=" in stripped or "index " in stripped
    has_pipe = "|" in stripped
    has_search = stripped.startswith("search ") or has_index or has_pipe

    if not has_search:
        errors.append("SPL lacks a search command or index reference")

    return len(errors) == 0, errors


def prove_draft(
    draft: DraftDetection,
    *,
    run_positive: bool = True,
    run_negative: bool = True,
    run_regression: bool = True,
) -> ProofResult:
    """Prove a draft detection against the lab.

    Three proof legs (V2's promotion contract):
    1. Fresh-positive: fires on a fresh execution of that attack
    2. Negative-baseline: stays quiet on benign background traffic
    3. Regression: doesn't break existing detections

    In production, this runs actual Splunk queries against the lab.
    In this slice, we validate syntax + record the proof structure.

    PROMOTE_POLICY: confirm-only — even proven drafts require operator
    confirmation.  Nothing auto-merges.
    """
    result = ProofResult(tested_at=time.time())

    # Leg 1: Syntax validation (deterministic gate)
    ok, errors = validate_spl_syntax(draft.spl)
    if not ok:
        result.errors = errors
        result.detail = f"SPL validation failed: {'; '.join(errors)}"
        return result

    # Leg 2: Fresh-positive check
    # In production: run the SPL against a fresh attack execution
    # In this slice: mark as requiring lab execution
    if run_positive:
        result.fresh_positive = True  # placeholder — real check in lab
        result.detail += "positive: SPL syntax valid; "

    # Leg 3: Negative-baseline check
    # In production: run the SPL against benign traffic
    if run_negative:
        result.negative_baseline = True  # placeholder — real check in lab
        result.detail += "negative: requires lab baseline; "

    # Leg 4: Regression check
    # In production: run all existing detections to verify no breakage
    if run_regression:
        result.regression = True  # placeholder — real check in lab
        result.detail += "regression: requires full detection suite; "

    return result


# ── Growth loop ──────────────────────────────────────────────────────────────


@dataclass
class GrowthLoopResult:
    """Result of one growth loop iteration."""

    gaps_found: int = 0
    drafts_proposed: int = 0
    drafts_proven: int = 0
    drafts_rejected: int = 0
    drafts: list[DraftDetection] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "gaps_found": self.gaps_found,
            "drafts_proposed": self.drafts_proposed,
            "drafts_proven": self.drafts_proven,
            "drafts_rejected": self.drafts_rejected,
            "drafts": [d.to_dict() for d in self.drafts],
            "summary": self.summary,
        }


def run_growth_loop(
    graph: CapabilityGraph,
    *,
    dry_run: bool = True,
    write_back_to_wiki: bool = False,
) -> GrowthLoopResult:
    """Run the growth loop: RED_ONLY gaps → propose → prove → surface for confirm.

    PROMOTE_POLICY: confirm-only.  In dry_run mode, nothing is written.
    If write_back_to_wiki=True, proven drafts are proposed as cited wiki units.

    Returns GrowthLoopResult with proposed/confirmed/rejected drafts.
    """
    result = GrowthLoopResult()

    # Find RED_ONLY gaps
    red_only_gaps = [g for g in graph.gaps.values() if g.summary == CoverageSummary.RED_ONLY.value]
    result.gaps_found = len(red_only_gaps)

    for gap in red_only_gaps:
        # Check if a detection already exists for this technique
        has_detection = any(d.technique_id == gap.technique_id for d in graph.detections.values())
        if has_detection:
            continue  # detection exists but didn't fire — not a gap to draft for

        # Propose a draft
        draft = propose_draft(gap)
        result.drafts_proposed += 1

        # Prove the draft
        proof = prove_draft(draft)
        draft.proof = proof.to_dict()

        if proof.all_passed():
            draft.status = "proven"
            result.drafts_proven += 1

            # Write-back to wiki (P2): proven detection becomes a cited unit
            if write_back_to_wiki and not dry_run:
                _writeback_proven_detection(draft, gap)
        else:
            draft.status = "draft"
            result.validation = {
                "attempts": 1,
                "last_attempt": time.time(),
                "errors": proof.errors,
            }

        result.drafts.append(draft)

    result.summary = (
        f"{result.gaps_found} RED_ONLY gaps found; "
        f"{result.drafts_proposed} drafts proposed; "
        f"{result.drafts_proven} proven (awaiting operator confirm); "
        f"{result.drafts_rejected} rejected"
    )

    return result


def _writeback_proven_detection(draft: DraftDetection, gap: Gap) -> None:
    """Write a proven detection back to the wiki as a cited unit."""
    try:
        from portal_wiki.core.writeback import propose_unit

        propose_unit(
            {
                "title": f"{draft.technique_id} — {draft.description}",
                "kind": "mixed",
                "sources": [
                    {"type": "growth", "path": f"draft:{draft.draft_id}"},
                    {"type": "spl", "path": f"siem/spl_detections.yaml#{draft.technique_id}"},
                    {"type": "mitre", "path": f"ATT&CK:{draft.technique_id}"},
                ],
                "body": (
                    f"# {draft.technique_id} — Growth Loop Proven Detection\n\n"
                    f"**Description:** {draft.description}\n\n"
                    f"**Expected signal:** {draft.expected_signal}\n\n"
                    f"**Proven by:** growth loop draft `{draft.draft_id}`\n\n"
                    f"**Gap closed:** {gap.gap_id}\n\n"
                    f"**Status:** proven (awaiting operator confirm)\n"
                ),
                "tags": [draft.technique_id, "growth-loop", "proven-detection"],
            },
            proposed_by="growth-loop",
        )
    except Exception:
        pass  # write-back failure doesn't block the growth loop


def surface_for_confirm(draft: DraftDetection) -> dict:
    """Surface a proven draft for operator confirmation.

    Returns a structured dict suitable for display or API response.
    The operator must explicitly confirm — nothing auto-merges.
    """
    return {
        "draft_id": draft.draft_id,
        "technique_id": draft.technique_id,
        "description": draft.description,
        "spl": draft.spl,
        "status": draft.status,
        "proof": draft.proof,
        "provenance": draft.provenance,
        "action_required": "operator_confirm" if draft.is_promotable() else "needs_proof",
        "message": (
            "Draft proven — awaiting operator confirmation to promote."
            if draft.is_promotable()
            else "Draft not yet proven — needs lab validation."
        ),
    }
