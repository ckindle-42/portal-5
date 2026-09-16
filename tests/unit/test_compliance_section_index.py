"""One identity space (BILATERAL_CORPUS_V1 P4).

The defect this phase corrects is that a search hit and a canonical section came
from different id spaces, so ``set(examined_sections) == {chunk_id}`` could never
pass. These tests build a real store, project it, and check the identity holds in
both directions — including the direction where it must NOT: a withheld section
makes the boundary incomplete.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import section_index as si
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository


def _capture(
    path: Path, bodies: list[tuple[str, str]], extractor: str = "docling"
) -> CapturedDocument:
    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for ordinal, (heading, body) in enumerate(bodies):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="prose",
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
        extractor=extractor,
        reader_strings=tuple(b for _h, b in bodies),
    )


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    for logical_id, jurisdiction, kind, bodies in (
        (
            "NERC/CIP-007-6",
            "US",
            "regulatory_standard",
            [
                ("B. Requirements and Measures", "Patch each applicable system within 35 days."),
                ("Guidelines and Technical Basis", "The intent is to know, track and mitigate."),
                ("Version History", "Version 5 revised to use RBS Template."),
            ],
        ),
        (
            "LSPG/patching",
            "internal",
            "procedure",
            [
                ("3 Patching", "Patches are evaluated every 40 days by the OT team."),
                ("4 Evidence", "Evidence is retained in the change record."),
            ],
        ),
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
            logical_id, f"/docs/{logical_id}.pdf", logical_id.encode()
        )
        store_capture(repo, revision.revision_id, _capture(Path(f"/docs/{logical_id}.pdf"), bodies))
    yield repo
    repo.close()


class TestOneIdentitySpace:
    def test_a_unit_is_addressed_by_its_section_id(self, store: Repository) -> None:
        plan = si.build_plan(store, jurisdiction="US")
        section_ids = {
            r[0]
            for r in store._conn.execute(
                "SELECT section_id FROM source_sections WHERE char_start >= 0"
            )
        }
        assert {u.chunk_id for u in plan.units} <= section_ids
        assert set(plan.examined_sections) <= section_ids

    def test_every_projected_id_resolves_back_to_a_section(self, store: Repository) -> None:
        plan = si.build_plan(store, jurisdiction="US")
        resolved = si.resolve_sections(store, [u.chunk_id for u in plan.units])
        assert len(resolved) == len(plan.examined_sections)
        assert all(entry["resolvable"] for entry in resolved.values())

    def test_resolved_text_is_the_verbatim_span(self, store: Repository) -> None:
        plan = si.build_plan(store, jurisdiction="US")
        resolved = si.resolve_sections(store, plan.examined_sections)
        by_text = {e["text"].strip() for e in resolved.values()}
        assert "Patch each applicable system within 35 days." in by_text
        assert "Version 5 revised to use RBS Template." in by_text

    def test_an_unresolvable_id_is_absent_never_invented(self, store: Repository) -> None:
        assert si.resolve_sections(store, ["csection-doesnotexist"]) == {}

    def test_both_jurisdictions_project_into_their_own_corpus(self, store: Repository) -> None:
        assert si.build_plan(store, jurisdiction="US").kb_id == "nerc_corpus"
        assert si.build_plan(store, jurisdiction="internal").kb_id == "operator_corpus"


class TestSplittingIsNotANewIdentity:
    def test_a_long_section_splits_into_ordered_sub_units(self, tmp_path: Path) -> None:
        repo = Repository(tmp_path / "long.db")
        try:
            repo.upsert_source_document(
                SourceDocument(
                    logical_id="LSPG/long",
                    title="long",
                    issuer="x",
                    source_kind="procedure",
                    jurisdiction="internal",
                )
            )
            revision = repo.add_document_revision("LSPG/long", "/docs/long.pdf", b"long")
            body = ". ".join(f"sentence number {i} about patching" for i in range(900))
            store_capture(
                repo, revision.revision_id, _capture(Path("/docs/long.pdf"), [("1", body)])
            )
            plan = si.build_plan(repo, jurisdiction="internal")
            assert len(plan.units) > 1
            assert len(plan.examined_sections) == 1
            ids = [u.chunk_id for u in plan.units]
            assert ids == sorted(ids, key=lambda i: int(i.split("#")[1]))
            assert all(si.parent_section_id(i) == plan.examined_sections[0] for i in ids)
            assert "".join(u.text for u in plan.units) == body + "\n"
        finally:
            repo.close()

    def test_a_sub_unit_id_resolves_to_its_parent(self) -> None:
        assert si.parent_section_id("csection-abc#3") == "csection-abc"
        assert si.parent_section_id("csection-abc") == "csection-abc"

    def test_split_pieces_stay_within_the_window(self) -> None:
        pieces = si.split_text("x" * 20_000, limit=6000)
        assert all(len(p) <= 6000 for p in pieces)
        assert "".join(pieces) == "x" * 20_000


class TestTheBoundaryIsAFact:
    def test_a_complete_projection_yields_a_complete_receipt(self, store: Repository) -> None:
        plan = si.build_plan(store, jurisdiction="US")
        receipt = si.boundary_receipt(store, plan)
        assert receipt["complete"] is True
        assert receipt["corpus_whole"] is True
        assert set(receipt["eligible_sections"]) == set(receipt["examined_sections"])
        assert receipt["omissions"] == []
        assert receipt["document_revision_hashes"]

    def test_a_scoped_receipt_covers_only_the_scope(self, store: Repository) -> None:
        plan = si.build_plan(store, jurisdiction="US")
        scope = plan.examined_sections[:2]
        receipt = si.boundary_receipt(store, plan, scope_sections=scope)
        assert receipt["eligible_sections"] == sorted(scope)
        assert receipt["complete"] is True

    def test_an_uncaptured_document_is_named_and_the_corpus_is_not_whole(
        self, store: Repository
    ) -> None:
        store.upsert_source_document(
            SourceDocument(
                logical_id="NERC/CIP-010-4",
                title="CIP-010-4",
                issuer="NERC",
                source_kind="regulatory_standard",
                jurisdiction="US",
            )
        )
        revision = store.add_document_revision("NERC/CIP-010-4", "/docs/010.pdf", b"010")
        from portal.modules.compliance.core.models import SourceSection

        store.add_source_section(
            SourceSection(section_id="legacy-010-1", revision_id=revision.revision_id, path="R1")
        )
        plan = si.build_plan(store, jurisdiction="US")
        receipt = si.boundary_receipt(store, plan)
        assert receipt["complete"] is True  # every eligible section was examined
        assert receipt["corpus_whole"] is False  # but a document is not captured
        assert "NERC/CIP-010-4" in receipt["documents_not_captured"]


class TestAbsenceIsProvableInBothDirections:
    def test_an_exhaustive_acquisition_yields_a_boundary_proof_id(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import assessment_source as src

        monkeypatch.setattr(src, "_store", lambda: _StubStore())
        monkeypatch.setattr(
            "portal.modules.compliance.core.repository.Repository",
            lambda *a, **k: store,
        )
        candidates = src.acquire_exhaustively(kb_id="operator_corpus", jurisdiction="internal")
        receipt = candidates.acquisition_receipt["boundary_receipt"]
        assert receipt["complete"] is True
        assert set(receipt["examined_sections"]) == {r.chunk_id for r in candidates.records}

        request = _request(candidates)
        from portal.modules.compliance.core.assessment_report import _boundary_proof_id

        assert _boundary_proof_id(request).startswith("boundary-")

    def test_withholding_one_section_voids_the_proof(
        self, store: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from portal.modules.compliance.core import assessment_source as src

        monkeypatch.setattr(src, "_store", lambda: _StubStore())
        monkeypatch.setattr(
            "portal.modules.compliance.core.repository.Repository",
            lambda *a, **k: store,
        )
        every = si.build_plan(store, jurisdiction="internal").examined_sections
        candidates = src.acquire_exhaustively(
            kb_id="operator_corpus", jurisdiction="internal", withhold=[every[0]]
        )
        receipt = candidates.acquisition_receipt["boundary_receipt"]
        assert receipt["complete"] is False
        assert receipt["omissions"] == [every[0]]

        from portal.modules.compliance.core.assessment_report import _boundary_proof_id

        assert _boundary_proof_id(_request(candidates)) == ""


class _StubTable:
    version = 1

    def search(self):  # noqa: ANN201 - mirrors the lancedb surface
        return self

    def limit(self, _n):  # noqa: ANN001, ANN201
        return self

    def to_list(self):  # noqa: ANN201
        return []


class _StubStore:
    @staticmethod
    def tname(kb_id, prefix=""):  # noqa: ANN001, ANN205
        return f"{prefix}{kb_id}"

    @staticmethod
    def text_table(kb_id, create=False, prefix=""):  # noqa: ANN001, ANN205
        return _StubTable()

    @staticmethod
    def read_stamp(kb_id, prefix=""):  # noqa: ANN001, ANN205
        return {"embed_model": "stub-embedder"}


def _request(candidates):  # noqa: ANN001, ANN202
    from portal.modules.compliance.core import assessment_source as src
    from portal.modules.compliance.core.applicability import AssetScope
    from portal.modules.compliance.core.determination import AssessmentRequest

    snapshot = src.build_corpus_snapshot(
        "operator_corpus", acquisition_receipt=candidates.acquisition_receipt
    )
    return AssessmentRequest(
        requirement_id="CIP-007-6 R2 Part 2.2",
        kb_id="operator_corpus",
        org_id="default",
        scope=AssetScope(),
        snapshot=snapshot,
        candidate_set=candidates,
    )


class TestTheProjectionCarriesWhatTheStoreMeans:
    """SUBSTRATE_PROPERTIES_V1 P1: every projected row carries the predicate
    columns, copied from the canonical store, so property 1 — temporal validity
    filters BEFORE ranking — becomes expressible as a ``.where()`` predicate."""

    def test_every_unit_carries_the_predicate_columns(self, store: Repository) -> None:
        plan = si.build_plan(store, jurisdiction="internal")
        assert plan.units
        for unit in plan.units:
            row = unit.as_row()
            for column in si.PREDICATE_COLUMNS:
                assert column in row, f"missing predicate column {column}"
                assert row[column] is not None, f"None in predicate column {column}"
            assert unit.jurisdiction == "internal"
            assert unit.logical_id == "LSPG/patching"
            assert unit.revision_id
            assert unit.source_kind == "procedure"
            assert unit.unit_kind == "prose"

    def test_clocks_are_date_shaped_with_explicit_open_bounds(self, store: Repository) -> None:
        revision_id = store._conn.execute(
            "SELECT revision_id FROM document_revisions WHERE logical_id = 'LSPG/patching'"
        ).fetchone()[0]
        row = store._conn.execute(
            "SELECT recorded_from FROM document_revisions WHERE revision_id = ?",
            (revision_id,),
        ).fetchone()
        plan = si.build_plan(store, jurisdiction="internal")
        unit = plan.units[0]
        # recorded_from is a full timestamp in the store; a .where() compares
        # strings, so it must land as YYYY-MM-DD or a known_at date never
        # matches its own day.
        assert unit.recorded_from == str(row[0])[:10]
        assert len(unit.recorded_from) == 10
        # an open bound is "" — never None, never a guess
        assert unit.effective_to == ""
        assert unit.recorded_to == ""
        assert unit.effective_from == ""

    def test_a_replaced_revision_is_flagged_governing_is_not(self, tmp_path: Path) -> None:
        repo = Repository(tmp_path / "revisions.db")
        try:
            repo.upsert_source_document(
                SourceDocument(
                    logical_id="NERC/glossary",
                    title="glossary",
                    issuer="NERC",
                    source_kind="glossary",
                    jurisdiction="US",
                )
            )
            old = repo.add_document_revision(
                "NERC/glossary",
                "/docs/glossary.pdf",
                b"old glossary bytes",
                effective_date="2020-01-01",
                inactive_date="2026-09-01",
            )
            store_capture(
                repo,
                old.revision_id,
                _capture(Path("/docs/glossary.pdf"), [("Terms", "The old term definition.")]),
            )
            new = repo.add_document_revision(
                "NERC/glossary",
                "/docs/glossary.pdf",
                b"new glossary bytes",
                effective_date="2026-09-01",
            )
            store_capture(
                repo,
                new.revision_id,
                _capture(Path("/docs/glossary.pdf"), [("Terms", "The new term definition.")]),
            )
            plan = si.build_plan(repo, jurisdiction="US")
            by_revision = {u.revision_id: u.is_superseded for u in plan.units}
            assert by_revision[old.revision_id] == 1
            assert by_revision[new.revision_id] == 0
            # history stays answerable: the superseded rows are still projected
            assert len({u.revision_id for u in plan.units}) == 2
        finally:
            repo.close()

    def test_an_untiered_unset_document_still_projects_every_predicate(
        self, tmp_path: Path
    ) -> None:
        repo = Repository(tmp_path / "bare.db")
        try:
            repo.upsert_source_document(
                SourceDocument(
                    logical_id="note/loose",
                    title="loose note",
                    issuer="operator",
                    source_kind="operator_note",
                    jurisdiction="operator_note",
                )
            )
            revision = repo.add_document_revision("note/loose", "note/loose", b"note bytes")
            store_capture(
                repo,
                revision.revision_id,
                _capture(Path("note/loose"), [("Note", "An operator note with no dates.")]),
            )
            plan = si.build_plan(repo, jurisdiction="operator_note")
            assert plan.units
            unit = plan.units[0]
            assert unit.effective_from == ""
            assert unit.effective_to == ""
            assert unit.is_superseded == 0
            assert unit.as_row()["is_superseded"] == 0
        finally:
            repo.close()
