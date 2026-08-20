"""W.2 -- the run feeds the scoreboard its real inputs
(TASK_BULLY_SCOREBOARD_CONFORMANCE_V1).

Seeded proof that `store.scoreboard_records_for_hunt` + `scoreboard.update`
make `trust_class=CONFIRMED_CORRECT` (via a PROMOTED candidate) and
`false_flag=True` (via a known_benign subject) REACHABLE -- both were
structurally unreachable under `bully_loop_milestone_run.py`'s prior
hardcoded `candidate_state=None, known_benign=False`."""

from __future__ import annotations

import pathlib

import pytest

from portal.modules.security.core.bully import contracts
from portal.modules.security.core.bully import scoreboard as scoreboard_mod
from portal.modules.security.core.bully.contracts import Decomposition
from portal.modules.security.core.bully.store import Store


@pytest.fixture
def store(tmp_path: pathlib.Path) -> Store:
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


class _Sig:
    def __init__(self, signature_id: str) -> None:
        self.signature_id = signature_id
        self.episode_ref = f"ep-{signature_id}"
        self.signature_algorithm_version = "v1"
        self.input_manifest_hash = f"hash-{signature_id}"
        self.canonical_fingerprint = "fp"
        self.action_sequence: list[str] = []
        self.event_graph: dict = {}
        self.parameter_families: dict = {}
        self.context_topology: dict = {}
        self.artifacts: dict = {}
        self.attack_mappings: list = []
        self.telemetry_shape: dict = {}
        self.detector_outcomes: dict = {}
        self.evidence_manifest_id = None
        self.completeness = 1.0
        self.created_at = 0.0


def _make_hunt(store: Store, hunt_id: str = "hunt-w2") -> None:
    store.hunt_create(
        hunt_id=hunt_id,
        objective="W.2 conformance seed",
        neighborhood_scope="lab-default",
        authorization_ref="operator:test",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )


def _make_assessment(
    store: Store,
    *,
    assessment_id: str,
    signature_id: str,
    relationship: str,
    reference_signature_id: str | None = None,
) -> None:
    store.record_signature(_Sig(signature_id))
    store.record_cousin(
        contracts.CousinAssessment(
            assessment_id=assessment_id,
            subject_signature_id=signature_id,
            reference_signature_id=reference_signature_id,
            candidate_set_id="cs-1",
            decomposition=Decomposition(
                behavior=0.5, telemetry=0.1, semantic=0.1, attack=0.1, context=0.1
            ),
            composite=0.5,
            relationship=relationship,
            nonsemantic_channels=1,
            vetoes=[],
            defense_response="MISSED",
            nearest_knowns=[],
            confidence=0.9,
            completeness=1.0,
            algorithm_version="v1",
            thresholds_version="v1",
        )
    )


def _record_grade_decision(store: Store, hunt_id: str, assessment_id: str) -> None:
    from portal.modules.security.core.bully.contracts import DecisionEvent, new_id

    store.record_decision(
        DecisionEvent(
            event_id=new_id("dec"),
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:test",
            kind="grade",
            subject_id=assessment_id,
            rationale="seed",
            data={},
            recorded_at=0.0,
        )
    )


def test_promoted_candidate_reaches_confirmed_correct(store: Store):
    hunt_id = "hunt-w2-promoted"
    _make_hunt(store, hunt_id)
    _make_assessment(
        store,
        assessment_id="assess-promoted",
        signature_id="sig-promoted",
        relationship="ANOMALOUS_UNCLASSIFIED",
    )
    _record_grade_decision(store, hunt_id, "assess-promoted")

    manifest_id = "em-w2-observed"
    store.evidence_manifest_put(
        manifest_id=manifest_id,
        episode_id="ep-w2",
        required_types=["packet"],
        items=[
            {
                "evidence_id": f"{manifest_id}-item",
                "type": "packet",
                "uri": "capture://x",
                "content_hash": "abc123",
                "synthetic": False,
                "origin": "observed_packet",
            }
        ],
        completeness=1.0,
        reasons=[],
    )
    store.candidate_create(
        candidate_id="cand-promoted",
        hunt_id=hunt_id,
        assessment_id="assess-promoted",
        evidence_manifest_id=manifest_id,
        gate_policy_version="bin-gates-v1",
    )
    # Satisfy the PROMOTED trigger's gate-chain requirement (all seven gates
    # passing at the candidate's current alert_version) -- this test's
    # interest is scoreboard_records_for_hunt reading real candidate_state,
    # not the BIN gate machinery itself (covered elsewhere, e.g. C7).
    for i, gate in enumerate(("G-1", "G0", "G1a", "G1b", "G2", "G5", "G3")):
        store.gate_result_put(
            result_id=f"gr-w2-{i}",
            candidate_id="cand-promoted",
            alert_version=1,
            gate_id=gate,
            attempt=1,
            outcome="pass",
            validator_version="v1",
            inputs={},
            evidence={},
            checks=[],
            reasons=[],
        )
    store._conn.execute(
        "UPDATE candidates SET current_state='AWAITING_OPERATOR' WHERE candidate_id='cand-promoted'"
    )
    store._conn.execute(
        "UPDATE candidates SET current_state='PROMOTED' WHERE candidate_id='cand-promoted'"
    )
    store._conn.commit()

    records = store.scoreboard_records_for_hunt(hunt_id)
    assert records, "expected the graded assessment to be assembled"
    assert records[0]["candidate_state"] == "PROMOTED"

    result = scoreboard_mod.update(hunt_id, records)
    scored = result["records"][0]
    assert scored["trust_class"] == scoreboard_mod.CONFIRMED_CORRECT
    assert result["trust_mean_rank"] is not None


def test_known_benign_subject_reaches_false_flag(store: Store):
    hunt_id = "hunt-w2-benign"
    _make_hunt(store, hunt_id)
    _make_assessment(
        store,
        assessment_id="assess-benign",
        signature_id="sig-benign",
        relationship="ANOMALOUS_UNCLASSIFIED",
    )
    _record_grade_decision(store, hunt_id, "assess-benign")
    store.update_known_state(
        "sig-benign", "known_benign", {"note": "confirmed benign by operator"}, hunt_id=hunt_id
    )

    records = store.scoreboard_records_for_hunt(hunt_id)
    assert records[0]["known_benign"] is True

    result = scoreboard_mod.update(hunt_id, records)
    scored = result["records"][0]
    assert scored["false_flag"] is True
    assert result["false_flag_count"] == 1


def test_hardcoded_nulls_make_both_outcomes_unreachable():
    """The seeded contrast: the OLD call site's literal inputs
    (`candidate_state=None, known_benign=False`) can never produce either
    outcome above, no matter what the assessment looks like -- proving the
    hardcoded nulls, not the scorer, were the defect."""
    hardcoded = {
        "assessment_id": "x",
        "relationship": "ANOMALOUS_UNCLASSIFIED",
        "defense_response": "NOT_COVERED",
        "composite": 0.9,
        "candidate_state": None,
        "known_benign": False,
    }
    scored = scoreboard_mod.score_record(hardcoded)
    assert scored["trust_class"] != scoreboard_mod.CONFIRMED_CORRECT
    assert scored["false_flag"] is False
