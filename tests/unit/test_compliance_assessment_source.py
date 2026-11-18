"""Workstream B — source acquisition / snapshot adapter unit tests.

No network, no real Ollama, no live retrieval service. Retrieval, rerank,
store and the policy graph are injected through fixtures.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from portal.modules.compliance.core import assessment_source as src
from portal.modules.compliance.core.boundary import (
    BoundaryCompletenessReceipt,
    BoundarySearch,
)
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.determination import (
    AssessmentRequest,
    CandidateRecord,
    CandidateSet,
    CorpusSnapshot,
    ScenarioEdit,
    ScenarioOverlay,
    SourceSlice,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _fake_graph():
    ref_node = SimpleNamespace(
        id="CIP-013-2 R1 Part 1.2",
        verbatim_text="The referenced supply chain clause body.",
        node_type="actor_cu",
        standard="CIP-013-2",
        requirement="R1",
        part="1.2",
        source_pdf="cip-013-2.pdf",
    )
    def_node = SimpleNamespace(
        id="CIP-013-2 R1 Part 1.3",
        verbatim_text="Definition: 'vendor' means an entity that provides products.",
        node_type="premise",
        standard="CIP-013-2",
        requirement="R1",
        part="1.3",
        source_pdf="cip-013-2.pdf",
    )
    edges = [
        {
            "src": "CIP-013-2 R1 Part 1.1",
            "dst": "CIP-013-2 R1 Part 1.2",
            "rel": "REFERS_TO",
            "surface_text": "Part 1.2",
            "char_start": 10,
            "char_end": 18,
            "resolution": "exact",
        },
        {
            "src": "CIP-013-2 R1 Part 1.1",
            "dst": "CIP-013-2 R1 Part 1.3",
            "rel": "REFERS_TO",
            "surface_text": "Part 1.3",
            "char_start": 20,
            "char_end": 28,
            "resolution": "exact",
        },
        # unresolved endpoints must be dropped, never fabricated
        {"src": "CIP-013-2 R1 Part 1.1", "dst": "", "rel": "REFERS_TO"},
        {"src": "CIP-013-2 R1 Part 1.1", "dst": "CIP-999-9 R9", "rel": "REFERS_TO"},
    ]
    return SimpleNamespace(nodes=[ref_node, def_node], edges=edges)


def test_resolve_bundle_preserves_full_part_leadin_refs_and_defs():
    reg = Register.load()
    node = next(n for n in reg.nodes if n.id == "CIP-013-2 R1 Part 1.1")
    lead = next(n for n in reg.nodes if n.id == "CIP-013-2 R1")

    bundle = src.resolve_governing_bundle("CIP-013-2 R1 Part 1.1", policy_graph=_fake_graph())

    assert bundle.ref == "CIP-013-2 R1 Part 1.1"
    # the complete Part, never trimmed to a role/first atom
    assert bundle.part_text == node.verbatim_text
    assert bundle.lead_in == lead.verbatim_text
    assert [r["ref"] for r in bundle.references] == ["CIP-013-2 R1 Part 1.2"]
    assert bundle.references[0]["text"] == "The referenced supply chain clause body."
    graph_defs = [d for d in bundle.definitions if not d.get("source")]
    assert [d["ref"] for d in graph_defs] == ["CIP-013-2 R1 Part 1.3"]
    assert graph_defs[0]["text"].startswith("Definition:")
    # P2: a standard deferring to the NERC Glossary also carries the Glossary
    # terms its own duty text depends on, each labelled with its source.
    for entry in bundle.definitions:
        if entry.get("source"):
            assert entry["source"] == "NERC Glossary of Terms"
            assert entry["section_id"] or not entry["resolved"]
    # every assembled element has a slice; no fabricated governing-register anchor
    refs = {s.ref for s in bundle.source_slices}
    assert {"CIP-013-2 R1 Part 1.1", "CIP-013-2 R1", "CIP-013-2 R1 Part 1.2"} <= refs
    assert all("governing-register" not in s.ref for s in bundle.source_slices)
    assert bundle.fingerprint


def test_resolve_bundle_fingerprint_is_stable_and_content_addressed():
    a = src.resolve_governing_bundle("CIP-013-2 R1 Part 1.1", policy_graph=_fake_graph())
    b = src.resolve_governing_bundle("CIP-013-2 R1 Part 1.1", policy_graph=_fake_graph())
    assert a.fingerprint == b.fingerprint
    assert all(s.revision_hash == _sha(s.text) for s in a.source_slices)


def test_resolve_bundle_unknown_requirement_raises_never_fabricates():
    with pytest.raises(ValueError, match="not in the register"):
        src.resolve_governing_bundle("CIP-999-9 R9 Part 9.9", policy_graph=_fake_graph())


def _source(cid: str, doc: str, chunk: str, text: str, loc: str = "p1") -> CandidateRecord:
    sl = SourceSlice(
        slice_id=f"sl-{cid}",
        ref=cid,
        document_id=doc,
        revision_hash=_sha(text),
        chunk_id=chunk,
        locator=loc,
        text=text,
        char_start=0,
        char_end=len(text),
        role="candidate",
    )
    return CandidateRecord(
        candidate_id=cid,
        document_id=doc,
        chunk_id=chunk,
        text=text,
        locator=loc,
        source_slice=sl,
    )


def _base_request() -> AssessmentRequest:
    snap = CorpusSnapshot(
        snapshot_id="s0",
        kb_id="kb",
        fingerprint="FP-BASE",
        acquisition_mode="RETRIEVAL",
        completeness="UNKNOWN",
    )
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2 Part 2.2",
        snapshot=snap,
        candidate_set=CandidateSet(
            records=[
                _source("c1", "policy.pdf", "chunk-1", "old forty day rule"),
                _source("c2", "other.pdf", "chunk-2", "unrelated retained policy"),
            ]
        ),
    )


def test_materialize_overlay_rejects_snapshot_mismatch():
    with pytest.raises(ValueError, match="U13"):
        src.materialize_overlay(_base_request(), ScenarioOverlay(base_snapshot_fingerprint="WRONG"))


def test_materialize_replace_returns_new_request_preserving_unaffected():
    request = _base_request()
    old = "old forty day rule"
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="policy.pdf",
        chunk_id="chunk-1",
        char_start=0,
        char_end=len(old),
        expected_old_hash=_sha(old),
        new_text="new thirty five day rule",
    )
    out = src.materialize_overlay(request, ScenarioOverlay("FP-BASE", edits=[edit]))

    assert out is not request
    # original is untouched
    assert request.snapshot is not None and request.snapshot.fingerprint == "FP-BASE"
    assert [r.candidate_id for r in request.candidate_set.records] == ["c1", "c2"]
    # new snapshot + preserved unaffected candidate + proposed slice
    assert out.snapshot is not None and out.snapshot.fingerprint != "FP-BASE"
    ids = [r.candidate_id for r in out.candidate_set.records]
    assert "c2" in ids
    proposed = next(r for r in out.candidate_set.records if r.layer == "proposed")
    assert proposed.text == "new thirty five day rule"
    assert proposed.source_slice is not None and proposed.source_slice.role == "proposed"
    assert "policy.pdf" in out.affected_parts


def test_materialize_replace_rejects_stale_hash():
    request = _base_request()
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="policy.pdf",
        chunk_id="chunk-1",
        char_start=0,
        char_end=len("old forty day rule"),
        expected_old_hash="deadbeef",
        new_text="x",
    )
    with pytest.raises(ValueError, match="stale expected_old_hash"):
        src.materialize_overlay(request, ScenarioOverlay("FP-BASE", edits=[edit]))


def test_materialize_replace_rejects_overlapping_edits():
    request = _base_request()
    old = "old forty day rule"
    edits = [
        ScenarioEdit(
            operation="REPLACE",
            target_document="policy.pdf",
            chunk_id="chunk-1",
            char_start=0,
            char_end=10,
            expected_old_hash=_sha(old[0:10]),
            new_text="AAAA",
        ),
        ScenarioEdit(
            operation="REPLACE",
            target_document="policy.pdf",
            chunk_id="chunk-1",
            char_start=5,
            char_end=15,
            expected_old_hash=_sha(old[5:15]),
            new_text="BBBB",
        ),
    ]
    with pytest.raises(ValueError, match="overlapping"):
        src.materialize_overlay(request, ScenarioOverlay("FP-BASE", edits=edits))


def test_materialize_replace_rejects_ambiguous_target():
    request = _base_request()
    duplicate = _source("c3", "policy.pdf", "chunk-1", "a second chunk one")
    request.candidate_set.records.append(duplicate)
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="policy.pdf",
        chunk_id="chunk-1",
        expected_old_hash=_sha("old forty day rule"),
        new_text="x",
    )
    with pytest.raises(ValueError, match="ambiguous"):
        src.materialize_overlay(request, ScenarioOverlay("FP-BASE", edits=[edit]))


def test_materialize_add_appends_proposed_procedure():
    request = _base_request()
    edit = ScenarioEdit(
        operation="ADD",
        target_document="new-policy.pdf",
        target_section="Part 2.2",
        new_text="SMEs shall evaluate patches every 35 days.",
    )
    out = src.materialize_overlay(request, ScenarioOverlay("FP-BASE", edits=[edit]))
    added = next(r for r in out.candidate_set.records if r.layer == "proposed")
    assert added.document_id == "new-policy.pdf"
    assert added.source_slice is not None and added.source_slice.role == "proposed"
    assert "new-policy.pdf" in out.affected_parts
    # unaffected originals all retained
    assert {"c1", "c2"} <= {r.candidate_id for r in out.candidate_set.records}


def _legacy_boundary(**kw) -> BoundarySearch:
    return BoundarySearch("REQ", ["q"], "gen", "manifest", 1, **kw)


def test_boundary_without_receipt_is_not_exhaustive():
    assert _legacy_boundary().exhaustive is False


def test_boundary_with_complete_receipt_is_exhaustive():
    receipt = BoundaryCompletenessReceipt(
        eligible=[{"section_id": "a"}, {"section_id": "b"}],
        examined=["a", "b"],
        acquisition_mode="EXPLICIT_SET",
    )
    assert receipt.complete is True
    assert _legacy_boundary(completeness_receipt=receipt).exhaustive is True


def test_boundary_with_unaccounted_or_omitted_sections_is_not_exhaustive():
    unaccounted = BoundaryCompletenessReceipt(
        eligible=[{"section_id": "a"}, {"section_id": "b"}],
        examined=["a"],
    )
    assert unaccounted.unaccounted() == ["b"]
    assert _legacy_boundary(completeness_receipt=unaccounted).exhaustive is False
    omitted = BoundaryCompletenessReceipt(
        eligible=[{"section_id": "a"}],
        examined=["a"],
        omissions=["b"],
    )
    assert _legacy_boundary(completeness_receipt=omitted).exhaustive is False


def test_table_part_recovers_parent_from_pinned_pdf():
    bundle = src.resolve_governing_bundle("CIP-007-6 R2 Part 2.2")
    assert "collectively include each of the applicable requirement parts" in bundle.lead_in
    parent = next(s for s in bundle.source_slices if s.ref == "CIP-007-6 R2")
    assert parent.text == bundle.lead_in
    assert parent.revision_hash == _sha(parent.text)


def test_parent_pdf_revision_must_match_register():
    reg = Register.load()
    node = next(n for n in reg.nodes if n.id == "CIP-007-6 R2 Part 2.2")
    reg.source_pdfs[node.source_pdf] = "0" * 12
    with pytest.raises(ValueError, match="revision mismatch"):
        src._pdf_parent_requirement(node, reg)
