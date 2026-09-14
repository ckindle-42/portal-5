"""T4 — the change pipeline verification suite (Phases 7).

Tier 0: invariants. Tier 1: the real CIP-003-8 -> CIP-003-9 transition. Tier 2:
planted change controls. Change-detection recall is the headline (a missed
change is a silently stale policy); cosmetic false-positive rate is reported
beside it, never averaged.
"""

from __future__ import annotations

import hashlib
from typing import Any

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.change_pipeline import (
    draft_revisions,
    expire_mappings,
    impact_report,
    prospective_report,
)
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.modules.compliance.core.register_diff import diff_standard, diff_summary

reg = Register.load()
_OLD = Register(nodes=[n for n in reg.nodes if n.standard == "CIP-003-8"], edges=[])
_NEW = Register(nodes=[n for n in reg.nodes if n.standard == "CIP-003-9"], edges=[])
_SCOPE = AssetScope(
    impact_present={"high", "medium", "low"},
    associated_present={"eacms", "pacs", "pca"},
    declared_by="op",
    declared_at="2026-09-03",
)


def _mk(
    part,
    text,
    *,
    vrf="Medium",
    appsys="high impact and medium impact BES Cyber Systems",
    measure="",
):
    return RegisterNode(
        id=f"X {part}",
        standard="X-1",
        version="1",
        requirement="R1",
        part=part,
        verbatim_text=text,
        measure_text=measure,
        applicable_systems=appsys,
        table_name="T",
        vrf=vrf,
        time_horizon="OP",
        lifecycle_state="EFFECTIVE",
        valid_from=None,
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="x.pdf",
        source_pages=[],
        recorded_at=0.0,
        granularity="part",
    )


def _diff(old_nodes, new_nodes):
    return diff_standard(
        Register(nodes=old_nodes, edges=[]), Register(nodes=new_nodes, edges=[]), "X"
    )


# ── Tier 0: invariants ────────────────────────────────────────────────────
def test_every_diff_row_carries_both_spans():
    rows = diff_standard(_OLD, _NEW, "CIP-003")
    for r in rows:
        assert isinstance(r.old_span, str) and isinstance(r.new_span, str)
        if r.change_type == "PART_ADDED":
            assert r.new_span and not r.old_span
        elif r.change_type == "PART_REMOVED":
            assert r.old_span and not r.new_span
        else:
            assert r.old_span and r.new_span


def test_a_mapping_never_inherits_a_verdict_across_a_language_change(tmp_path):
    store = MappingStore(tmp_path / "m.json")
    mp = store.propose("CIP-003-8 R1 Part 1.2.6", "OT-POL", "§1", "FULL")
    store.approve(mp.id, "sme")
    expire_mappings(store, diff_standard(_OLD, _NEW, "CIP-003"), "2024-04-01")
    # the FULL mapping is closed; its successor is NEEDS_REVIEW, not FULL
    successors = [m for m in store._rows if m.source == "successor_of_expired"]
    assert successors and all(m.coverage == "NEEDS_REVIEW" for m in successors)
    assert store._by_id(mp.id).valid_to == "2024-04-01"


def test_prospective_output_is_marked_and_never_a_today_obligation():
    pr = prospective_report(reg, _SCOPE, "2024-06-01")
    assert pr["n_future_effective"] >= 1
    assert all(r["prospective"] is True for r in pr["rows"])
    assert "MUST NOT reach" in pr["segregation"]


# ── Tier 1: the real transition ──────────────────────────────────────────
def test_cip_003_8_to_9_produces_the_known_changes():
    rows = diff_standard(_OLD, _NEW, "CIP-003")
    types = {(r.change_type, r.part_id_new) for r in rows}
    # old 1.2.6 ("CIP Exceptional Circumstances") shifted to new 1.2.7
    assert ("RENUMBERED", "CIP-003-9 R1 Part 1.2.7") in types
    # new 1.2.6 now carries "Vendor electronic remote access security controls"
    lang = next(r for r in rows if r.part_id_new == "CIP-003-9 R1 Part 1.2.6")
    assert lang.change_type == "LANGUAGE_CHANGED" and lang.sub_type == "substantive"
    assert "Vendor electronic remote access" in lang.new_span
    # the U+2010 hyphen churn on 1.1.x is cosmetic, not raised as an obligation change
    s = diff_summary(rows)
    assert s["cosmetic"] >= 5
    assert all(r.to_dict()["substantive"] or r.sub_type == "cosmetic" for r in rows)


# ── Tier 2: planted change controls ──────────────────────────────────────
def test_explicit_and_implicit_change_both_detected():
    old = [_mk("1.1", "Review the access list at least once every 15 calendar months.")]
    new = [_mk("1.1", "Review the access list at least once every 12 calendar months.")]
    rows = _diff(old, new)
    assert len(rows) == 1 and rows[0].change_type == "TIMELINE_CHANGED"


def test_modality_change_typed_as_modality_not_wording():
    old = [_mk("1.1", "The entity shall encrypt data in transit.")]
    new = [_mk("1.1", "The entity should encrypt data in transit.")]
    rows = _diff(old, new)
    assert rows[0].change_type == "LANGUAGE_CHANGED" and rows[0].sub_type == "modality"


def test_timeline_change_is_substantive():
    old = [_mk("1.1", "install the patch within 35 calendar days")]
    new = [_mk("1.1", "install the patch within 15 calendar days")]
    r = _diff(old, new)[0]
    assert r.change_type == "TIMELINE_CHANGED" and r.to_dict()["substantive"]
    assert "35" in r.detail and "15" in r.detail


def test_cosmetic_change_is_not_raised_as_an_obligation_change():
    old = [_mk("1.1", "Cyber security awareness (per CIP-004);")]
    new = [_mk("1.1", "Cyber security awareness (per CIP‐004)")]  # U+2010 + no semicolon
    rows = _diff(old, new)
    assert len(rows) == 1
    assert rows[0].sub_type == "cosmetic" and not rows[0].to_dict()["substantive"]


def test_renumber_is_paired_and_high_confidence_or_needs_review():
    old = [_mk("1.5", "Transient Cyber Assets and Removable Media malicious code risk mitigation")]
    new = [_mk("1.6", "Transient Cyber Assets and Removable Media malicious code risk mitigation")]
    r = _diff(old, new)[0]
    assert r.change_type == "RENUMBERED" and r.sub_type == "paired" and r.confidence >= 0.9
    # a low-similarity pair is not silently mispaired
    old2 = [_mk("1.5", "Physical access controls at the perimeter")]
    new2 = [_mk("1.6", "Cyber Security Incident response coordination with the ERO")]
    rows2 = _diff(old2, new2)
    assert {r.change_type for r in rows2} == {"PART_ADDED", "PART_REMOVED"}


def test_inapplicable_change_is_informational_not_work(tmp_path):
    old = [
        _mk("1.1", "old text about medium impact only", appsys="Medium Impact BES Cyber Systems")
    ]
    new = [
        _mk("1.1", "new text about medium impact only", appsys="Medium Impact BES Cyber Systems")
    ]
    high_only = AssetScope(impact_present={"high"}, declared_by="op", declared_at="x")
    ir = impact_report(
        Register(nodes=old, edges=[]),
        Register(nodes=new, edges=[]),
        "X",
        high_only,
        MappingStore(tmp_path / "m.json"),
    )
    assert ir["work_items"] == 0 and ir["informational"] == 1


def test_mapping_expiry_completeness(tmp_path):
    store = MappingStore(tmp_path / "m.json")
    # 1.2.5 changed only its trailing list conjunction (cosmetic); 1.2.6 changed
    # meaning AND was renumbered to 1.2.7. Only the 1.2.6 mapping expires.
    for pid in ("CIP-003-8 R1 Part 1.2.5", "CIP-003-8 R1 Part 1.2.6"):
        mp = store.propose(pid, "OT-POL-003", "§x", "FULL")
        store.approve(mp.id, "sme")
    res = expire_mappings(store, diff_standard(_OLD, _NEW, "CIP-003"), "2024-04-01")
    assert res["n_expired"] == 1
    assert res["n_successors_needs_review"] == 1
    assert store._by_id(store.all_for("CIP-003-8 R1 Part 1.2.5")[0].id).valid_to is None


def _seeded_store(tmp_path):
    """A mapping store this test owns.

    ``impact_report`` fills ``mapped_sections`` from ``store.all_for(...)``. With
    no ``store=`` it constructs ``MappingStore()`` at the gitignored ``STORE_PATH``
    — machine-local state. On a developer box that store is populated and these
    tests pass; on a clean checkout (CI, or a fresh clone) it is empty, every row
    gets zero mapped sections, and ``draft_revisions`` returns no specifications.
    That is P5-CI-DRAFT-REVISIONS-FLAKE-001: not a CI-runner effect, a fixture
    that asserted on ambient state.
    """
    store = MappingStore(tmp_path / "mappings.db")
    mapping = store.propose("CIP-003-9 R1 Part 1.2.6", "LSPG-CIP-003-POLICY", "4.2", "FULL")
    store.approve(mapping.id, "sme-fixture")
    return store


def test_impact_report_ignores_ambient_machine_state(tmp_path):
    """The regression guard: an empty store must produce zero specifications.

    If this ever passes with specifications, something reintroduced a default
    store read and the suite is once again machine-dependent. It guards the
    ``store or MappingStore()`` defect specifically: ``MappingStore`` defines
    ``__len__``, so an empty store is falsy and that idiom silently swapped the
    injected store for the ambient one — leaving the seam working only for a
    populated store, which is the one case it is not needed for.
    """
    empty = MappingStore(tmp_path / "empty.db")
    ir = impact_report(_OLD, _NEW, "CIP-003", _SCOPE, empty)
    assert ir["examined"] == 6
    assert ir["substantively_resolved"] == 0
    assert draft_revisions(ir)["specifications"] == []


def test_impact_report_examined_and_resolved_are_separate_numbers(tmp_path):
    ir = impact_report(_OLD, _NEW, "CIP-003", _SCOPE, _seeded_store(tmp_path))
    assert ir["examined"] == 6 and ir["substantively_resolved"] == 1
    assert "examined" in ir and "substantively_resolved" in ir
    assert ir["examined"] >= ir["substantively_resolved"]


# ── Phase 6 proposal workflow ───────────────────────────────────────────
def test_draft_revisions_is_proposal_by_default(tmp_path):
    ir = impact_report(_OLD, _NEW, "CIP-003", _SCOPE, _seeded_store(tmp_path))
    dr = draft_revisions(ir)
    assert dr["mode"] == "draft_as_proposal"
    assert all(s["drafted_replacement"] for s in dr["specifications"])
    assert dr["review_decision_kind"] == "S03_ACCEPT_PROPOSED_REDLINE"
    # the old hardcoded SUPPORTED receipt is gone: with no resolving edit
    # target / pinned snapshot the draft is honestly unvalidated.
    assert dr["specifications"]
    assert all(s["reassessment"]["status"] == "UNVALIDATED" for s in dr["specifications"])
    assert not any(s["reassessment"]["closes_own_gap"] for s in dr["specifications"])
    assert all(s["reassessment"]["after"] is None for s in dr["specifications"])


def _draft_inputs(*, weak: str, strong: str) -> tuple[dict, dict, dict]:
    from portal.modules.compliance.core.determination import (
        AssessmentRequest,
        CandidateRecord,
        CandidateSet,
        CorpusSnapshot,
        GoverningBundle,
        ScenarioEdit,
        SourceSlice,
    )

    def _sha(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    request = AssessmentRequest(
        requirement_id="X R1 Part 1.1",
        scope=AssetScope(impact_present={"high"}, declared_by="op", declared_at="x"),
        governing=GoverningBundle(
            ref="X R1 Part 1.1",
            part_text="Each entity shall evaluate patches.",
            lead_in="Each entity shall implement each of the following Parts:",
            source_slices=[
                SourceSlice(
                    slice_id="gov-1",
                    ref="register:x",
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
        candidate_set=CandidateSet(
            records=[
                CandidateRecord(
                    candidate_id="c1",
                    document_id="OT-POL",
                    chunk_id="ch-1",
                    text=weak,
                    source_slice=SourceSlice(
                        slice_id="cand-c1",
                        ref="OT-POL#1",
                        document_id="OT-POL",
                        revision_hash=_sha(weak),
                        chunk_id="ch-1",
                        text=weak,
                        role="candidate",
                    ),
                )
            ]
        ),
    )
    impact = {
        "impact_rows": [
            {
                "classification": "work",
                "changed_part": "X R1 Part 1.1",
                "change_type": "LANGUAGE_CHANGED",
                "old_span": "old",
                "new_span": "Evaluate patches at least once every 35 calendar days.",
                "mapped_sections": [
                    {"document_id": "OT-POL", "section_id": "1.1", "prior_coverage": "PARTIAL"}
                ],
            }
        ]
    }
    edit = ScenarioEdit(
        operation="REPLACE",
        target_document="OT-POL",
        chunk_id="ch-1",
        char_start=0,
        char_end=len(weak),
        expected_old_hash=_sha(weak),
        new_text=strong,
    )
    return impact, request, edit


def _staged_seat() -> Any:
    import json

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
                                "missing_commitment": "35 day cadence",
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


def _ctx() -> Any:
    from portal.modules.compliance.core.determination import AssessmentContext

    seats = [{"id": f"s{i}", "label": str(i), "model": f"m{i}"} for i in range(3)]
    return AssessmentContext(seats=seats, quorum=0.66, seat_fn=_staged_seat(), kb_id="kb")


WEAK = "SMEs shall evaluate patch applicability once every 40 calendar days."
STRONG = "SMEs shall evaluate patch applicability once every 35 calendar days."


def test_draft_revisions_validates_an_actual_closing_overlay():
    impact, request, edit = _draft_inputs(weak=WEAK, strong=STRONG)
    dr = draft_revisions(
        impact,
        context=_ctx(),
        requests_by_part={"X R1 Part 1.1": request},
        edits_by_section={("OT-POL", "1.1"): edit},
    )
    rea = dr["specifications"][0]["reassessment"]
    assert rea["status"] == "VALIDATED"
    assert rea["after"] == "FULL"
    assert rea["closes_own_gap"] is True
    assert rea["method"] == "overlay re-judgment through operations.propose"
    assert dr["n_validated"] == 1


def test_draft_revisions_prose_quote_is_not_a_hardcoded_supported():
    """A patch quoting the governing text inside descriptive prose does not
    close the still-open weaker rule: the overlay re-judgment fails."""
    impact, request, _ = _draft_inputs(weak=WEAK, strong=STRONG)
    prose = (
        "The responsible owner shall implement and retain evidence of the following "
        "requirement: evaluate patches at least once every 35 calendar days."
    )
    additive = {
        "operation": "ADD",
        "target_document": "OT-POL",
        "target_section": "1.1",
        "new_text": prose,
        "label": "legacy-add",
    }
    dr = draft_revisions(
        impact,
        context=_ctx(),
        requests_by_part={"X R1 Part 1.1": request},
        edits_by_section={("OT-POL", "1.1"): additive},
    )
    rea = dr["specifications"][0]["reassessment"]
    assert rea["status"] == "FAILED_VALIDATION"
    assert rea["after"] != "SUPPORTED"
    assert rea["closes_own_gap"] is False
    assert rea["weakened_obligations"]
    assert dr["n_failed_validation"] == 1


# ── materialization: default is source-only; assessment is explicit opt-in ──
def _load_materializer():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "materialize_compliance_v3.py"
    spec = importlib.util.spec_from_file_location("materialize_compliance_v3", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_materialize_default_emits_no_verdict(tmp_path, monkeypatch):
    import inspect

    module = _load_materializer()
    assert inspect.signature(module.materialize).parameters["assess"].default is False
    # the retired verdict machinery is gone from the module
    assert not hasattr(module, "assess_atom")
    assert not hasattr(module, "BoundarySearch")


def test_materialize_default_run_emits_no_claims(tmp_path, monkeypatch):
    from portal.modules.compliance.core.cip_register import Register, RegisterNode
    from portal.modules.compliance.core.repository import Repository

    module = _load_materializer()
    node = RegisterNode(
        id="TEST-1 R1 Part 1.1",
        standard="TEST-1",
        version="1",
        requirement="R1",
        part="1.1",
        verbatim_text="Do the thing.",
        measure_text="",
        applicable_systems="High Impact BES Cyber Systems",
        table_name="",
        vrf="",
        time_horizon="",
        lifecycle_state="EFFECTIVE",
        valid_from="2020-01-01",
        valid_to=None,
        supersedes=None,
        superseded_by=None,
        authority_tier=0,
        source_pdf="",
        source_pages=[],
        recorded_at=0.0,
        granularity="part",
    )
    monkeypatch.setattr(
        module, "Register", type("R", (), {"load": staticmethod(lambda: Register(nodes=[node]))})
    )
    monkeypatch.setattr(module, "effective_parts", lambda reg, valid_at: [node])
    monkeypatch.setattr(module, "read_sidecar", lambda: {})
    monkeypatch.setattr(module, "_pdf_text", lambda path: "policy text")
    monkeypatch.setattr(module, "classify_document", lambda text: "policy")
    monkeypatch.setattr(module, "extract_assertions", lambda *a, **k: [])
    monkeypatch.setattr(module, "_anchor", lambda *a, **k: "span-1")
    monkeypatch.setattr(module, "_insert_relationship", lambda *a, **k: None)

    corpus = tmp_path / "corpus"
    (corpus / "TEST-1").mkdir(parents=True)
    (corpus / "TEST-1" / "a.pdf").write_bytes(b"x")
    repo = Repository(tmp_path / "materialize.db")
    counts = module.materialize(corpus, "2026-09-12", repository=repo, assess=False)
    assert counts["engine"] == "v3-source-materialization"
    assert counts["emits_coverage_claims"] is False
    assert counts["claims_emitted"] == 0


def test_materialize_assessment_requires_explicit_opt_in(tmp_path, monkeypatch):
    module = _load_materializer()
    captured: dict = {}

    def fake_materialize(corpus, valid_at, **kwargs):
        captured.update(kwargs)
        return {"anchor_failures": [], "foreign_key_violations": []}

    monkeypatch.setattr(module, "materialize", fake_materialize)
    assert module.main(["--corpus", str(tmp_path), "--valid-at", "2026-09-12"]) == 0
    assert captured["assess"] is False
    captured.clear()
    assert module.main(["--corpus", str(tmp_path), "--valid-at", "2026-09-12", "--assess"]) == 0
    assert captured["assess"] is True
