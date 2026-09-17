"""Property 2: authority tiers have precedence, and contradiction is a
retrievable fact (SUBSTRATE_PROPERTIES_V1 P4).

Tier is a property of a SECTION — projected from what was RECORDED about its
document, never defaulted — and a cross-tier contradiction is emitted, with
both sides addressable, and never reconciled. The reading path (search hits,
reads, the assembly) now carries what the verdict engine used to hoard.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from portal.modules.compliance.core import section_index as si
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.reading_assembly import conflicts_for_requirement
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.tiers import recorded_tier
from portal.modules.compliance.tools import compliance_mcp

cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")
ingest = importlib.import_module("portal.modules.compliance.core.ingest")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")

DIM = 8


def _vec(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [((digest[i] / 255.0) - 0.5) for i in range(DIM)]


async def _emb(text=None, image_path=None, is_query=False):
    return _vec(text or image_path or "")


async def _emb_batch(items):
    return [_vec(i.get("text") or i.get("image_path") or "") for i in items]


async def _rr(_q, cands, _n):
    return [{"index": i, "score": 1.0 - i * 0.1} for i in range(len(cands))]


async def _model_id():
    return ("fake-vl-model", DIM)


def _capture(
    path: Path,
    bodies: list[tuple[str, str]],
    unit_kind: str = "prose",
) -> CapturedDocument:
    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for ordinal, (heading, body) in enumerate(bodies):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind=unit_kind,
                heading_path=heading,
                title=heading,
                page_start=ordinal + 1,
                page_end=ordinal + 1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=len(bodies),
        full_text="".join(buf),
        units=units,
        extractor="docling",
        reader_strings=tuple(b for _h, b in bodies),
    )


def _doc(
    repo: Repository,
    logical_id: str,
    jurisdiction: str,
    kind: str,
    bodies: list[tuple[str, str]],
    unit_kind: str = "prose",
    **dates,
):
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=logical_id,
            issuer="x",
            source_kind=kind,
            jurisdiction=jurisdiction,
        )
    )
    revision = repo.add_document_revision(
        logical_id, f"/docs/{logical_id}", logical_id.encode(), **dates
    )
    store_capture(
        repo, revision.revision_id, _capture(Path(f"/docs/{logical_id}"), bodies, unit_kind)
    )
    return revision


def _link(repo: Repository, ref: str, section_id: str) -> None:
    repo.propose_relationship(
        RelationshipAssertion(
            assertion_id="",
            relation_type="IMPLEMENTS",
            src_ref=ref,
            src_revision_id=None,
            dst_ref=section_id,
            dst_revision_id=None,
            scope="",
            citations=[],
            status="proposed",
            review_state="proposed",
            coverage="",
            proposed_coverage="",
            confidence=0.9,
        )
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", DIM)
    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_embed_batch", _emb_batch)
    monkeypatch.setattr(_embedding, "vl_rerank", _rr)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)
    monkeypatch.setattr(cr, "_PAGES_DIR", tmp_path / "compliance_pages")
    # no sidecar: tiers come from the doc-class table alone in this fixture
    monkeypatch.setattr(ingest, "LAYER_SIDECAR", tmp_path / "absent_sidecar.json")
    _store._db = None
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")
    fake._read_file = lambda p: "body"
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)

    db_path = tmp_path / "store.db"

    def make():
        return Repository(db_path)

    return {"make": make}


def _project(repo: Repository, jurisdictions=("internal",)) -> None:
    for j in jurisdictions:
        plan = si.build_plan(repo, jurisdiction=j)
        asyncio.run(cr.project_sections(plan.kb_id, plan.units, rebuild=True))


REF = "CIP-007-6 R2 Part 2.2"


def _link_all(repo: Repository, logicals: list[str]) -> None:
    for logical in logicals:
        row = repo._conn.execute(
            "SELECT section_id FROM source_sections WHERE revision_id = ("
            "SELECT revision_id FROM document_revisions WHERE logical_id = ?)",
            (logical,),
        ).fetchone()
        _link(repo, REF, str(row[0]))


def _conflict_population(make):
    """A standard (its requirement row carries no number) plus three linked
    operator documents: a policy (tier 2) and a work instruction (tier 3) with
    INCOMPATIBLE cadences, and an untiered plan."""
    repo = make()
    try:
        _doc(
            repo,
            "NERC/CIP-007-6",
            "US",
            "regulatory_standard",
            [
                (
                    "B. Requirements and Measures",
                    "2.2 | High Impact | The Responsible Entity evaluates security patches.",
                ),
                (
                    "B. Requirements and Measures",
                    "M2 | Retain evaluation evidence for 15 calendar months.",
                ),
            ],
            unit_kind="table_row",
        )
        _doc(
            repo,
            "LSPG policy",
            "internal",
            "policy",
            [("1 Purpose", "Security patches are evaluated every 30 calendar days.")],
        )
        _doc(
            repo,
            "LSPG work instruction",
            "internal",
            "work_instruction",
            [("1 Steps", "Security patches are evaluated every 45 calendar days.")],
        )
        _doc(
            repo,
            "LSPG plan",
            "internal",
            "plan",  # not a class the tier table names — no recorded tier
            [("1 Plan", "Patching governance is documented here.")],
        )
        _link_all(repo, ["LSPG policy", "LSPG work instruction", "LSPG plan"])
        _project(repo, jurisdictions=("internal",))
    finally:
        repo.close()


def _measures_population(make):
    """The coverage.py:550 shape in isolation: the standard's own Measures quote
    a cadence that an operator procedure contradicts — while the requirement
    rows themselves carry no number. Pooling the Measures would fabricate the
    standard 'disagreeing' with its own example evidence."""
    repo = make()
    try:
        _doc(
            repo,
            "NERC/CIP-007-6",
            "US",
            "regulatory_standard",
            [
                (
                    "B. Requirements and Measures",
                    "2.2 | High Impact | The Responsible Entity evaluates security patches.",
                ),
                (
                    "B. Requirements and Measures",
                    "M2 | Retain evaluation evidence for 15 calendar months.",
                ),
            ],
            unit_kind="table_row",
        )
        _doc(
            repo,
            "LSPG procedure",
            "internal",
            "procedure",
            [("4 Records", "Evaluation evidence is retained for 12 calendar months.")],
        )
        _link_all(repo, ["LSPG procedure"])
        _project(repo, jurisdictions=("internal",))
    finally:
        repo.close()


# ── contradiction is retrievable ────────────────────────────────────────────


class TestContradictionIsRetrievable:
    def test_incompatible_cadences_produce_one_conflict_with_both_sides(self, env) -> None:
        make = env["make"]
        _conflict_population(make)
        repo = make()
        try:
            out = conflicts_for_requirement(repo, REF)
        finally:
            repo.close()
        real = [c for c in out["conflicts"] if c.get("signal") == "COMPLIANCE_CONFLICT"]
        assert len(real) == 1
        conflict = real[0]
        assert conflict["kind"] == "quantitative"
        # both tiers, both section ids, and NO reconciliation
        hi = conflict["higher_authority"]
        lo = conflict["lower_authority"]
        assert {hi["tier"], lo["tier"]} == {2, 3}
        assert hi["tier_name"] == "policy" and lo["tier_name"] == "procedure"
        assert hi["citation"] and lo["citation"]
        assert "NOT reconciled" in conflict["resolution"]
        # both sides addressable through the reported sections
        assert set(conflict["sections"].values()) == {hi["citation"], lo["citation"]}

    def test_the_standard_quoting_its_own_measures_fires_nothing(self, env) -> None:
        """The coverage.py:550 false-positive shape: the Measures cell says 15
        calendar months, an operator procedure says 12 — pooling the Measures as
        a standard-side span would flag the standard 'disagreeing' with its own
        example evidence. The requirement rows carry no number here, so a
        correctly-scoped pool finds nothing at all — while the Measures text is
        provably in the document."""
        make = env["make"]
        _measures_population(make)
        repo = make()
        try:
            out = conflicts_for_requirement(repo, REF)
            revision_id = repo._conn.execute(
                "SELECT revision_id FROM document_revisions WHERE logical_id = 'NERC/CIP-007-6'"
            ).fetchone()[0]
            body = repo.get_document_text(revision_id) or ""
            measures = 1 if "15 calendar months" in body else 0
        finally:
            repo.close()
        assert measures >= 1, "fixture sanity: the Measures text is in the capture"
        assert out["conflicts"] == []

    def test_an_untiered_document_is_visible_never_ranked(self, env) -> None:
        make = env["make"]
        _conflict_population(make)
        repo = make()
        try:
            out = conflicts_for_requirement(repo, REF)
            plan_sections = repo._conn.execute(
                "SELECT section_id FROM source_sections s "
                "JOIN document_revisions r USING(revision_id) WHERE logical_id = 'LSPG plan'"
            ).fetchall()
            resolved = si.resolve_sections(repo, [str(r[0]) for r in plan_sections])
            assert resolved, "fixture sanity: the plan document has projected sections"
            assert all(e["authority_tier"] == "" for e in resolved.values())
        finally:
            repo.close()
        assert out["untiered_sections"], "the untiered document is named"
        assert len(out["untiered_sections"]) == 1

    def test_recorded_tier_precedence(self, tmp_path, monkeypatch) -> None:
        sidecar = tmp_path / "sidecar.json"
        sidecar.write_text(json.dumps({"LSPG/doc.pdf": {"tier": 3}}))
        monkeypatch.setattr(ingest, "LAYER_SIDECAR", sidecar)
        # sidecar record wins
        assert recorded_tier("LSPG/doc.pdf", "policy") == "3"
        # no sidecar entry: the doc-class table, exact hits only
        assert recorded_tier("LSPG/other.pdf", "policy") == "2"
        assert recorded_tier("NERC/x", "regulatory_standard") == "0"
        # a class the table does not name has NO recorded tier — never a default
        assert recorded_tier("LSPG/plan.pdf", "plan") == ""
        assert recorded_tier("x", "operator_note") == ""


# ── the tier rides on every surface ─────────────────────────────────────────


class TestTheTierRidesOnEveryHit:
    def test_every_search_hit_carries_a_tier_field(self, env, monkeypatch) -> None:
        make = env["make"]
        _conflict_population(make)
        monkeypatch.setattr(compliance_mcp, "_repo", make)
        out = compliance_mcp.compliance_search(
            query="patches evaluated calendar days", jurisdiction="internal", top_k=5
        )
        assert out["num_results"] >= 1
        for hit in out["results"]:
            assert "authority_tier" in hit
            assert hit["authority_tier"] in ("", "0", "1", "2", "3", "4")
        tiers = {hit["authority_tier"] for hit in out["results"]}
        assert "" in tiers, "the untiered plan document must be visible as untiered"
        assert "2" in tiers and "3" in tiers

    def test_conflicts_enter_the_full_assembly(self, env) -> None:
        from portal.modules.compliance.core import reading_assembly

        make = env["make"]
        _conflict_population(make)
        repo = make()
        try:
            assembled = reading_assembly.assemble(repo, REF, include=["requirement", "conflicts"])
        finally:
            repo.close()
        names = [c["component"] for c in assembled["components"]]
        assert "conflicts" in names
        conflicts_component = next(
            c for c in assembled["components"] if c["component"] == "conflicts"
        )
        assert conflicts_component["sections"], "the known contradiction rides with the reading"
        entry = conflicts_component["sections"][0]
        assert entry["conflict"]["signal"] == "COMPLIANCE_CONFLICT"


class TestEdgesResolveInBothRecordedShapes:
    """Defect found wiring P4 (live store): mapping_store writes edge endpoints
    as ``{document}::{section_id}`` while the reading path resolved the raw
    value — on the live store every ``::``-shaped edge resolved to nothing and
    only bare section-id edges reached the reading."""

    def test_a_doc_colon_colon_section_edge_resolves_to_its_section(self, env) -> None:
        make = env["make"]
        repo = make()
        try:
            revision = _doc(
                repo,
                "LSPG procedure",
                "internal",
                "procedure",
                [("4 Records", "Evaluation evidence is retained for 12 calendar months.")],
            )
            section_id = repo._conn.execute(
                "SELECT section_id FROM source_sections WHERE revision_id = ?",
                (revision.revision_id,),
            ).fetchone()[0]
            repo.propose_relationship(
                RelationshipAssertion(
                    assertion_id="",
                    relation_type="IMPLEMENTS",
                    src_ref=REF,
                    src_revision_id=None,
                    dst_ref=f"LSPG procedure.pdf::{section_id}",
                    dst_revision_id=None,
                    scope="",
                    citations=[],
                    status="proposed",
                    review_state="proposed",
                    coverage="",
                    proposed_coverage="",
                    confidence=0.9,
                )
            )
            from portal.modules.compliance.core.reading_assembly import linked_internal

            linked = linked_internal(repo, REF)
        finally:
            repo.close()
        assert len(linked) == 1
        assert linked[0]["text"].startswith("Evaluation evidence")
