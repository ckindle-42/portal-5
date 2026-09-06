"""P2 policy-graph typing invariants (TASK_COMPLIANCE_REASONING_V6, check Y01)."""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.policy_graph import (
    build_policy_graph,
    classify_node,
    resolve_references,
)

_MODAL_TERMS = ("shall", "must", "may not", "required to")


@pytest.fixture(scope="module")
def graph():
    return build_policy_graph()


def test_every_node_is_typed(graph):
    reg_n = len(Register.load().nodes)
    register_derived = [
        n for n in graph.nodes if n.typing_rule != "synthesized_from_applicable_systems"
    ]
    assert len(register_derived) == reg_n
    valid = {"premise", "meta_cu", "actor_cu"}
    assert all(n.node_type in valid for n in graph.nodes)
    assert all(n.typing_rule and n.typing_evidence for n in graph.nodes)


def test_meta_cus_gate_actor_cus_and_are_never_bare_register_nodes(graph):
    metas = [n for n in graph.nodes if n.node_type == "meta_cu"]
    assert metas and all(n.typing_rule == "synthesized_from_applicable_systems" for n in metas)
    # every synthesized meta-CU carries a parsed predicate and gates >=1 actor-CU
    gated = {e["dst"] for e in graph.edges if e["rel"] == "GATES"}
    gators = {e["src"] for e in graph.edges if e["rel"] == "GATES"}
    assert gators == {n.id for n in metas}
    by_id = {n.id: n for n in graph.nodes}
    for m in metas:
        assert m.scope_predicate.get("impact_ratings") is not None
    for dst in gated:
        assert by_id[dst].node_type == "actor_cu"
        assert any(m.startswith(dst.split(" ")[0]) for m in by_id[dst].gated_by)


def test_only_actor_cus_would_receive_determinations(graph):
    # Y01: premises and meta-CUs must be excluded from the judged set.
    judged = [n for n in graph.nodes if n.node_type == "actor_cu"]
    not_judged = [n for n in graph.nodes if n.node_type != "actor_cu"]
    assert len(judged) == 197
    assert all(n.node_type in {"premise", "meta_cu"} for n in not_judged)


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


def test_resolve_references_direct():
    reg = Register.load()
    ids = {n.id for n in reg.nodes}
    node = next(n for n in reg.nodes if n.id == "CIP-002-5.1a R2 Part 2.1")
    edges = resolve_references(node, reg, ids)
    dsts = {e["dst"] for e in edges}
    assert "CIP-002-5.1a R1" in dsts  # "Requirement R1"
    assert any(e["resolution"] == "unresolved_relative" for e in edges)  # "its parts"


def test_reference_edges_resolve_or_are_worklisted(graph):
    reg_ids = {n.id for n in graph.nodes}
    reg_stds = {n.standard for n in graph.nodes}
    refs = [e for e in graph.edges if e["rel"] == "REFERS_TO"]
    assert len(refs) >= 90
    groupish = {"requirement_group", "part_group", "standard_stem"}
    worklist = {
        "unresolved_relative",
        "unresolved_section",
        "unresolved_part",
        "unresolved_requirement",
        "table_not_a_node",
    }
    for e in refs:
        if e["resolution"] in worklist:
            assert e["dst"] == "" or e["resolution"] == "table_not_a_node"
            continue
        assert e["dst"], e
        assert e["dst"] in reg_ids or e["dst"] in reg_stds or e["resolution"] in groupish, e


def test_reference_spans_reresolve_verbatim(graph):
    by_id = {n.id: n.verbatim_text for n in graph.nodes}
    for e in graph.edges:
        if e["rel"] == "REFERS_TO" and e["surface_text"]:
            src = by_id[e["src"]]
            assert src[e["char_start"] : e["char_end"]] == e["surface_text"], e


def test_cip002_r1_part_points_at_its_attachment_criteria(graph):
    by_src = {}
    for e in graph.edges:
        if e["rel"] == "REFERS_TO":
            by_src.setdefault(e["src"], []).append(e["dst"])
    assert "CIP-002-5.1a Attachment 1 Section 1" in by_src.get("CIP-002-5.1a R1 Part 1.1", [])


def test_cross_standard_reference_resolves_to_effective_version(graph):
    # CIP-003-9 R1 Part 1.1.1 mentions "(CIP-004)" — must resolve to CIP-004-7.
    edge = next(
        e for e in graph.edges if e["src"] == "CIP-003-9 R1 Part 1.1.1" and e["rel"] == "REFERS_TO"
    )
    assert edge["dst"] == "CIP-004-7"


def test_actor_cu_decomposition_has_spanned_fields(graph):
    acus = [n for n in graph.nodes if n.node_type == "actor_cu"]
    assert all(n.cu for n in acus)
    for n in acus:
        cu = n.cu
        assert set(cu) == {"subject", "constraint", "condition", "context"}
        t = n.verbatim_text
        s = cu["subject"]
        if not s["implied"]:
            assert t[s["char_start"] : s["char_end"]] == s["text"]
        q = cu["constraint"].get("quantity")
        if q:
            assert t[q["char_start"] : q["char_end"]] == q["text"]
            assert q["direction"] in {
                "max_interval",
                "max_elapsed",
                "min_interval",
                "interval",
            }
        for c in cu["condition"]:
            assert c["kind"] in {"exception", "conditional", "scope"}
            assert t[c["char_start"] : c["char_end"]].strip() == c["text"]


def test_known_quantities_parse_with_correct_direction(graph):
    by_id = {n.id: n for n in graph.nodes}
    q = by_id["CIP-007-6 R2 Part 2.2"].cu["constraint"]["quantity"]
    assert (q["value"], q["unit"], q["qualifier"], q["direction"]) == (
        35,
        "day",
        "calendar",
        "max_interval",
    )
    q2 = by_id["CIP-010-4 R1 Part 1.3"].cu["constraint"]["quantity"]
    assert (q2["value"], q2["unit"], q2["direction"]) == (30, "day", "max_elapsed")


def test_cu_context_carries_scope_and_refs(graph):
    by_id = {n.id: n for n in graph.nodes}
    ctx = by_id["CIP-007-6 R2 Part 2.2"].cu["context"]
    assert ctx["applicable_systems"]
    assert ctx["gated_by"]  # gated by its applicable_systems meta-CU
    assert "CIP-007-6 R2 Part 2.1" in ctx["refers_to"]  # "identified in Part 2.1"


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
