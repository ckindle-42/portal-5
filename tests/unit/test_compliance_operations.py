"""P6 the six operations — typed contracts, thin judge adapter, proposal re-judgment.

Hermetic: every model call is an injected ``seat_fn``; retrieval is bypassed by
injecting a pre-built :class:`AssessmentRequest`; no network or real Ollama.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.determination import (
    AssessmentContext,
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    CorpusSnapshot,
    GoverningBundle,
    ScenarioEdit,
    ScenarioOverlay,
    SourceSlice,
)
from portal.modules.compliance.core.operations import (
    diff,
    judge,
    norms,
    propose,
    resolve,
    trace,
)
from portal.modules.compliance.core.policy_graph import build_policy_graph


@pytest.fixture(scope="module")
def g():
    return build_policy_graph()


def _scope():
    return AssetScope(
        impact_present={"high", "medium"},
        associated_present={"eacms", "pacs", "pca"},
        declared_by="operator:test",
    )


_SEATS = [{"id": f"s{i}", "label": str(i), "model": f"m{i}"} for i in range(3)]

GOV_TEXT = "Each Responsible Entity shall evaluate security patches for applicability."
WEAK_TEXT = "SMEs shall evaluate patch applicability once every 40 calendar days."
STRONG_TEXT = "SMEs shall evaluate patch applicability once every 35 calendar days."


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _governing(ref: str = "CIP-007-6 R2 Part 2.2") -> GoverningBundle:
    return GoverningBundle(
        ref=ref,
        part_text=GOV_TEXT,
        lead_in="Each Responsible Entity shall implement each of the following Parts:",
        source_slices=[
            SourceSlice(
                slice_id="gov-1",
                ref=ref,
                document_id="register",
                revision_hash="h",
                chunk_id="reg-gov",
                text="Evaluate patches at least once every 35 calendar days.",
                role="governing",
            )
        ],
        fingerprint="govfp",
        meta=[{"applicable_systems": "High Impact BES Cyber Systems"}],
    )


def _candidate(cid: str, text: str) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=cid,
        document_id="proc",
        chunk_id=f"ch-{cid}",
        text=text,
        source_slice=SourceSlice(
            slice_id=f"cand-{cid}",
            ref=f"proc#{cid}",
            document_id="proc",
            revision_hash=_sha(text),
            chunk_id=f"ch-{cid}",
            text=text,
            role="candidate",
        ),
    )


def _request(text: str = STRONG_TEXT, *, fingerprint: str = "snapfp") -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2 Part 2.2",
        scope=_scope(),
        governing=_governing(),
        snapshot=CorpusSnapshot(
            snapshot_id="snap", kb_id="kb", completeness="COMPLETE", fingerprint=fingerprint
        ),
        candidate_set=CandidateSet(records=[_candidate("c1", text)]),
    )


def _staged_seat() -> Any:
    """One transport dispatching on the three stage system prompts.

    The report stage keys coverage on the operative activity the alignment stage
    set: a weaker cadence (``40``) is ``weak``. A ``prop-`` slice marks the
    virtual (after) assessment, which is used only to expose virtual identity.
    """

    def fn(model: str, system: str, user: str) -> str:
        if json.loads(user).get("task") == "clause_alignment":
            packet = json.loads(user)
            gid = packet["governing"]["selectable_slice_ids"][0]
            records = []
            for cand in packet["candidates"]:
                text = cand["text"]
                weak = "40 calendar days" in text
                records.append(
                    {
                        "candidate_id": cand["candidate_id"],
                        "relation": "SAME",
                        "governing_slice_ids": [gid],
                        "candidate_slice_ids": cand["selectable_slice_ids"][:1],
                        "population_overlap": "OVERLAPPING",
                        "source_function": "OPERATIVE_COMMITMENT",
                        "activity": "weak" if weak else "evaluate patches",
                        "object": "security patches",
                        "constraint_bindings": [],
                    }
                )
            return json.dumps({"records": records})
        if "sealed seat on a compliance review council" in system:
            weak = "40 calendar days" in user
            return json.dumps(
                {
                    "determination": "PARTIAL" if weak else "SUPPORTED",
                    "finding_type": None,
                    "cited_refs": ["c1"],
                    "confidence": 0.9,
                    "rationale": "scripted",
                }
            )
        if "You are a compliance analyst" in system:
            # The reading pass replaced the reporter: duties, not covered/gaps.
            packet = json.loads(user)
            gid = packet["governing"]["selectable_slice_ids"][0]
            cands = packet["candidates"]
            internal = next(
                (c["selectable_slice_ids"][0] for c in cands if c["selectable_slice_ids"]), ""
            )
            weak = any("40 calendar days" in c["text"] for c in cands)
            return json.dumps(
                {
                    "documentary_coverage": "PARTIAL" if weak else "FULL",
                    "duties": [
                        {
                            "duty_id": "d1",
                            "statement": "evaluate patches",
                            "finding": "PARTIAL" if weak else "COVERED",
                            "governing_slice_ids": [gid],
                            "candidate_slice_ids": [internal],
                        }
                    ],
                    "gaps": (
                        [
                            {
                                "duty_id": "d1",
                                "gap_id": "gap-cadence",
                                "kind": "WEAKER_COMMITMENT",
                                "missing_commitment": "35 calendar day cadence",
                                "governing_slice_ids": [gid],
                                "internal_counterevidence_slice_ids": [internal],
                            }
                        ]
                        if weak
                        else []
                    ),
                    "uncertainties": [],
                }
            )
        if "source-linked reporting analyst" in system:
            packet = json.loads(user)
            gid = packet["governing"]["governing_slice_ids"][0]
            internal = packet["permitted_internal_slice_ids"][0]
            weak = any(o.get("activity") == "weak" for o in packet.get("operative_commitments", []))
            covered = [
                {
                    "commitment": "evaluate patches",
                    "governing_slice_ids": [gid],
                    "internal_slice_ids": [internal],
                }
            ]
            if weak:
                return json.dumps(
                    {
                        "documentary_coverage": "PARTIAL",
                        "covered": covered,
                        "gaps": [
                            {
                                "gap_id": "gap-cadence",
                                "kind": "WEAKER_COMMITMENT",
                                "missing_commitment": "35 calendar day cadence",
                                "governing_slice_ids": [gid],
                                "internal_counterevidence_slice_ids": [internal],
                            }
                        ],
                        "uncertainties": [],
                    }
                )
            return json.dumps(
                {
                    "documentary_coverage": "FULL",
                    "covered": covered,
                    "gaps": [],
                    "uncertainties": [],
                }
            )
        if "checking one thing only" in system:
            return '{"overrides": false, "exception_ref": null}'
        raise AssertionError(f"unexpected system prompt: {system[:60]}")

    return fn


def _context() -> AssessmentContext:
    return AssessmentContext(seats=_SEATS, quorum=0.66, seat_fn=_staged_seat(), kb_id="kb")


# ── resolve / trace / diff / norms (unchanged contracts) ───────────────────


def test_resolve_current_attaches_premises_and_reference_closure(g):
    gs = resolve("CIP-007-6 R2 Part 2.2", valid_at="2026-09-06", scope=_scope(), policy_graph=g)
    assert gs.label == "current"
    assert gs.enforceable
    assert gs.actor_cus and gs.actor_cus[0]["cu"]
    assert "CIP-007-6 R2 Part 2.1" in gs.reference_closure
    assert any(p["id"] == "CIP-007-6 R2 Part 2.1" for p in gs.premises)


def test_resolve_before_effective_date_is_labelled_not_current(g):
    gs = resolve("CIP-003-9 R1", valid_at="2021-01-01", scope=_scope(), policy_graph=g)
    assert gs.label in {"future", "historical"}
    assert not gs.enforceable


def test_trace_discloses_frontier_at_budget(g):
    meta = next(n.id for n in g.nodes if n.node_type == "meta_cu")
    p = trace(meta, direction="both", depth=3, policy_graph=g, max_edges=3)
    assert p.budget_hit
    assert p.frontier
    assert set(p.frontier).isdisjoint(set(p.nodes) - set(p.frontier))


def test_diff_rows_carry_a_taxonomy_type():
    rows = diff("CIP-003-8", "CIP-003-9")
    assert rows
    assert all(r["taxonomy_type"] for r in rows)
    assert any(r["creates_review_work"] for r in rows)


def test_norms_direction_and_intent(g):
    prof = norms(
        "CIP-007-6 R2 Part 2.2",
        internal_quantities=[{"value": 21, "unit": "day"}],
        policy_graph=g,
        policy_decisions={},
    )
    assert prof.direction == "max_interval"
    assert prof.classification == "MORE_RESTRICTIVE"
    assert prof.intent["code"] == "U07_INTENT_UNKNOWN"


# ── judge: a thin adapter over the shared service ──────────────────────────


def test_judge_projects_the_shared_assessment_result():
    d = judge(
        "CIP-007-6 R2 Part 2.2",
        scope=_scope(),
        seats=_SEATS,
        request=_request(STRONG_TEXT),
        context=_context(),
    )
    assert d.determination == "SUPPORTED"
    assert d.documentary_coverage == "FULL"
    assert d.assessment_id
    assert not d.gate_gated_out
    assert d.council_votes.get("SUPPORTED") == 3
    assert d.covered and d.covered[0].internal_slice_ids


def test_judge_gates_out_of_scope_part_without_council():
    councils: list[str] = []
    staged = _staged_seat()

    def fn(model: str, system: str, user: str) -> str:
        if "sealed seat on a compliance review council" in system:
            councils.append(model)
        return staged(model, system, user)

    low_only = AssetScope(impact_present={"low"}, declared_by="operator:test")
    request = _request(STRONG_TEXT)
    request.scope = low_only
    d = judge(
        "CIP-007-6 R2 Part 2.2",
        scope=low_only,
        seats=_SEATS,
        request=request,
        context=AssessmentContext(seats=_SEATS, quorum=0.66, seat_fn=fn, kb_id="kb"),
    )
    assert d.determination == "NOT_APPLICABLE"
    assert d.gate_gated_out
    assert councils == []


# ── propose: no self-certification ─────────────────────────────────────────


def test_propose_validates_a_real_closing_overlay():
    base = _request(WEAK_TEXT)
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="proc",
        chunk_id="ch-c1",
        char_start=0,
        char_end=len(WEAK_TEXT),
        expected_old_hash=_sha(WEAK_TEXT),
        new_text=STRONG_TEXT,
    )
    overlay = ScenarioOverlay(base_snapshot_fingerprint="snapfp", edits=[edit])
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["gap-cadence"],
        "",
        overlay=overlay,
        request=base,
        context=_context(),
    )
    assert pkg.status == "VALIDATED"
    assert pkg.rejudged is not None and pkg.rejudged.documentary_coverage == "FULL"
    assert pkg.before is not None and pkg.before.documentary_coverage == "PARTIAL"
    assert pkg.closes_fields == ["gap-cadence"]
    assert pkg.virtual_fingerprint
    assert pkg.closed_gaps == ["gap-cadence"]


def test_propose_does_not_self_certify_a_governing_text_quote():
    """An additive draft that merely quotes the governing text cannot close a
    gap the still-present weaker rule keeps open: no hardcoded SUPPORTED."""
    draft = (
        "The responsible owner shall implement and retain evidence of the following "
        "requirement: evaluate patches at least once every 35 calendar days."
    )
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        ["gap-cadence"],
        draft,
        request=_request(WEAK_TEXT),
        context=_context(),
    )
    assert pkg.status == "FAILED_VALIDATION"
    assert pkg.closes_fields == []
    assert pkg.rejudged is not None and pkg.rejudged.documentary_coverage == "PARTIAL"
    assert any("does not close" in reason for reason in pkg.weakens)
    assert pkg.unclosed_gaps == ["gap-cadence"]


def test_propose_blocked_when_no_pinned_snapshot():
    base = _request(STRONG_TEXT)
    base.snapshot = None
    pkg = propose(
        "CIP-007-6 R2 Part 2.2",
        [],
        "some draft",
        request=base,
        context=_context(),
    )
    assert pkg.status == "BLOCKED_MISSING_FACT"
    assert pkg.missing_facts
    assert pkg.rejudged is None
