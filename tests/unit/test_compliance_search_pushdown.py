"""Property 1: the clocks filter BEFORE ranking (SUBSTRATE_PROPERTIES_V1 P3).

These tests run the real path — a canonical store, a real LanceDB table
projected from it by ``project_sections``, and ``compliance_search`` building a
``.where()`` predicate that the arms apply under ranking. The first tests are
the regression that motivated the phase: superseded revisions are
near-duplicates of the governing text and rank adjacently, so a blind top-k
could spend every slot on text that no longer governs. On the pre-P3 code (no
pushdown, no supersession predicate) they FAIL — that is the point of them.

Ranking is controlled, not random: the fake embedder hashes the exact embedded
string, so a section whose text equals the query verbatim gets distance 0 and
outranks everything — the deterministic stand-in for a real near-duplicate.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository

si = importlib.import_module("portal.modules.compliance.core.section_index")
compliance_mcp = importlib.import_module("portal.modules.compliance.tools.compliance_mcp")
cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")

DIM = 8
QUERY = "evaluate security patches"


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


def _capture(path: Path, text: str, heading: str = "") -> CapturedDocument:
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text=text,
        units=[
            CapturedUnit(
                ordinal=0,
                unit_kind="prose",
                heading_path=heading,
                title=heading,
                page_start=1,
                page_end=1,
                char_start=0,
                char_end=len(text),
                text=text,
            )
        ],
        extractor="docling",
        reader_strings=(text,),
    )


def _doc(repo: Repository, logical_id: str, jurisdiction: str, kind: str, text: str, **dates):
    repo.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=logical_id,
            issuer="x",
            source_kind=kind,
            jurisdiction=jurisdiction,
        )
    )
    return repo.add_document_revision(
        logical_id, f"/docs/{logical_id}", logical_id.encode() + text.encode(), **dates
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated LanceDB + embedder fakes + a fresh canonical store factory."""
    pytest.importorskip("lancedb")
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", DIM)
    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_embed_batch", _emb_batch)
    monkeypatch.setattr(_embedding, "vl_rerank", _rr)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)
    monkeypatch.setattr(cr, "_PAGES_DIR", tmp_path / "compliance_pages")
    _store._db = None
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")
    fake._read_file = lambda p: "body"
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)

    db_path = tmp_path / "store.db"

    def make():
        return Repository(db_path)

    return {"make": make}


def _project(repo: Repository, jurisdictions=("internal", "US")):
    for j in jurisdictions:
        plan = si.build_plan(repo, jurisdiction=j)
        asyncio.run(cr.project_sections(plan.kb_id, plan.units, rebuild=True))


def _search(monkeypatch, make, **kwargs):
    """compliance_search over the projected fixture; the tool closes its repo in
    a finally, so a fresh Repository is created per call."""
    monkeypatch.setattr(compliance_mcp, "_repo", make)
    return compliance_mcp.compliance_search(**kwargs)


def _revision_of(make, alias: str) -> str:
    repo = make()
    try:
        return repo._conn.execute(
            "SELECT revision_id FROM document_revisions WHERE alias_path = ?", (alias,)
        ).fetchone()[0]
    finally:
        repo.close()


# ── the motivating regression ───────────────────────────────────────────────


class TestSupersededCannotOutrankGoverning:
    def _population(self, make) -> None:
        repo = make()
        try:
            repo.upsert_source_document(
                SourceDocument(
                    logical_id="LSPG/patching",
                    title="patching",
                    issuer="x",
                    source_kind="procedure",
                    jurisdiction="internal",
                )
            )
            # three SUPERSEDED revisions whose sections echo the query verbatim
            for n, (eff, inactive) in enumerate(
                (
                    ("2022-01-01", "2023-01-01"),
                    ("2023-01-01", "2024-01-01"),
                    ("2024-01-01", "2025-01-01"),
                )
            ):
                rev = repo.add_document_revision(
                    "LSPG/patching",
                    f"/docs/v{n}",
                    f"v{n}-bytes".encode(),
                    effective_date=eff,
                    inactive_date=inactive,
                )
                store_capture(repo, rev.revision_id, _capture(Path(f"/docs/v{n}"), QUERY))
            # the governing revision phrases it differently
            new = repo.add_document_revision(
                "LSPG/patching", "/docs/v9", b"v9-bytes", effective_date="2025-01-01"
            )
            store_capture(
                repo,
                new.revision_id,
                _capture(
                    Path("/docs/v9"),
                    "Patch evaluation happens monthly against the approved sources.",
                    heading="3 Patching",
                ),
            )
            _project(repo, jurisdictions=("internal",))
        finally:
            repo.close()

    def test_only_the_current_revision_comes_back_by_default(self, env, monkeypatch) -> None:
        make = env["make"]
        self._population(make)
        out = _search(monkeypatch, make, query=QUERY, jurisdiction="internal", top_k=1)
        governing = _revision_of(make, "/docs/v9")
        assert out["num_results"] == 1
        assert out["results"][0]["revision_id"] == governing
        assert any("superseded" in note for note in out["filter_notes"])

    def test_the_governing_text_survives_near_duplicates_filling_the_keyhole(
        self, env, monkeypatch
    ) -> None:
        make = env["make"]
        self._population(make)
        # even at top_k=3, every slot is the governing document's text: the
        # three echoes were filtered below ranking, not sieved after it
        out = _search(monkeypatch, make, query=QUERY, jurisdiction="internal", top_k=3)
        assert out["num_results"] >= 1
        governing = _revision_of(make, "/docs/v9")
        assert all(r["revision_id"] == governing for r in out["results"])


# ── the clocks, pushed down ─────────────────────────────────────────────────


class TestTheClocksPushDown:
    def _two_revision_store(self, make):
        repo = make()
        try:
            repo.upsert_source_document(
                SourceDocument(
                    logical_id="LSPG/patching",
                    title="patching",
                    issuer="x",
                    source_kind="procedure",
                    jurisdiction="internal",
                )
            )
            old = repo.add_document_revision(
                "LSPG/patching",
                "/docs/old",
                b"old-revision",
                effective_date="2024-01-01",
                inactive_date="2025-06-01",
            )
            store_capture(
                repo,
                old.revision_id,
                _capture(Path("/docs/old"), "The 2024 procedure: patches every 30 days."),
            )
            new = repo.add_document_revision(
                "LSPG/patching", "/docs/new", b"new-revision", effective_date="2025-06-01"
            )
            store_capture(
                repo,
                new.revision_id,
                _capture(Path("/docs/new"), "The 2025 procedure: patches every 35 days."),
            )
            _project(repo, jurisdictions=("internal",))
        finally:
            repo.close()

    def test_valid_at_before_a_revision_returns_the_prior_revision(self, env, monkeypatch):
        make = env["make"]
        self._two_revision_store(make)
        out = _search(
            monkeypatch,
            make,
            query="procedure patches days",
            jurisdiction="internal",
            valid_at="2024-06-01",
            top_k=5,
        )
        assert out["num_results"] >= 1
        assert "2024 procedure" in out["results"][0]["text"]
        assert all("2025 procedure" not in r["text"] for r in out["results"])

    def test_known_at_excludes_the_late_recorded_revision_with_its_reason(
        self, env, monkeypatch
    ) -> None:
        make = env["make"]
        repo = make()
        try:
            repo.upsert_source_document(
                SourceDocument(
                    logical_id="LSPG/patching",
                    title="patching",
                    issuer="x",
                    source_kind="procedure",
                    jurisdiction="internal",
                )
            )
            early = repo.add_document_revision(
                "LSPG/patching", "/docs/early", b"early-bytes", effective_date="2025-01-01"
            )
            store_capture(
                repo, early.revision_id, _capture(Path("/docs/early"), "Early procedure text.")
            )
            late = repo.add_document_revision(
                "LSPG/patching", "/docs/late", b"late-bytes", effective_date="2025-01-01"
            )
            store_capture(
                repo, late.revision_id, _capture(Path("/docs/late"), "Late procedure text.")
            )
            # the store only learned about this revision in December — a
            # September query must not see it
            repo._conn.execute(
                "UPDATE document_revisions SET recorded_from = ? WHERE alias_path = '/docs/late'",
                ("2026-12-01T09:00:00+00:00",),
            )
            repo._conn.commit()
            _project(repo, jurisdictions=("internal",))
        finally:
            repo.close()

        out = _search(
            monkeypatch,
            make,
            query="procedure text",
            jurisdiction="internal",
            # TODAY, derived. The early revision's recorded_from is stamped at
            # ingest, so a literal date here silently stops testing anything the
            # day after it is written -- and then starts failing.
            known_at=datetime.now(UTC).strftime("%Y-%m-%d"),
            top_k=5,
        )
        texts = " ".join(r["text"] for r in out["results"])
        assert "Late procedure" not in texts
        assert "Early procedure" in texts
        assert "UNKNOWN_KNOWLEDGE" in " ".join(out["filter_notes"])

    def test_a_filter_returns_top_k_matching_rows_not_top_k_minus_the_sieve(
        self, env, monkeypatch
    ) -> None:
        make = env["make"]
        repo = make()
        try:
            for n in range(12):
                _doc(
                    repo,
                    f"LSPG/doc{n}",
                    "internal",
                    "procedure" if n % 2 else "policy",
                    f"Document number {n} about patching cadence.",
                )
                revision_id = repo._conn.execute(
                    "SELECT revision_id FROM document_revisions WHERE logical_id = ?",
                    (f"LSPG/doc{n}",),
                ).fetchone()[0]
                store_capture(
                    repo,
                    revision_id,
                    _capture(Path(f"/docs/LSPG/doc{n}"), f"Document number {n} about cadence."),
                )
            _project(repo, jurisdictions=("internal",))
        finally:
            repo.close()
        out = _search(
            monkeypatch,
            make,
            query="document number cadence",
            jurisdiction="internal",
            standard="LSPG/doc",  # matches all 12
            top_k=10,
        )
        assert out["num_results"] == 10
        assert all("LSPG/doc" in r["logical_id"] for r in out["results"])

    def test_standard_narrows_the_search_instead_of_sieving_it(self, env, monkeypatch):
        make = env["make"]
        scored: list[int] = []
        real_search = cr.search

        async def spy(kb_id, query, top_k, *, where=""):
            body = await real_search(kb_id, query, top_k, where=where)
            scored.append(int(body.get("num_results", 0)))
            return body

        monkeypatch.setattr(cr, "search", spy)

        repo = make()
        try:
            for n in range(5):
                logical = f"NERC/CIP-007-6 doc{n}"
                revision = _doc(
                    repo, logical, "US", "regulatory_standard", f"Standard text number {n}."
                )
                store_capture(
                    repo,
                    revision.revision_id,
                    _capture(Path(f"/docs/{logical}"), f"Standard text number {n}."),
                )
                logical2 = f"LSPG/other{n}"
                revision2 = _doc(
                    repo, logical2, "internal", "procedure", f"Operator text number {n}."
                )
                store_capture(
                    repo,
                    revision2.revision_id,
                    _capture(Path(f"/docs/{logical2}"), f"Operator text number {n}."),
                )
            _project(repo, jurisdictions=("internal", "US"))
        finally:
            repo.close()

        out = _search(monkeypatch, make, query="text number", standard="CIP-007-6", top_k=10)
        # the arms SCORED only the five matching candidates — a sieve would
        # have scored ten and thrown half away after ranking
        assert sum(scored) == 5
        assert all("CIP-007-6" in r["logical_id"] for r in out["results"])


# ── injection, and what the caller is told ──────────────────────────────────


class TestTheCallerCanSeeWhatRan:
    def test_a_quoted_standard_is_data_not_a_clause(self, env, monkeypatch) -> None:
        make = env["make"]
        repo = make()
        try:
            revision = _doc(repo, "LSPG/doc0", "internal", "procedure", "Harmless text.")
            store_capture(
                repo, revision.revision_id, _capture(Path("/docs/LSPG/doc0"), "Harmless text.")
            )
            _project(repo, jurisdictions=("internal",))
        finally:
            repo.close()
        out = _search(
            monkeypatch,
            make,
            query="harmless",
            jurisdiction="internal",
            standard="LSPG/doc0' OR 1=1 --",
            top_k=5,
        )
        # the call returned (no raise), and the fragment stayed a quoted value
        assert out["num_results"] == 0
        assert "LSPG/doc0'' OR 1=1 --" in out["filter_applied"]

    def test_filter_applied_is_the_clause_that_ran(self, env, monkeypatch) -> None:
        make = env["make"]
        repo = make()
        try:
            revision = _doc(repo, "LSPG/doc0", "internal", "procedure", "Some text.")
            store_capture(
                repo, revision.revision_id, _capture(Path("/docs/LSPG/doc0"), "Some text.")
            )
            _project(repo, jurisdictions=("internal",))
        finally:
            repo.close()
        out = _search(
            monkeypatch,
            make,
            query="text",
            jurisdiction="internal",
            standard="LSPG/doc0",
            layer="procedure",
            valid_at="2026-01-01",
            known_at="2026-06-01",
            top_k=5,
        )
        clause = out["filter_applied"]
        assert "logical_id LIKE '%LSPG/doc0%'" in clause
        assert "source_kind LIKE '%procedure%'" in clause
        assert "effective_from <= '2026-01-01'" in clause
        assert "recorded_to > '2026-06-01'" in clause
        assert out["filter_report"], "per-corpus arm report is carried"
        assert out["excluded_meaning"].startswith("hits that do not resolve")
