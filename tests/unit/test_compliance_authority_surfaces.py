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
import sys
import types
from pathlib import Path

import pytest

from portal.modules.compliance.core import section_index as si
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.reading_assembly import conflicts_for_requirement
from portal.modules.compliance.core.repository import Repository

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
            "ACME procedure",
            "internal",
            "procedure",
            [("4 Records", "Evaluation evidence is retained for 12 calendar months.")],
        )
        _link_all(repo, ["ACME procedure"])
        _project(repo, jurisdictions=("internal",))
    finally:
        repo.close()


class TestContradictionIsRetrievable:
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
