"""P6.6 / Q12 — scenarios over one pinned snapshot.

Hermetic: injected ``seat_fn`` and a pre-built ``AssessmentRequest``; no
network, no real Ollama. Before and after share the same pinned snapshot and
differ only by the materialised overlay.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.cip_register import Register, RegisterNode
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
from portal.modules.compliance.core.scenarios import evaluate_scenario, new_scenario

_SCOPE = AssetScope(impact_present={"high"}, declared_by="op", declared_at="2026-01-01")
_SEATS = [{"id": f"s{i}", "label": str(i), "model": f"m{i}"} for i in range(3)]

WEAK = "The Responsible Entity shall evaluate patches within 40 calendar days."
STRONG = "The Responsible Entity shall evaluate patches within 35 calendar days."


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _node(**kw) -> RegisterNode:
    base = {
        "id": "TEST-1 R1 Part 1.1",
        "standard": "TEST-1",
        "version": "1",
        "requirement": "R1",
        "part": "1.1",
        "verbatim_text": "Do the thing.",
        "measure_text": "",
        "applicable_systems": "High Impact BES Cyber Systems",
        "table_name": "",
        "vrf": "",
        "time_horizon": "",
        "lifecycle_state": "EFFECTIVE",
        "valid_from": "2020-01-01",
        "valid_to": None,
        "supersedes": None,
        "superseded_by": None,
        "authority_tier": 0,
        "source_pdf": "",
        "source_pages": [],
        "recorded_at": 0.0,
        "granularity": "part",
    }
    base.update(kw)
    return RegisterNode(**base)


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


def _request(text: str = WEAK) -> AssessmentRequest:
    return AssessmentRequest(
        requirement_id="TEST-1 R1 Part 1.1",
        scope=_SCOPE,
        governing=GoverningBundle(
            ref="TEST-1 R1 Part 1.1",
            part_text="Each entity shall evaluate patches.",
            lead_in="Each entity shall implement each of the following Parts:",
            source_slices=[
                SourceSlice(
                    slice_id="gov-1",
                    ref="register:test",
                    document_id="register",
                    revision_hash="h",
                    chunk_id="reg",
                    text="Evaluate patches at least once every 35 calendar days.",
                    role="governing",
                )
            ],
            fingerprint="govfp",
            meta=[{"applicable_systems": "High Impact BES Cyber Systems"}],
        ),
        snapshot=CorpusSnapshot(
            snapshot_id="snap", kb_id="kb", completeness="COMPLETE", fingerprint="snapfp"
        ),
        candidate_set=CandidateSet(records=[_candidate("c1", text)]),
    )


def _staged_seat() -> Any:
    def fn(model: str, system: str, user: str) -> str:
        if json.loads(user).get("task") == "clause_alignment":
            packet = json.loads(user)
            gid = packet["governing"]["selectable_slice_ids"][0]
            records = []
            for cand in packet["candidates"]:
                weak = "40 calendar days" in cand["text"]
                records.append(
                    {
                        "candidate_id": cand["candidate_id"],
                        "relation": "SAME",
                        "governing_slice_ids": [gid],
                        "candidate_slice_ids": cand["selectable_slice_ids"][:1],
                        "population_overlap": "OVERLAPPING",
                        "source_function": "OPERATIVE_COMMITMENT",
                        "activity": "weak" if weak else "evaluate patches",
                        "object": "patches",
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
        raise AssertionError(system[:60])

    return fn


def _context() -> AssessmentContext:
    return AssessmentContext(seats=_SEATS, quorum=0.66, seat_fn=_staged_seat(), kb_id="kb")


def test_scenario_not_found_target_is_a_clear_error():
    reg = Register(nodes=[_node()])
    scenario = new_scenario("MISSING", "patch text", "because")
    result = evaluate_scenario(scenario, reg, _SCOPE, "2026-09-05", lambda n, side: [])
    assert "error" in result


def test_scenario_replacement_closes_gap_over_one_pinned_snapshot():
    reg = Register(nodes=[_node()])
    request = _request(WEAK)
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="proc",
        chunk_id="ch-c1",
        char_start=0,
        char_end=len(WEAK),
        expected_old_hash=_sha(WEAK),
        new_text=STRONG,
    )
    scenario = new_scenario(
        "TEST-1 R1 Part 1.1",
        STRONG,
        "close the cadence gap",
        overlay=ScenarioOverlay(base_snapshot_fingerprint="snapfp", edits=[edit]),
    )
    result = evaluate_scenario(
        scenario, reg, _SCOPE, "2026-09-05", None, context=_context(), request=request
    )
    assert result["coverage_before"] == "PARTIAL"
    assert result["coverage_after"] == "FULL"
    assert result["determination_changed"] is True
    assert result["weakening"] is False
    # before and after are distinct assessments over one shared base snapshot
    assert result["snapshot_fingerprint"] == "snapfp"
    assert result["virtual_fingerprint"] != result["snapshot_fingerprint"]
    assert result["before_assessment_id"] != result["after_assessment_id"]
    assert result["temporal_label"] == "current"


def test_scenario_bare_patch_is_additive_not_a_replacement():
    """A bare legacy patch is an explicitly additive scenario: the weak rule is
    still present, so the virtual state does not become FULL."""
    reg = Register(nodes=[_node()])
    scenario = new_scenario("TEST-1 R1 Part 1.1", "We now do the thing well.", "additive")
    result = evaluate_scenario(
        scenario, reg, _SCOPE, "2026-09-05", None, context=_context(), request=_request(WEAK)
    )
    assert result["coverage_after"] != "FULL"
    assert result["note"], result["note"]


def test_new_scenario_generates_a_stable_id():
    s1 = new_scenario("X", "patch", "reason")
    s2 = new_scenario("X", "patch", "reason")
    assert s1.scenario_id != s2.scenario_id
    assert len(s1.scenario_id) == 12
