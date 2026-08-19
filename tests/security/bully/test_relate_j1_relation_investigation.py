"""J.1 -- relation-driven investigation, the interlock: the arm's first
queries are derived from the relation's uncertainty reasons; a
low-confidence relation produces more investigation, not less."""

from __future__ import annotations

from portal.modules.security.core.bully import observed_mode
from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.connectors import IterableIngestConnector
from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane
from portal.modules.security.core.bully.relation_investigation import build_investigation_brief
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


def test_arm_questions_are_derived_from_uncertainty_reasons():
    lib = _populated_library()
    signature = sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    rel = relation_mod.relate(signature, lib, capabilities={"semantic_text": False})
    brief = build_investigation_brief(rel)

    assert brief.questions[0] == brief.base_question
    assert len(brief.questions) == 1 + len(rel.uncertainty_reasons)
    assert "resembles" in brief.base_question or "no anchor resembles" in brief.base_question
    # every follow-up question traces to a specific uncertainty reason
    assert brief.uncertainty_question_count == len(rel.uncertainty_reasons)


def test_low_confidence_relation_produces_more_investigation_not_less():
    lib = _populated_library()
    high_conf_signature = sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    low_conf_signature = sig_mod.build_signature({"target_host": "host2"}, {})

    high_conf_rel = relation_mod.relate(
        high_conf_signature, lib, capabilities={"semantic_text": True}
    )
    low_conf_rel = relation_mod.relate(
        low_conf_signature, lib, capabilities={"semantic_text": True}
    )

    high_brief = build_investigation_brief(high_conf_rel)
    low_brief = build_investigation_brief(low_conf_rel)

    assert low_conf_rel.confidence <= high_conf_rel.confidence
    assert len(low_brief.questions) >= len(high_brief.questions)


def test_wired_observed_investigation_puts_relation_in_evidence():
    plane = DataPlane()
    connector = IterableIngestConnector(
        "edr",
        [{"host": "host1", "action": "proc_create"}, {"host": "host1", "action": "net_connect"}],
    )
    plane.connect(
        "edr",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, True)},
    )
    lib = _populated_library()
    seed = Seed(seed_id="seed-j1", kind="detection_fire", entities=("host1",))

    def _signature_fn(scope):
        actions = [
            str(r.get("action")) for r in scope.records if isinstance(r, dict) and r.get("action")
        ]
        return sig_mod.build_signature({"target_host": "host1"}, {"action_sequence": actions})

    run = observed_mode.run_observed_investigation(
        seed, plane, "edr", lib, signature_fn=_signature_fn
    )

    # TASK_BULLY_COUSIN_RELATION_V1 C.2: RELATING is re-pointed at the
    # observed-mode cousin grader, so evidence["relation"] is now a
    # CousinRelation (`status`), not the provoked-grader Relation
    # (`verdict`) -- see test_cousin_c2_observed_wiring.py for the
    # CousinRelation-specific contract.
    assert run.current_stage == "CLOSED"
    assert run.evidence["relation"] is not None
    assert run.evidence["relation"].status in {
        "COUSIN_CANDIDATE",
        "NOVEL_NOTABLE",
        "INSUFFICIENT_VIEW",
        "NO_RELATION",
    }
    investigation = run.evidence["investigation"]
    assert investigation.relation is run.evidence["relation"]
    assert investigation.questions[0] == investigation.base_question
