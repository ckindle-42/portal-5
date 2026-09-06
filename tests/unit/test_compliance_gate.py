"""P4 the gate — structural pre-analysis, no model calls (checks Y08, Y03, Y04)."""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.gate import run_gate
from portal.modules.compliance.core.policy_graph import build_policy_graph
from portal.modules.compliance.core.vocabulary_bridge import derive_vocabulary


@pytest.fixture(scope="module")
def env():
    g = build_policy_graph()
    v = derive_vocabulary()
    return g, v


def _scope_hm():
    return AssetScope(
        impact_present={"high", "medium"},
        associated_present={"eacms", "pacs", "pca"},
        declared_by="operator:test",
    )


def test_gate_has_no_model_call():
    src = __import__("pathlib").Path("portal/modules/compliance/core/gate.py").read_text()
    for banned in ("ollama", "httpx", "AsyncClient", "/api/chat", "openai"):
        assert banned not in src


def test_applies_scope_produces_a_council_packet(env):
    g, v = env
    coms = [
        {
            "commitment_id": "c1",
            "document_id": "spm",
            "standard_folder": "CIP-007",
            "actor": "OT Security Team",
            "text": "The OT Security Team shall evaluate security patches for applicability every 21 calendar days.",
        }
    ]
    r = run_gate("CIP-007-6 R2 Part 2.2", g, v, _scope_hm(), coms)
    assert r.applicability == "APPLIES"
    assert not r.gated_out
    assert r.reference_closure == ["CIP-007-6 R2 Part 2.1"]  # Y03: traversed, not retrieved
    assert r.candidates and r.candidates[0].actor_aligned
    assert r.candidates[0].quantity_outcome == "MORE_RESTRICTIVE"
    packet = r.to_council_packet()
    assert packet["governing_unit"]["ref"] == "CIP-007-6 R2 Part 2.2"
    assert "constraint" in packet["governing_unit"]


def test_out_of_scope_cu_is_gated_out_not_scored(env):
    g, v = env
    # a low-impact-only entity against a high/medium-only Part
    low_only = AssetScope(impact_present={"low"}, declared_by="operator:test")
    hm_only = next(
        n
        for n in g.nodes
        if n.node_type == "actor_cu"
        and "High Impact" in n.applicable_systems
        and "low impact" not in n.applicable_systems
    )
    r = run_gate(hm_only.id, g, v, low_only, [])
    assert r.applicability == "DOES_NOT_APPLY"
    assert r.gated_out
    assert r.candidates == []
    assert any("never scored ABSENT" in note for note in r.notes)


def test_exception_clause_is_surfaced_for_the_council(env):
    g, v = env
    r = run_gate("CIP-004-7 R2 Part 2.2", g, v, _scope_hm(), [])
    assert any("Exceptional Circumstances" in c["text"] for c in r.exception_clauses)


def test_retrieval_backstop_surplus_is_reported_not_unioned(env):
    g, v = env
    hits = [{"commitment_id": "r99", "actor": "x", "text": "Patches reviewed once a year."}]
    r = run_gate("CIP-007-6 R2 Part 2.2", g, v, _scope_hm(), [], retrieval_hits=hits)
    assert "r99" in r.backstop_surplus
    assert any("surplus reported" in note for note in r.notes)
    assert [c for c in r.candidates if c.source == "retrieval_backstop"]


def test_undeclared_scope_is_unknown_not_applies(env):
    g, v = env
    r = run_gate("CIP-007-6 R2 Part 2.2", g, v, AssetScope(), [])
    assert r.applicability in {"UNKNOWN", "CONFLICTED"}
    assert not r.gated_out  # UNKNOWN still reaches the council, provisionally
