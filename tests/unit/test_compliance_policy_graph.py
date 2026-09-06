"""P2 policy-graph typing invariants (TASK_COMPLIANCE_REASONING_V6, check Y01)."""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.policy_graph import (
    build_policy_graph,
    classify_node,
)

_MODAL_TERMS = ("shall", "must", "may not", "required to")


@pytest.fixture(scope="module")
def graph():
    return build_policy_graph()


def test_every_node_is_typed(graph):
    assert len(graph.nodes) == len(Register.load().nodes)
    valid = {"premise", "meta_cu", "actor_cu"}
    assert all(n.node_type in valid for n in graph.nodes)
    assert all(n.typing_rule and n.typing_evidence for n in graph.nodes)


def test_typing_is_deterministic():
    a = build_policy_graph()
    b = build_policy_graph()
    assert [(n.id, n.node_type) for n in a.nodes] == [(n.id, n.node_type) for n in b.nodes]


def test_impact_rating_criteria_are_premises(graph):
    crit = [n for n in graph.nodes if n.standard.startswith("CIP-002") and "Attachment 1" in n.id]
    assert crit and all(n.node_type == "premise" for n in crit)


def test_policy_topic_labels_are_premises(graph):
    # CIP-003 R1's "policies that ... address the following topics" list — the
    # topic is subject matter, never itself a duty (task A02).
    topics = [n for n in graph.nodes if n.typing_rule == "enumerated_policy_topic"]
    assert len(topics) >= 20
    assert all(n.node_type == "premise" for n in topics)


def test_no_premise_carries_an_unconditioned_modal(graph):
    # A premise may quote a modal inside a defined term, but a bare
    # "Each Responsible Entity shall ..." Part must never be typed premise.
    for n in graph.nodes:
        if n.node_type != "premise":
            continue
        low = n.verbatim_text.lower()
        assert not (
            low.startswith(("each responsible entity shall", "the responsible entity shall"))
        )


def test_known_obligations_are_actor_cus(graph):
    by_id = {n.id: n for n in graph.nodes}
    for ref in (
        "CIP-007-6 R2 Part 2.2",
        "CIP-007-6 R4 Part 4.4",
        "CIP-004-7 R2 Part 2.2",
        "CIP-004-7 R2 Part 2.3",
        "CIP-010-4 R1 Part 1.3",
        "CIP-010-4 R2 Part 2.1",
        "CIP-009-6 R2 Part 2.1",
        "CIP-006-6 R1 Part 1.5",
        "CIP-002-5.1a R2 Part 2.2",
    ):
        assert by_id[ref].node_type == "actor_cu", ref


def test_classify_node_pure_premise_definition():
    n = RegisterNode(
        id="X R1 Part 1.1",
        standard="CIP-999-1",
        version="1",
        requirement="R1",
        part="1.1",
        verbatim_text="Each BES Cyber System used to perform a function.",
        measure_text="",
        applicable_systems="",
        table_name="",
        vrf="",
        time_horizon="",
        lifecycle_state="EFFECTIVE",
        valid_from="2020-01-01",
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="x.pdf",
        source_pages=[],
        recorded_at=0.0,
        granularity="part",
    )
    kind, rule, _ = classify_node(n, None)
    assert kind == "premise"


def test_classify_node_explicit_modal_is_actor_cu():
    n = RegisterNode(
        id="X R1 Part 1.1",
        standard="CIP-999-1",
        version="1",
        requirement="R1",
        part="1.1",
        verbatim_text="Each Responsible Entity shall retain evidence for 3 years.",
        measure_text="",
        applicable_systems="",
        table_name="Evidence",
        vrf="",
        time_horizon="",
        lifecycle_state="EFFECTIVE",
        valid_from="2020-01-01",
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="x.pdf",
        source_pages=[],
        recorded_at=0.0,
        granularity="part",
    )
    kind, rule, _ = classify_node(n, None)
    assert kind == "actor_cu"
    assert rule == "explicit_modal"
