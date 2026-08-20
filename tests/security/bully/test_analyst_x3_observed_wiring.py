"""X.3 -- the observed lane raises concerns through the analyst loop.

`observed_mode.run_observed`'s `promote_fn`/`compound_fn` hooks were
previously unwired -- nothing ever reached a queue. `run_observed_investigation`
now defaults them to `analyst_loop.raise_concern`/`record_verdict`, gated
ONLY by `compounding.should_escalate`, when the caller supplies a `grade_fn`.
(TASK_BULLY_ANALYST_LOOP_V1 X.3)"""

from __future__ import annotations

from portal.modules.security.core.bully import analyst_loop as al
from portal.modules.security.core.bully import compounding, observed_mode
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.connectors import IterableIngestConnector
from portal.modules.security.core.bully.contracts import CousinAssessment, Decomposition
from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane
from portal.modules.security.core.bully.seed_scope import Seed


def _plane_with_seed(actions):
    plane = DataPlane()
    connector = IterableIngestConnector(
        "edr",
        [{"host": "host1", "action": a} for a in actions],
    )
    plane.connect(
        "edr",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, True)},
    )
    return plane


def _signature_fn(scope):
    actions = [
        str(r.get("action")) for r in scope.records if isinstance(r, dict) and r.get("action")
    ]
    return sig_mod.build_signature({"target_host": "host1"}, {"action_sequence": actions})


def _grade_fn(reference_signature_id: str | None):
    def grade_fn(scope, investigation):
        return CousinAssessment(
            assessment_id="as-x3",
            subject_signature_id="sig-subject",
            reference_signature_id=reference_signature_id,
            candidate_set_id="cs-1",
            decomposition=Decomposition(
                behavior=0.1, telemetry=0.1, semantic=0.1, attack=0.1, context=0.1
            ),
            composite=0.1,
            relationship="SAME",
            nonsemantic_channels=2,
            vetoes=[],
            defense_response="COVERED",
            nearest_knowns=[],
            confidence=0.9,
            completeness=1.0,
            algorithm_version="test-v1",
            thresholds_version="test-v1",
            explanation={},
        )

    return grade_fn


def test_observed_run_before_benign_close_anchor_raises_a_concern():
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = AnchorLibrary()
    seed = Seed(seed_id="seed-x3a", kind="detection_fire", entities=("host1",))
    notified = []

    run = observed_mode.run_observed_investigation(
        seed,
        plane,
        "edr",
        lib,
        signature_fn=_signature_fn,
        grade_fn=_grade_fn(reference_signature_id=None),
        notify=notified.append,
    )

    assert run.evidence["promotion"] is not None
    assert len(notified) == 1
    assert notified[0]["relationship"] == "SAME"


def test_observed_run_over_benign_closed_neighbourhood_raises_no_concern():
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = AnchorLibrary()
    signature = sig_mod.build_signature(
        {"target_host": "host1"}, {"action_sequence": ["proc_create", "net_connect"]}
    )
    anchor = compounding.write_outcome_as_anchor(
        lib,
        signature,
        source_id="analyst",
        outcome="BENIGN_CLOSE",
        analyst_confirmed=True,
    )

    seed = Seed(seed_id="seed-x3b", kind="detection_fire", entities=("host1",))
    notified = []

    run = observed_mode.run_observed_investigation(
        seed,
        plane,
        "edr",
        lib,
        signature_fn=_signature_fn,
        grade_fn=_grade_fn(reference_signature_id=anchor.anchor_id),
        notify=notified.append,
    )

    assert run.evidence["promotion"] is None
    assert notified == []


def test_compound_fn_writes_verdict_back_when_verdict_fn_supplies_one():
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = AnchorLibrary()
    seed = Seed(seed_id="seed-x3c", kind="detection_fire", entities=("host1",))

    run = observed_mode.run_observed_investigation(
        seed,
        plane,
        "edr",
        lib,
        signature_fn=_signature_fn,
        grade_fn=_grade_fn(reference_signature_id=None),
        notify=lambda _p: None,
        verdict_fn=lambda _concern: al.BENIGN,
    )

    closed, anchor = run.evidence["compounding"]
    assert closed.verdict == al.BENIGN
    assert anchor is not None
    assert anchor.record["outcome"] == "BENIGN_CLOSE"
    assert anchor.provenance_tier == "ANALYST_CONFIRMED"


def test_no_grade_fn_is_an_honest_no_op_not_a_fabricated_concern():
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = AnchorLibrary()
    seed = Seed(seed_id="seed-x3d", kind="detection_fire", entities=("host1",))

    run = observed_mode.run_observed_investigation(
        seed, plane, "edr", lib, signature_fn=_signature_fn
    )

    assert run.evidence["promotion"] is None
    assert run.evidence["compounding"] is None
