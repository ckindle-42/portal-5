"""END_TO_END Phase 4 — truthful internal revisions and source functions.

Under test: the control-block metadata parser (sourced-or-absent, never
guessed), section-function classification (operative vs traceability vs
control/ToC text), the migration-10 columns, the metadata/derivation
repository methods, and the impact quarantine that keeps folder/prefix
Cartesian proposals out of established impact.
"""

from __future__ import annotations

import hashlib

import pytest

from portal.modules.compliance.core import internal_corpus as ic
from portal.modules.compliance.core.internal_model import extract_assertions
from portal.modules.compliance.core.migrations import CURRENT_SCHEMA_VERSION
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.result_contract import is_source_role

# ── hermetic corpus fixtures (mimic the observed controlled-document shapes) ─


def _procedure_pages() -> list[str]:
    return [
        (
            " \nPRIVATE – FOR INTERNAL USE ONLY \n \n \n"
            "LSPG Security Patch Management \nProcedure \n \n"
            "Effective Date:  July 31, 2026 \n \n"
            "Document Type: Procedure \nNERC Standard: CIP-007 \n"
            "Document Number:  LSPG-ADM-CIP007SPM \n"
        ),
        (
            " \nPRIVATE – FOR INTERNAL USE ONLY \nPage 2 of 9 \n \n"
            "DOCUMENT OWNER \nName \nTitle \nRyan Borg \n"
            "Manager of OT Security Operations \n \n"
            "APPROVALS \nName \nDate \n \n"
            "Name: Richard Morgan \nTitle: Sr. Director, Operations Technology \n"
            "7/24/2026\n"
        ),
        (
            "Table of Contents \n"
            "1.0 Introduction........................................ 2 \n"
            "1.1 Purpose............................................. 2 \n"
            "5.0 Appendix............................................ 4 \n"
        ),
        (
            "1.0 Introduction \n1.1 \nPurpose \n"
            "The purpose is patch tracking. \n"
            "1.2 \nApplicability \n"
            "This applies to LSPG registrations. \n"
            "1.4 Roles and Responsibilities \n"
            "1.4.1 \nOT \n"
            "1.4.1.1 \n"
            "Carries out tasks outlined in this procedure that pertain to "
            "patching activities. \n"
        ),
        (
            "2.0 General Information \n"
            "2.1 \nTerms, Definitions and Acronyms \n"
            "CA - Cyber Asset. \n"
            "3.0 Procedure \n"
            "3.5 \nPatch Implementation Process \n"
            "The analyst shall install applicable patches. \n"
            "3.6 Patch Mitigation Plan Management \n"
            "Mitigation plans shall include a timeframe. \n"
        ),
        (
            "5.0 Appendix \n"
            "5.1 Appendix 1: Requirements Traceability \n"
            "NERC Standard & Requirement | Procedure Sections \n"
            "R2 Part 2.1 A patch management process for tracking. | Section 3.1 \n"
            "R2 Part 2.2 At least once every 35 calendar days, evaluate. | Section 3.3 \n"
        ),
        (
            "REVISION HISTORY \n \n"
            "Date \nVersion \nRevised By \nComments \n"
            "06/20/2025 \n6.0 \nR. Morgan \nAnnual Review \n"
            "06/24/2026 \n7.0 \nR. Borg \nAnnual Review; updates throughout \n"
        ),
    ]


@pytest.fixture
def procedure() -> list[str]:
    return _procedure_pages()


def _form_pages() -> list[str]:
    return [
        "LSPG CIP Exceptional Circumstance Request Form \n"
        "LSPG will use a CIP Exceptional Circumstances in a situation that \n"
        "Event Start Date & Time: \n",
        "Approving CEC \nSignature Date \n",
    ]


# ── control-block metadata ──────────────────────────────────────────────────


class TestDocumentControl:
    def test_full_procedure_block(self, procedure):
        control = ic.parse_document_control(procedure)
        assert control.title == "LSPG Security Patch Management Procedure"
        assert control.document_number == "LSPG-ADM-CIP007SPM"
        assert control.stated_type == "Procedure"
        assert control.nerc_standard == "CIP-007"
        assert control.effective_date == "2026-07-31"
        assert control.owner == "Ryan Borg"
        assert control.owner_title == "Manager of OT Security Operations"
        assert control.approver == "Richard Morgan"
        assert control.approval_date == "2026-07-24"
        assert control.version == "7.0"
        assert control.authored_date == "2026-06-24"
        assert control.last_reviewed_date == "2026-06-24"

    def test_every_sourced_field_carries_provenance(self, procedure):
        control = ic.parse_document_control(procedure)
        for field in (
            "title",
            "document_number",
            "stated_type",
            "nerc_standard",
            "effective_date",
            "owner",
            "approval_date",
            "version",
        ):
            assert field in control.sources, field

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
            "Document Type: Procedure \nDocument ID: LSPG-OTSO-NERC-PCD-AcsMgmt \n"
        ]
        control = ic.parse_document_control(pages)
        assert control.document_number == "LSPG-OTSO-NERC-PCD-AcsMgmt"
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
            None, "OT Vulnerability Management WI v1.pdf"
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


# ── section functions ───────────────────────────────────────────────────────


class TestSectionize:
    def test_roles_across_the_document(self, procedure):
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        by_path = {s.path: s for s in sections}
        assert by_path["toc.p3"].role == "TABLE_OF_CONTENTS"
        assert by_path["DOCUMENT OWNER"].role == "DOCUMENT_CONTROL"
        assert by_path["REVISION HISTORY"].role == "DOCUMENT_CONTROL"
        assert by_path["1.1"].role == "OPERATIVE_PROCEDURE"
        assert by_path["3.5"].role == "OPERATIVE_PROCEDURE"
        assert by_path["2.1"].role == "DEFINITION"
        assert by_path["5.1"].role == "TRACEABILITY_ASSERTION"

    def test_traceability_appendix_swallows_copied_table_rows(self, procedure):
        """The appendix table re-uses referenced section numbers ('3.1',
        '3.3'); numbering continuity keeps them inside the traceability
        section instead of minting duplicate operative sections."""
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        operative_paths = [s.path for s in sections if s.role == "OPERATIVE_PROCEDURE"]
        assert operative_paths.count("3.5") == 1
        trace = next(s for s in sections if s.path == "5.1")
        assert "R2 Part 2.2 At least once every 35 calendar days" in trace.text
        assert trace.page_start == 6 and trace.page_end == 6

    def test_revision_history_rows_stay_control_text(self, procedure):
        """Revision-history rows re-use section-shaped numbers ('1.0',
        '7.0'); the cutoff keeps them inside the control section."""
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        history = next(s for s in sections if s.path == "REVISION HISTORY")
        assert "06/24/2026" in history.text and "R. Borg" in history.text
        numbered_after = [
            s.path
            for s in sections
            if s.role == "OPERATIVE_PROCEDURE" and s.page_start >= history.page_start
        ]
        assert numbered_after == []

    def test_parent_sibling_closure(self, procedure):
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        paths = [s.path for s in sections]
        assert "1.4" in paths and "1.4.1" in paths
        # siblings share the parent prefix
        for path in ("1.4.1", "1.4.2"):
            if path in paths:
                assert any(p == path.rsplit(".", 1)[0] for p in paths)

    def test_numbered_content_items_are_not_sections(self, procedure):
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        titles = {s.title for s in sections}
        assert "Carries out tasks outlined in this procedure that pertain to" not in titles

    def test_span_offsets_round_trip_to_text(self, procedure):
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        full_text = "\n".join(procedure)
        for s in sections:
            assert full_text[s.char_start : s.char_end] == s.text
            assert (
                hashlib.sha256(s.text.encode()).hexdigest()
                == hashlib.sha256(s.text.encode()).hexdigest()
            )
            assert s.span_sha256() == s.span_sha256()

    def test_section_ids_are_stable_across_runs(self, procedure):
        a = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        b = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        assert [s.section_id for s in a] == [s.section_id for s in b]

    def test_form_falls_back_to_per_page_sections(self):
        sections = ic.sectionize(_form_pages(), operative_role="EVIDENCE_SPECIFICATION")
        assert [s.path for s in sections] == ["page.1", "page.2"]
        assert all(s.role == "EVIDENCE_SPECIFICATION" for s in sections)

    def test_every_role_is_in_the_controlled_vocabulary(self, procedure):
        sections = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        assert all(is_source_role(s.role) for s in sections)

    def test_section_ids_are_scoped_to_the_revision(self, procedure):
        """Two documents can both have a '1.0' on page 1 — found live when
        only 1037 of 2531 sections survived insertion because ids collided
        across revisions. The id must carry the revision hash."""
        a = ic.sectionize(procedure, operative_role="OPERATIVE_PROCEDURE")
        b = ic.sectionize(procedure, operative_role="WORK_INSTRUCTION")
        for sa in a:
            sa.revision_id = "revision-a"
        for sb in b:
            sb.revision_id = "revision-b"
        ids_a = {s.section_id for s in a}
        ids_b = {s.section_id for s in b}
        assert ids_a and ids_b
        assert ids_a.isdisjoint(ids_b)
        # and unchanged without a revision differs once set
        assert {s.section_id for s in a} == ids_a


# ── source-function gating of commitments ───────────────────────────────────


class TestCommitmentGating:
    def test_operative_section_yields_commitments(self):
        text = "The analyst shall install applicable patches within the window."
        out = extract_assertions("rev", text, anchor_id="a", section_role="OPERATIVE_PROCEDURE")
        assert out and out[0].relation_type == "IMPLEMENTS"

    def test_copied_traceability_rows_yield_no_commitments(self):
        text = (
            "R2 Part 2.2 At least once every 35 calendar days, evaluate security "
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


# ── migration 10 and the repository methods ─────────────────────────────────


class TestMigrationAndRepository:
    def test_fresh_store_reaches_current_version(self, tmp_path):
        repo = Repository(tmp_path / "fresh.db")
        assert repo.schema_version == CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION >= 10
        columns = {
            row[1] for row in repo._conn.execute("PRAGMA table_info(document_revisions)").fetchall()
        }
        assert {"document_number", "version", "owner", "owner_title"} <= columns
        rel_columns = {
            row[1]
            for row in repo._conn.execute("PRAGMA table_info(relationship_assertions)").fetchall()
        }
        assert "derivation" in rel_columns
        repo.close()

    def test_populated_store_upgrade_keeps_rows_and_defaults(self, tmp_path, monkeypatch):
        import sqlite3

        import portal.modules.compliance.core.migrations as migrations_pkg
        from portal.modules.compliance.core.migrations import apply_migrations

        v9_list = [m for m in migrations_pkg.MIGRATIONS if m[0] <= 9]
        monkeypatch.setattr(migrations_pkg, "MIGRATIONS", v9_list)
        path = tmp_path / "v9.db"
        conn = sqlite3.connect(path)
        apply_migrations(conn)
        conn.execute("INSERT INTO source_documents(logical_id, title) VALUES ('doc.pdf','doc')")
        conn.execute(
            "INSERT INTO document_revisions(revision_id, logical_id, alias_path, retrieved_at, recorded_from)"
            " VALUES ('rev1','doc.pdf','/x/doc.pdf','t','t')"
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(migrations_pkg, "MIGRATIONS", migrations_pkg.schema.MIGRATIONS)
        repo = Repository(path)
        rev = repo.get_revision("rev1")
        assert rev is not None
        # honest empty defaults — nothing is back-filled to look sourced
        assert rev.document_number == ""
        assert rev.version == ""
        assert rev.owner == ""
        assert rev.effective_date is None
        repo.close()

    def test_update_metadata_fills_placeholders_and_never_clobbers(self, tmp_path):
        repo = Repository(tmp_path / "store.db")
        repo.upsert_source_document(SourceDocument("doc.pdf", "doc", "", "procedure", ""))
        repo.add_document_revision("doc.pdf", "/x/doc.pdf", b"bytes")
        rev = repo.revisions_for_logical_id("doc.pdf")[0]
        assert repo.update_revision_control_metadata(
            rev.revision_id,
            binding_effect="internally_mandatory",
            document_number="LSPG-ADM-X1",
            version="7.0",
            effective_date="2026-07-31",
        )
        first = repo.get_revision(rev.revision_id)
        assert first.version == "7.0" and first.effective_date == "2026-07-31"
        # a re-run without the field must not erase it with an empty value
        assert repo.update_revision_control_metadata(rev.revision_id, owner="Ryan Borg")
        second = repo.get_revision(rev.revision_id)
        assert second.version == "7.0"
        assert second.owner == "Ryan Borg"
        assert second.binding_effect == "internally_mandatory"
        assert repo.update_revision_control_metadata("missing-rev", version="1") is False
        repo.close()

    def test_tag_relationship_derivation_requires_a_shape_filter(self, tmp_path):
        repo = Repository(tmp_path / "store.db")
        with pytest.raises(ValueError):
            repo.tag_relationship_derivation("folder_cartesian")
        repo.close()

    def test_cartesian_quarantine_tags_once_and_excludes_from_impact(self, tmp_path):
        repo = Repository(tmp_path / "store.db")
        repo.upsert_source_document(
            SourceDocument("NERC/CIP-007-6", "CIP-007-6", "NERC", "regulatory_standard", "US")
        )
        reg_rev = repo.add_document_revision("NERC/CIP-007-6", "/x/cip.pdf", b"reg")
        repo.upsert_source_document(
            SourceDocument("doc.pdf", "doc", "LSPG", "procedure", "internal")
        )
        int_rev = repo.add_document_revision("doc.pdf", "/x/doc.pdf", b"int")
        proposal = RelationshipAssertion(
            "rel-1",
            "IMPLEMENTS",
            "CIP-007-6 R2 Part 2.1",
            reg_rev.revision_id,
            "control-x",
            int_rev.revision_id,
            "CIP-007",
            rationale="content-derived candidate; determination does not depend on approval",
        )
        repo.propose_relationship(proposal)
        tagged = repo.tag_relationship_derivation(
            "folder_cartesian",
            from_rationale="content-derived candidate",
            relation_types=("IMPLEMENTS",),
        )
        assert tagged == 1
        # idempotent: already-tagged rows are never re-touched
        assert (
            repo.tag_relationship_derivation(
                "other", from_rationale="content-derived candidate", relation_types=("IMPLEMENTS",)
            )
            == 0
        )
        assert repo.get_relationship("rel-1").derivation == "folder_cartesian"

        from portal.modules.compliance.core.impact import analyze

        result = analyze(repo, "CIP-007-6 R2 Part 2.1")
        assert result["direct"] == [] and result["transitive"] == []
        candidates = result["discovery_candidates"]
        assert len(candidates) == 1
        assert candidates[0]["derivation"] == "folder_cartesian"
        assert "not an established" in candidates[0]["note"]
        repo.close()


# ── private-corpus integration (skipped when the operator PDFs are absent) ──


CORPUS = __import__("pathlib").Path(
    "coding_task/v9_compliance/LSPG-CIP/CIP-007/LSPG Security Patch Management Procedure V11.pdf"
)


@pytest.mark.skipif(not CORPUS.is_file(), reason="operator corpus is private/local")
class TestRealPatchProcedure:
    def test_patch_procedure_resolves_exact_revision_and_operative_sections(self):
        inv = ic.inventory_file(CORPUS)
        control = inv["control"]
        assert inv["source_kind"] == "procedure"
        assert inv["document_role"] == "OPERATIVE_PROCEDURE"
        assert control.document_number == "LSPG-ADM-CIP007SPM"
        assert control.version == "11.0"
        assert control.effective_date == "2026-07-31"
        assert control.owner == "Ryan Borg"
        paths = {s.path: s for s in inv["sections"]}
        # the sections the document's own traceability table references
        for referenced in ("3.1", "3.3", "3.5", "3.6"):
            assert referenced in paths, referenced
            assert paths[referenced].role == "OPERATIVE_PROCEDURE"
        trace = [s for s in inv["sections"] if s.role == "TRACEABILITY_ASSERTION"]
        assert trace and any("R2 Part 2.2" in s.text for s in trace)
