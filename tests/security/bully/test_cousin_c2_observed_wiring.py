"""C.2 -- observed mode grades via the cousin relation grader, not the
provoked `cousin_engine`/`relation` path. `relation.relate` is left in
place, unmodified, so C.7 can run the old path head-to-head."""

from __future__ import annotations

from portal.modules.security.core.bully import cousin_relation as cr
from portal.modules.security.core.bully import observed_mode
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.connectors import IterableIngestConnector
from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane
from portal.modules.security.core.bully.seed_scope import Seed


def _populated_library() -> AnchorLibrary:
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["proc_create", "net_connect"]},
        techniques=("T1059",),
    )
    lib.load_detection_coverage(
        source_id="detection_lib",
        detection_id="det-001",
        techniques=("T1059",),
        telemetry_shape={"source_class": "edr"},
    )
    return lib


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


def test_observed_run_puts_cousin_relation_in_evidence():
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = _populated_library()
    seed = Seed(seed_id="seed-c2", kind="detection_fire", entities=("host1",))

    run = observed_mode.run_observed_investigation(
        seed, plane, "edr", lib, signature_fn=_signature_fn
    )

    assert run.current_stage == "CLOSED"
    relation = run.evidence["relation"]
    assert isinstance(relation, cr.CousinRelation)


def test_run_never_enters_mutation_ready_or_executing():
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = _populated_library()
    seed = Seed(seed_id="seed-c2b", kind="operator_hunch", entities=("host1",))

    run = observed_mode.run_observed_investigation(
        seed, plane, "edr", lib, signature_fn=_signature_fn
    )

    assert "MUTATION_READY" not in run.stages_entered
    assert "EXECUTING" not in run.stages_entered


def test_source_with_zero_declared_capabilities_still_produces_a_graded_relation():
    """`capabilities` is no longer a weighting input: axis participation is
    decided by what the arrival actually carries, per-pair. A source that
    declares nothing still relates -- a capability flag never gates or
    weights the measurement."""
    plane = DataPlane()
    connector = IterableIngestConnector(
        "edr",
        [{"host": "host1", "action": "proc_create"}, {"host": "host1", "action": "net_connect"}],
    )
    plane.connect(
        "edr",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, False)},
    )
    lib = _populated_library()
    seed = Seed(seed_id="seed-c2c", kind="detection_fire", entities=("host1",))

    run = observed_mode.run_observed_investigation(
        seed, plane, "edr", lib, signature_fn=_signature_fn, capabilities={}
    )

    relation = run.evidence["relation"]
    assert isinstance(relation, cr.CousinRelation)
    assert relation.status == "COUSIN_CANDIDATE"
    assert relation.distance == 0.0
    assert run.evidence["capabilities_declared"] == {}


def test_capabilities_annotation_never_alters_the_measurement():
    """A declared-capabilities flag is recorded as an annotation only -- it
    must not change the distance/status the grader computes."""
    plane = _plane_with_seed(["proc_create", "net_connect"])
    lib = _populated_library()

    seed_a = Seed(seed_id="seed-a", kind="detection_fire", entities=("host1",))
    seed_b = Seed(seed_id="seed-b", kind="detection_fire", entities=("host1",))

    run_true = observed_mode.run_observed_investigation(
        seed_a,
        plane,
        "edr",
        lib,
        signature_fn=_signature_fn,
        capabilities=dict.fromkeys(CAPABILITIES, True),
    )
    run_false = observed_mode.run_observed_investigation(
        seed_b,
        plane,
        "edr",
        lib,
        signature_fn=_signature_fn,
        capabilities=dict.fromkeys(CAPABILITIES, False),
    )

    assert run_true.evidence["relation"].distance == run_false.evidence["relation"].distance
    assert run_true.evidence["relation"].status == run_false.evidence["relation"].status
    assert run_true.evidence["capabilities_declared"] != run_false.evidence["capabilities_declared"]


def test_provoked_path_unregressed():
    """relation.py is not touched by C.2 -- direct calls still work exactly
    as before."""
    from portal.modules.security.core.bully import relation as relation_mod

    lib = _populated_library()
    signature = sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    rel = relation_mod.relate(signature, lib, capabilities={"semantic_text": False})
    assert hasattr(rel, "verdict")
