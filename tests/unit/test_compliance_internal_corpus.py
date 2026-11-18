"""END_TO_END Phase 4 — truthful internal revisions and source functions.

Under test: the control-block metadata parser (sourced-or-absent, never
guessed), section-function classification (operative vs traceability vs
control/ToC text), the migration-10 columns, the metadata/derivation
repository methods, and the impact quarantine that keeps folder/prefix
Cartesian proposals out of established impact.
"""

from __future__ import annotations

import pathlib

import pytest

from portal.modules.compliance.core import internal_corpus as ic
from portal.modules.compliance.core.internal_model import extract_assertions
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.result_contract import SOURCE_ROLES


def _form_pages() -> list[str]:
    return [
        "ACME CIP Exceptional Circumstance Request Form \n"
        "ACME will use a CIP Exceptional Circumstances in a situation that \n"
        "Event Start Date & Time: \n",
        "Approving CEC \nSignature Date \n",
    ]


class TestDocumentControl:
    def test_absent_metadata_stays_none_never_guessed(self):
        control = ic.parse_document_control(_form_pages())
        # the only thing the form states is its own title line
        assert control.document_number is None
        assert control.stated_type is None
        assert control.effective_date is None
        assert control.version is None
        assert control.owner is None
        assert set(control.sources) == {"title"}

    def test_document_id_label_variant(self):
        pages = [
            "Access Management \nEffective Date: August 31, 2026 \n"
            "Document Type: Procedure \nDocument ID: ACME-OTSO-NERC-PCD-AcsMgmt \n"
        ]
        control = ic.parse_document_control(pages)
        assert control.document_number == "ACME-OTSO-NERC-PCD-AcsMgmt"
        assert control.effective_date == "2026-08-31"

    def test_slash_and_month_dates(self):
        assert ic.parse_date("7/24/2026") == "2026-07-24"
        assert ic.parse_date("July 31, 2026") == "2026-07-31"
        assert ic.parse_date("05/04/2016") == "2016-05-04"
        assert ic.parse_date("no date here") is None


class TestClassifyKind:
    def test_stated_type_wins_over_filename(self):
        kind, effect, role, evidence = ic.classify_kind("Work Instruction", "x-procedure.pdf")
        assert (kind, effect, role) == (
            "work_instruction",
            "internally_mandatory",
            "WORK_INSTRUCTION",
        )
        assert "document states" in evidence

    def test_filename_fallback_is_recorded_as_such(self):
        kind, _effect, role, evidence = ic.classify_kind(
            None, "OT Vulnerability Management Work Instruction v1.pdf"
        )
        assert kind == "work_instruction"
        assert role == "WORK_INSTRUCTION"
        assert "filename" in evidence

    def test_forms_are_evidence(self):
        kind, effect, role, _ = ic.classify_kind("Form", "x.pdf")
        assert kind == "evidence_specification"
        assert effect == "descriptive"
        assert role == "EVIDENCE_SPECIFICATION"

    def test_no_signal_is_unknown_not_guessed(self):
        kind, effect, role, _evidence = ic.classify_kind(None, "scan001.pdf")
        assert kind == "unknown"
        assert effect == "unknown"
        assert role == ""


class TestSectionize:
    def test_form_falls_back_to_per_page_sections(self):
        sections = ic.sectionize(_form_pages(), operative_role="EVIDENCE_SPECIFICATION")
        assert [s.path for s in sections] == ["page.1", "page.2"]
        assert all(s.role == "EVIDENCE_SPECIFICATION" for s in sections)


class TestCommitmentGating:
    def test_operative_section_yields_commitments(self):
        text = "The analyst shall install applicable patches within the window."
        out = extract_assertions("rev", text, anchor_id="a", section_role="OPERATIVE_PROCEDURE")
        assert out and out[0].relation_type == "IMPLEMENTS"

    def test_copied_traceability_rows_yield_no_commitments(self):
        text = (
            "R2 Part 2.2 At least once each 35-day window, evaluate security "
            "patches for applicability. | Section 3.3"
        )
        assert (
            extract_assertions("rev", text, anchor_id="a", section_role="TRACEABILITY_ASSERTION")
            == []
        )

    def test_toc_control_and_commentary_yield_no_commitments(self):
        text = "The analyst shall install applicable patches."
        for role in ("TABLE_OF_CONTENTS", "DOCUMENT_CONTROL", "COMMENTARY", "DEFINITION"):
            assert extract_assertions("rev", text, anchor_id="a", section_role=role) == [], role


def _write_revision_table_pdf() -> pathlib.Path:
    """A synthetic controlled document whose revision history is a
    HEADINGLESS table: a bare number line with an author-like title line on
    the next line passes the heading guard, so each dated change row leaks
    past any history cutoff as an operative section and D3's rule must
    re-classify it REVISION_LOG."""
    import tempfile

    import fitz  # noqa: PLC0415 - pymupdf's stable import name

    document = fitz.open()
    control = document.new_page()
    control.insert_text(
        (72, 72),
        (
            "PRIVATE - FOR INTERNAL USE ONLY\n"
            "ACME Asset Procedure\n"
            "Effective Date:  July 31, 2026\n"
            "Document Type: Procedure\n"
            "NERC Standard: CIP-901\n"
        ),
        fontsize=11,
    )
    body = document.new_page()
    body.insert_text(
        (72, 72),
        (
            "1.0 Introduction\n"
            "The process covers asset records.\n"
            "1.1 Purpose\n"
            "The purpose is asset tracking.\n"
            "2.0\n"
            "A. Chen\n"
            "Updated the asset list with the new substation. 7/24/2026\n"
            "3.0\n"
            "B. Ruiz\n"
            "Removed the retired transformer from the asset list. 6/12/2026\n"
        ),
        fontsize=11,
    )
    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=tempfile.gettempdir())
    document.save(str(handle.name))
    document.close()
    handle.close()
    return pathlib.Path(handle.name)


def test_ingest_accepts_revision_log_rows_end_to_end(tmp_path) -> None:
    """D-DT-19 F-R-1: D3 classifies headingless revision-table rows as
    REVISION_LOG, so the end-to-end ingest must accept that role — it used to
    raise ``classified outside the controlled vocabulary`` and crash on any
    document carrying such a table. Hermetic: synthetic text only."""
    from portal.modules.compliance.core.operator_profile import PROFILE_PATH

    if not PROFILE_PATH.exists():  # gitignored, operator's machine only (CI has none)
        pytest.skip("the local operator profile is not present")

    from scripts.materialize_internal_corpus import _materialize_document

    pdf_path = _write_revision_table_pdf()
    repo = Repository(tmp_path / "f-r1.db")
    try:
        logical_id = "CIP-901/ACME Asset Procedure v1.pdf"
        repo.upsert_source_document(
            SourceDocument(
                logical_id=logical_id,
                title="ACME Asset Procedure",
                issuer="ACME",
                source_kind="operating_procedure",
                jurisdiction="internal",
            )
        )
        repo.add_document_revision(
            logical_id,
            str(pdf_path),
            pdf_path.read_bytes(),
            binding_effect="internally_mandatory",
        )
        inv = ic.inventory_file(pdf_path)
        _materialize_document(repo, pdf_path.parent, pdf_path, inv)
        rows = repo._conn.execute(
            "select path, role, title from source_sections where revision_id=?",
            (inv["sha256"],),
        ).fetchall()
        roles = {str(r[1]) for r in rows}
        assert roles <= set(SOURCE_ROLES), roles - set(SOURCE_ROLES)
        revision_rows = [r for r in rows if r[1] == "REVISION_LOG"]
        assert revision_rows, "the headingless revision table must classify REVISION_LOG"
        operative = [r for r in rows if r[1] == "OPERATIVE_PROCEDURE"]
        assert operative, "the operative sections still materialize"
        # a revision-log row is never a commitment source (internal_model gate)
        assert (
            extract_assertions(
                "rev",
                "The analyst shall update the asset list.",
                anchor_id="a",
                section_role="REVISION_LOG",
            )
            == []
        )
    finally:
        repo.close()


def test_heading_only_fold_keeps_the_following_sections_heading() -> None:
    """A heading-only parent ('3.0 Introduction') folds into the section that
    follows it. The merged section owns the child's path and title, so its
    label (``heading`` → ``heading_path``) must be the child's too; the
    parent's heading line stays in the text as the lead. Labelling it with
    the parent's heading made every folded section read '§ 3.0 Introduction'."""
    full = "3.0 Introduction\n3.1 Exceptions\nExceptions are approved by the owner.\n"
    parent_end = full.index("3.1")
    sections = [
        ic.InternalSection(
            path="3.0",
            title="Introduction",
            role="OPERATIVE_PROCEDURE",
            page_start=2,
            page_end=2,
            char_start=0,
            char_end=parent_end,
            text=full[:parent_end],
            heading="3.0 Introduction",
        ),
        ic.InternalSection(
            path="3.1",
            title="Exceptions",
            role="OPERATIVE_PROCEDURE",
            page_start=2,
            page_end=2,
            char_start=parent_end,
            char_end=len(full),
            text=full[parent_end:],
            heading="3.1 Exceptions",
        ),
    ]
    merged = ic._merge_heading_only(sections, full)
    assert len(merged) == 1
    only = merged[0]
    assert (only.path, only.title, only.heading) == ("3.1", "Exceptions", "3.1 Exceptions")
    assert only.text.startswith("3.0 Introduction")
    assert (only.char_start, only.char_end) == (0, len(full))
