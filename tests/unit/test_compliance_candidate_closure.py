"""END_TO_END Phase 8 — candidate closure and the complete reading packet.

Under test: source-function preservation into the reader packet (a copied
NERC traceability row cannot present itself as operative implementation),
neighbor section closure, mapping metadata as governance-not-answer, and the
declared corpus boundary receipt.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.candidate_closure import (
    enrich_reading_packet,
    mapping_candidates,
    neighbor_closure,
    source_function_for,
)
from portal.modules.compliance.core.internal_corpus import (
    classify_kind,
    inventory_file,
    sectionize,
)
from portal.modules.compliance.core.models import RelationshipAssertion, SourceDocument
from portal.modules.compliance.core.repository import Repository

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _procedure_pages() -> list[str]:
    return [
        " \nPRIVATE – FOR INTERNAL USE ONLY \n"
        "LSPG Security Patch Management Procedure \n"
        "Effective Date:  July 31, 2026 \n"
        "Document Type: Procedure \nDocument Number:  LSPG-ADM-X1 \n",
        "3.0 Procedure \n3.5 Patch Implementation Process \n"
        "The analyst shall install applicable patches. \n",
        (
            "5.0 Appendix \n"
            "5.1 Appendix 1: Requirements Traceability \n"
            "NERC Standard & Requirement | Procedure Sections \n"
            "R2 Part 2.2 At least once every 35 calendar days, evaluate security "
            "patches for applicability. | Section 3.3 \n"
        ),
    ]


@pytest.fixture
def repo_with_doc(tmp_path):
    repo = Repository(tmp_path / "store.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="CIP-007/Procedure.pdf",
            title="Procedure",
            issuer="LSPG",
            source_kind="procedure",
            jurisdiction="internal",
        )
    )
    rev = repo.add_document_revision(
        "CIP-007/Procedure.pdf",
        "/corpus/CIP-007/Procedure.pdf",
        b"procedure-bytes",
        binding_effect="internally_mandatory",
    )
    from portal.modules.compliance.core.models import SourceSection

    sections = sectionize(_procedure_pages(), operative_role="OPERATIVE_PROCEDURE")
    for section in sections:
        section.revision_id = rev.revision_id
        repo.add_source_section(
            SourceSection(
                section_id=section.section_id,
                revision_id=rev.revision_id,
                path=section.path,
                page_start=section.page_start,
                page_end=section.page_end,
                extractor="internal_corpus",
                extractor_version="1",
                role=section.role,
                title=section.title,
            )
        )
        repo.add_source_span(
            "ispan-" + section.section_id[len("isection-") :],
            section.section_id,
            section.char_start,
            max(section.char_start + 1, section.char_end),
            section.span_sha256(),
        )
    yield repo, rev
    repo.close()


class TestSourceFunction:
    def test_operative_clause_is_operative(self, repo_with_doc):
        repo, _rev = repo_with_doc
        fn = source_function_for(repo, "CIP-007/Procedure.pdf", "3.5 Patch Implementation Process")
        assert fn["source_function"] == "OPERATIVE_PROCEDURE"
        assert fn["operative"] is True

    def test_copied_traceability_row_is_not_implementation(self, repo_with_doc):
        """The appendix section carries the copied NERC text; its classified
        role is TRACEABILITY_ASSERTION, so the packet labels it non-operative."""
        repo, _rev = repo_with_doc
        fn = source_function_for(
            repo,
            "CIP-007/Procedure.pdf",
            "5.1 Appendix 1: Requirements Traceability",
        )
        assert fn["source_function"] == "TRACEABILITY_ASSERTION"
        assert fn["operative"] is False
        assert "cannot implement a duty" in fn["note"]

    def test_unresolved_document_is_labeled_not_guessed(self, repo_with_doc):
        repo, _rev = repo_with_doc
        fn = source_function_for(repo, "Unknown Doc.pdf", "anything")
        assert fn["source_function"] == "UNRESOLVED"
        assert fn["operative"] is False


class TestClosure:
    def test_neighbor_closure_returns_siblings_of_operative_sections(self, repo_with_doc):
        repo, _rev = repo_with_doc
        neighbors = neighbor_closure(repo, "CIP-007/Procedure.pdf")
        paths = {n["path"] for n in neighbors}
        assert "5.0" in paths or "3.5" in paths  # siblings around operative hits
        assert all(n["relation"] == "sibling" for n in neighbors)

    def test_mapping_metadata_is_labeled_discovery(self, repo_with_doc):
        repo, rev = repo_with_doc
        rel = RelationshipAssertion(
            "rel-x",
            "IMPLEMENTS",
            "CIP-007-6 R2 Part 2.2",
            None,
            "CIP-007/Procedure.pdf",
            rev.revision_id,
            "CIP-007",
            derivation="folder_cartesian",
        )
        repo.propose_relationship(rel)
        mappings = mapping_candidates(repo, "CIP-007-6 R2 Part 2.2")
        assert mappings and mappings[0]["status"] == "proposed"
        assert mappings[0]["derivation"] == "folder_cartesian"
        assert "never decides satisfaction" in mappings[0]["note"]


class TestPacketEnrichment:
    def _packet(self, doc_text: str) -> dict:
        return {
            "governing": {"part_text": "governing text"},
            "candidates": [
                {
                    "candidate_id": "c1",
                    "document_id": "CIP-007/Procedure.pdf",
                    "text": doc_text,
                }
            ],
        }

    def test_copied_row_cannot_act_as_implementation(self, repo_with_doc):
        """The exit-criterion adversary: the copied NERC row, retrieved as a
        candidate, enters the packet labelled non-operative."""
        repo, _rev = repo_with_doc
        packet = self._packet("5.1 Appendix 1: Requirements Traceability")
        enrich_reading_packet(repo, packet, requirement_id="CIP-007-6 R2 Part 2.2", corpus_dir="")
        cand = packet["candidates"][0]
        assert cand["operative"] is False
        assert cand["source_function"] == "TRACEABILITY_ASSERTION"
        assert cand["revision_id"]

    def test_boundary_receipt_attached(self, repo_with_doc, tmp_path):
        repo, _rev = repo_with_doc
        packet = self._packet("3.5 Patch Implementation Process")
        corpus = tmp_path / "corpus"
        (corpus / "CIP-007").mkdir(parents=True)
        (corpus / "CIP-007" / "Procedure.pdf").write_bytes(b"x")
        (corpus / "CIP-007" / "Other.pdf").write_bytes(b"y")
        enrich_reading_packet(repo, packet, requirement_id="", corpus_dir=str(corpus))
        boundary = packet["corpus_boundary"]
        assert boundary["declared_documents"] == 2
        assert boundary["registered_documents"] == 1
        assert boundary["complete"] is False  # Other.pdf is not registered
        assert boundary["unregistered"] == ["CIP-007/Other.pdf"]

    def test_unenriched_packet_says_so(self):
        """Without a repository the packet is served unenriched and discloses
        it — never silently."""
        from portal.modules.compliance.core.determination import AssessmentRequest
        from portal.modules.compliance.core.reading import build_reading_packet

        request = AssessmentRequest(requirement_id="X R1 Part 1.1")
        packet = build_reading_packet(request)
        assert "not enriched" in packet["candidate_closure"]


class TestRealProcedureIntegration:
    """Live-corpus check of the full classify→store→packet chain (skipped in
    CI where the private corpus is absent)."""

    CORPUS = __import__("pathlib").Path(
        "coding_task/v9_compliance/LSPG-CIP/CIP-007/"
        "LSPG Security Patch Management Procedure V11.pdf"
    )

    @pytest.mark.skipif(not CORPUS.is_file(), reason="operator corpus is private/local")
    def test_real_traceability_appendix_never_operative(self, tmp_path):
        inv = inventory_file(self.CORPUS)
        roles = {s.path: s.role for s in inv["sections"]}
        trace = [p for p, r in roles.items() if r == "TRACEABILITY_ASSERTION"]
        assert trace, "the procedure's requirements-traceability appendix must classify"
        kind, _effect, role, _ev = classify_kind(inv["control"].stated_type, self.CORPUS.name)
        assert (kind, role) == ("procedure", "OPERATIVE_PROCEDURE")
