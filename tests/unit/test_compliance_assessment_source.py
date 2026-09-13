"""Workstream B — source acquisition / snapshot adapter unit tests.

No network, no real Ollama, no live retrieval service. Retrieval, rerank,
store and the policy graph are injected through fixtures.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from portal.modules.compliance.core import assessment_source as src
from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.boundary import (
    BoundaryCompletenessReceipt,
    BoundarySearch,
    persist,
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


# ── resolve_governing_bundle ────────────────────────────────────────────────


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
    assert [d["ref"] for d in bundle.definitions] == ["CIP-013-2 R1 Part 1.3"]
    assert bundle.definitions[0]["text"].startswith("Definition:")
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


# ── acquire_candidates ──────────────────────────────────────────────────────


def _hit(**over):
    base = {
        "document_id": "policy.pdf",
        "section_id": "policy.pdf #chunk44 p11",
        "chunk_id": "chunk-44",
        "text": "The full stored chunk text that a reader must be able to read.",
        "headings": "3 > 3.4 > 3.4.2",
        "char_start": 120,
        "char_end": 300,
        "page": 11,
        "layer": "policy",
        "rerank_score": 0.91,
        "relevant": True,
        "anchor_verified": True,
        "locatable": True,
    }
    base.update(over)
    return base


@pytest.fixture
def stub_retrieval(monkeypatch):
    calls: dict[str, object] = {}

    def _fake(node, *, kb_id, top_k, arbiter_fn):
        calls["args"] = (node.id, kb_id, top_k)
        hits = [_hit()]
        unresolved = [
            {
                "document_id": "diagram.pdf",
                "section_id": "diagram.pdf #chunk-1 p3",
                "kind": "visual",
                "reason": "non-text pointer",
            }
        ]
        receipt = {
            "kb_id": kb_id,
            "acquisition_mode": "RETRIEVAL",
            "completeness": "UNKNOWN",
        }
        return hits, unresolved, receipt

    monkeypatch.setattr(src._propose, "resolve_candidates", _fake)
    return calls, _fake


def test_acquire_candidates_carries_full_text_provenance_and_slice(stub_retrieval):
    calls, _ = stub_retrieval
    node = SimpleNamespace(id="CIP-007-6 R2 Part 2.2", standard="CIP-007-6", verbatim_text="q")
    cs = src.acquire_candidates(node, kb_id="operator_corpus", top_k=15)

    assert calls["args"] == ("CIP-007-6 R2 Part 2.2", "operator_corpus", 15)
    assert len(cs.records) == 1
    rec = cs.records[0]
    assert rec.candidate_id == "chunk-44"
    assert rec.text == _hit()["text"]  # complete, not the 400-char display span
    assert rec.chunk_id == "chunk-44"
    assert rec.locator == "3 > 3.4 > 3.4.2"
    assert rec.char_start == 0 and rec.char_end == len(rec.text)
    sl = rec.source_slice
    assert sl is not None
    assert sl.role == "candidate"
    assert sl.text == rec.text
    assert sl.doc_char_start == 120 and sl.doc_char_end == 300
    assert sl.revision_hash == _sha(rec.text)
    # scores/flags stay diagnostics
    assert cs.retrieval_annotations[0]["rerank_score"] == 0.91
    assert cs.retrieval_annotations[0]["relevant"] is True
    # non-text pointer travels, never becomes evidence
    assert cs.unresolved and cs.unresolved[0]["kind"] == "visual"
    assert cs.acquisition_receipt["acquisition_mode"] == "RETRIEVAL"
    assert cs.acquisition_receipt["completeness"] == "UNKNOWN"
    assert cs.acquisition_receipt["candidate_identities"] == ["chunk-44"]


def test_acquire_candidates_empty_is_typed_with_receipt_not_completeness(monkeypatch):
    monkeypatch.setattr(
        src._propose,
        "resolve_candidates",
        lambda node, *, kb_id, top_k, arbiter_fn: ([], [], {"kb_id": kb_id}),
    )
    node = SimpleNamespace(id="X", standard="CIP-007-6", verbatim_text="q")
    cs = src.acquire_candidates(node, kb_id="operator_corpus")
    assert cs.records == []
    assert cs.acquisition_receipt["completeness"] == "UNKNOWN"
    assert cs.acquisition_receipt["n_candidates"] == 0


# ── build_corpus_snapshot ───────────────────────────────────────────────────


class _Frame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):  # noqa: ARG002 - matches pandas API
        return self._rows


class _Table:
    version = 70

    def to_pandas(self):
        return _Frame(
            [
                {"source_file": "a.pdf", "chunk_index": 0, "text": "alpha"},
                {"source_file": "a.pdf", "chunk_index": 1, "text": "beta"},
                {"source_file": "b.pdf", "chunk_index": 0, "text": "gamma"},
            ]
        )


@pytest.fixture
def stub_store(monkeypatch):
    from portal.platform.retrieval import store as store_mod

    monkeypatch.setattr(store_mod, "text_table", lambda *a, **k: _Table())
    monkeypatch.setattr(store_mod, "read_stamp", lambda *a, **k: {"embed_model": "fake-vl"})


def test_corpus_snapshot_unknown_for_topk_and_stable_fingerprint(stub_store):
    snap = src.build_corpus_snapshot("operator_corpus")
    assert snap.completeness == "UNKNOWN"
    assert snap.acquisition_mode == "RETRIEVAL"
    assert snap.table_name == "compliance_operator_corpus"
    assert snap.table_version == 70
    assert snap.index_generation.startswith("compliance_operator_corpus@70")
    assert set(snap.document_revision_hashes) == {"a.pdf", "b.pdf"}
    assert snap.manifest_hash
    assert snap.fingerprint == _snapshot_fp(snap)
    again = src.build_corpus_snapshot("operator_corpus")
    assert again.fingerprint == snap.fingerprint  # random id excluded from the hash
    assert snap.snapshot_id != "" and snap.snapshot_id.startswith("snap-")


def test_corpus_snapshot_complete_only_with_completed_boundary_receipt(stub_store):
    receipt = {
        "acquisition_mode": "EXPLICIT_SET",
        "boundary_receipt": {"complete": True},
        "candidate_identities": ["s1", "s2"],
    }
    snap = src.build_corpus_snapshot("fixture_kb", acquisition_receipt=receipt)
    assert snap.completeness == "COMPLETE"
    assert snap.acquisition_mode == "EXPLICIT_SET"
    assert snap.candidate_identities == ["s1", "s2"]
    # a bare "search ran" receipt is not completeness
    snap2 = src.build_corpus_snapshot("fixture_kb", acquisition_receipt={"searched": True})
    assert snap2.completeness == "UNKNOWN"


def _snapshot_fp(snap: CorpusSnapshot) -> str:
    # recompute independently of the module helper
    import json

    body = {
        "kb_id": snap.kb_id,
        "manifest_hash": snap.manifest_hash,
        "index_generation": snap.index_generation,
        "table_name": snap.table_name,
        "table_version": snap.table_version,
        "document_revision_hashes": dict(sorted(snap.document_revision_hashes.items())),
        "candidate_identities": sorted(snap.candidate_identities),
        "acquisition_mode": snap.acquisition_mode,
        "completeness": snap.completeness,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# ── build_assessment_request ────────────────────────────────────────────────


def test_build_assessment_request_declares_scope_and_wires_snapshot(
    monkeypatch, stub_retrieval, stub_store
):
    from portal.modules.compliance.core import determination as det

    fake_bundle = det.GoverningBundle(ref="CIP-013-2 R1 Part 1.1", part_text="full part text")
    monkeypatch.setattr(src, "resolve_governing_bundle", lambda rid, policy_graph=None: fake_bundle)

    request = src.build_assessment_request(
        "CIP-013-2 R1 Part 1.1",
        scope_text="high and medium impact; EACMS",
        effective_on="2026-09-12",
        conditional_scope=True,
        top_k=15,
    )
    assert request.requirement_id == "CIP-013-2 R1 Part 1.1"
    assert request.scope_basis == "conditional"
    assert request.conditional_scope is True
    assert isinstance(request.scope, AssetScope)
    assert request.scope.declared_by == "operator:scope-declaration"
    assert request.governing is fake_bundle
    assert request.snapshot is not None and request.snapshot.kb_id == "operator_corpus"
    assert request.candidate_set is not None and request.candidate_set.records
    assert request.metadata["scope"]["basis"] == "declared"


def test_build_assessment_request_defaults_actual_scope(monkeypatch, stub_retrieval, stub_store):
    from portal.modules.compliance.core import determination as det

    monkeypatch.setattr(
        src,
        "resolve_governing_bundle",
        lambda rid, policy_graph=None: det.GoverningBundle(ref=rid, part_text="full part text"),
    )
    request = src.build_assessment_request("CIP-013-2 R1 Part 1.1")
    assert request.scope_basis == "actual"
    assert request.conditional_scope is False
    assert request.org_id == "default"


# ── materialize_overlay ─────────────────────────────────────────────────────


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


def test_materialize_bare_legacy_patch_is_labelled_add_never_replacement():
    request = _base_request()
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="policy.pdf",
        target_section="ignored",
        new_text="a bare legacy patch",
        label="",
    )
    out = src.materialize_overlay(request, ScenarioOverlay("FP-BASE", edits=[edit]))
    # the old rule is retained, not silently replaced
    ids = [r.candidate_id for r in out.candidate_set.records]
    assert "c1" in ids
    added = next(r for r in out.candidate_set.records if r.layer == "proposed")
    assert "legacy-add" in added.locator


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


# ── boundary completeness receipt ───────────────────────────────────────────


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


def test_persist_rejects_boundary_without_receipt(tmp_path):
    from portal.modules.compliance.core.repository import Repository

    repo = Repository(tmp_path / "boundary.db")
    with pytest.raises(ValueError, match="completed-boundary receipt"):
        persist(repo, _legacy_boundary())


def test_persist_accepts_complete_receipt(tmp_path):
    from portal.modules.compliance.core.repository import Repository

    repo = Repository(tmp_path / "boundary.db")
    receipt = BoundaryCompletenessReceipt(
        eligible=[{"section_id": "a"}],
        examined=["a"],
        acquisition_mode="EXPLICIT_SET",
    )
    proof_id = persist(repo, _legacy_boundary(completeness_receipt=receipt))
    assert proof_id.startswith("boundary-")


# ── runtime config ──────────────────────────────────────────────────────────


def test_build_assessment_context_uses_config_seats_and_quorum(tmp_path):
    from portal.modules.compliance.core.runtime_config import (
        build_assessment_context,
        council_quorum,
        seat_roster,
    )

    ctx = build_assessment_context(
        "operator_corpus", AssetScope(), "2026-09-12", "2026-09-12", repository=None
    )
    assert ctx.seats == seat_roster()
    assert ctx.quorum == council_quorum()
    assert callable(ctx.source_resolver)
    assert ctx.kb_id == "operator_corpus"


def test_org_commitments_distinguish_missing_from_empty(tmp_path):
    from portal.modules.compliance.core.runtime_config import (
        load_org_commitments,
        load_org_commitments_result,
    )

    missing = load_org_commitments_result(tmp_path / "nope.json")
    assert missing["status"] == "MISSING"
    assert missing["commitments"] == []
    assert load_org_commitments(tmp_path / "nope.json") == []

    empty_path = tmp_path / "empty.json"
    empty_path.write_text('{"documents": [], "nodes": []}')
    empty = load_org_commitments_result(empty_path)
    assert empty["status"] == "EMPTY"
    assert empty["revision"]
    assert empty["commitments"] == []
