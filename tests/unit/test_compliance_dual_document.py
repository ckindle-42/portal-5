"""DATA_TRUTH Amendment 1 DD3 — the dual-document payload, hermetically.

One builder, two reader-facing tools: the standard's normative Parts by
address (or the top-2 standards through the governing-anchor lane), the
operator's document set whole and labelled, the operator's notes, the
operator's traceability declarations — priced against the declared window
with whole-document deferral and no clipping, ever.
"""

from __future__ import annotations

import pathlib

import pytest

from portal.modules.compliance.core import dual_document as dd
from portal.modules.compliance.core.models import SourceDocument, SourceSection
from portal.modules.compliance.core.repository import Repository

_LEAD = "Each Responsible Entity shall carry out the asset process as follows."
_REQUIREMENT = "Record each asset in the operations register every week."
_PART_1_2 = "Review the register with the operations manager every month."


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> Repository:
    """One synthetic standard (two Parts), one folder document carrying
    structure to strip, one traceability-named document, one note."""
    store = Repository(tmp_path / "dd3.db")
    conn = store._conn
    store.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-901-1",
            title="NERC/CIP-901-1",
            issuer="synthetic",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    standard = store.add_document_revision(
        "NERC/CIP-901-1",
        "/docs/cip-901-1.pdf",
        (_LEAD + _REQUIREMENT + _PART_1_2).encode("utf-8"),
        binding_effect="regulatory",
        effective_date="2026-01-01",
    )
    store.put_document_text(
        standard.revision_id,
        _LEAD + _REQUIREMENT + _PART_1_2,
        page_count=1,
        extractor="fixture",
        extractor_version="0",
    )
    registry_sections = [
        ("csection-reg-r1", "B. Requirements / R1", "R1", 0, len(_LEAD)),
        (
            "csection-reg-11",
            "B. Requirements / 1.1",
            "1.1",
            len(_LEAD),
            len(_LEAD) + len(_REQUIREMENT),
        ),
        (
            "csection-reg-12",
            "B. Requirements / 1.2",
            "1.2",
            len(_LEAD) + len(_REQUIREMENT),
            len(_LEAD) + len(_REQUIREMENT) + len(_PART_1_2),
        ),
    ]
    for ordinal, (sid, spath, stitle, cs, ce) in enumerate(registry_sections):
        store.add_source_section(
            SourceSection(
                section_id=sid,
                revision_id=standard.revision_id,
                path=spath,
                extractor="fixture",
                role="B_REQUIREMENTS_AND_MEASURES",
                title=stitle,
                unit_kind="table_row",
                ordinal=ordinal,
                char_start=cs,
                char_end=ce,
                heading_path=stitle,
            )
        )
    for requirement_id, sid, offset, text in (
        ("CIP-901-1 R1", "csection-reg-r1", 0, _LEAD),
        ("CIP-901-1 R1 Part 1.1", "csection-reg-11", len(_LEAD), _REQUIREMENT),
        (
            "CIP-901-1 R1 Part 1.2",
            "csection-reg-12",
            len(_LEAD) + len(_REQUIREMENT),
            _PART_1_2,
        ),
    ):
        conn.execute(
            "insert into requirement_sections (requirement_id, revision_id, section_id,"
            " relation, char_start, char_end, occurrences, anchor_method, anchored_at,"
            " extractor_version) values (?,?,?,?,?,?,1,'exact','2026-10-05','fixture')",
            (
                requirement_id,
                standard.revision_id,
                sid,
                "governing",
                offset,
                offset + len(text),
            ),
        )
    # the folder document: operative sections plus structure to strip
    _add_operator_document(
        store,
        "CIP-901/ACME Asset Procedure v1.pdf",
        "ACME Asset Procedure",
        [
            ("isection-doc-ctl", "DOCUMENT_CONTROL", "Document control", "Owner: ACME."),
            ("isection-toc", "TABLE_OF_CONTENTS", "Table of Contents", "1.0 ... 3.0 ..."),
            (
                "isection-revlog",
                "OPERATIVE_PROCEDURE",
                "1.0 L. Ellisor",
                "Added CIP-002 Visio flow chart process. 05/04/2016",
            ),
            (
                "isection-31",
                "OPERATIVE_PROCEDURE",
                "3.1 Record assets",
                "PRIVATE - FOR INTERNAL USE ONLY\n"
                + "The team records each asset.\n" * 120
                + "Page 1 of 9",
            ),
            (
                "isection-app",
                "TRACEABILITY_ASSERTION",
                "Appendix 1",
                "R1 Part 1.1 ... Sections 3.1",
            ),
        ],
    )
    # the traceability-named document, filed under another standard
    cross_rev = _add_operator_document(
        store,
        "CIP-902/Cross Procedure v2.pdf",
        "Cross Procedure",
        [
            (
                "isection-x1",
                "OPERATIVE_PROCEDURE",
                "2.1 Weekly register",
                "The register review happens weekly.",
            )
        ],
    )
    conn.execute(
        "insert into relationship_assertions (assertion_id, relation_type, src_ref,"
        " src_revision_id, dst_ref, dst_revision_id, status, review_state, derivation, recorded_from)"
        " values ('rel-dd3-addr', 'ADDRESSES', 'CIP-902/Cross Procedure v2.pdf', ?,"
        " 'CIP-901-1 R1 Part 1.1', NULL, 'machine_determined', 'machine_determined',"
        " 'operator_traceability', '2026-10-05')",
        (cross_rev,),
    )
    conn.execute(
        "insert into relationship_assertions (assertion_id, relation_type, src_ref,"
        " dst_ref, dst_revision_id, status, review_state, derivation, recorded_from)"
        " values ('rel-dd3-impl', 'IMPLEMENTS', 'CIP-901-1 R1 Part 1.1',"
        " 'isection-x1', ?, 'machine_determined', 'machine_determined',"
        " 'operator_traceability', '2026-10-05')",
        (cross_rev,),
    )
    # an operator note on the requirement
    conn.execute(
        "insert into operator_notes (note_id, subject_ref, kind, author, created_at,"
        " section_id, revision_id) values ('note-1', 'CIP-901-1 R1 Part 1.1', 'note',"
        " 'ACME', '2026-10-01', 'isection-x1', ?)",
        (cross_rev,),
    )
    conn.commit()
    return store


def _add_operator_document(
    store: Repository,
    logical_id: str,
    title: str,
    sections: list[tuple[str, str, str, str]],
) -> str:
    store.upsert_source_document(
        SourceDocument(
            logical_id=logical_id,
            title=title,
            issuer="ACME",
            source_kind="operating_procedure",
            jurisdiction="internal",
        )
    )
    revision = store.add_document_revision(logical_id, f"/docs/{logical_id}", title.encode("utf-8"))
    full = "\n".join(text for _, _, _, text in sections)
    store.put_document_text(
        revision.revision_id,
        full,
        page_count=1,
        extractor="fixture",
        extractor_version="0",
    )
    offset = 0
    for ordinal, (section_id, role, heading, text) in enumerate(sections):
        store.add_source_section(
            SourceSection(
                section_id=section_id,
                revision_id=revision.revision_id,
                path=heading,
                extractor="fixture",
                role=role,
                title=heading,
                unit_kind="prose",
                ordinal=ordinal,
                char_start=offset,
                char_end=offset + len(text),
                heading_path=heading,
            )
        )
        offset += len(text) + 1  # the joining newline
    return revision.revision_id


def _close(repo: Repository) -> None:
    repo.close()


def test_address_path_delivers_standard_parts_and_document_set(repo: Repository) -> None:
    try:
        payload = dd.build(repo, requirement_ref="CIP-901-1 R1")
    finally:
        _close(repo)
    assert payload["resolved"] is True
    print("DOCS INCLUDED:", payload["documents_included"])
    print(
        "TEXT SLICE:",
        repr(payload["text"][len(payload["text"]) // 2 : len(payload["text"]) // 2 + 700]),
    )
    print("DOCS DEFERRED:", payload["documents_deferred"])
    print("STANDARDS:", payload["standards"])
    assert payload["requirement_refs"] == [
        "CIP-901-1 R1",
        "CIP-901-1 R1 Part 1.1",
        "CIP-901-1 R1 Part 1.2",
    ]
    # (a) the standard: the requirement's lead sentence FIRST, then both Parts
    assert payload["requirement_refs"][0] == "CIP-901-1 R1"
    assert _LEAD in payload["text"]
    assert _REQUIREMENT in payload["text"] and _PART_1_2 in payload["text"]
    assert "== CIP-901-1 R1 ==" in payload["text"]
    # (b) the folder document, whole, labelled; TOC and revision-log rows
    # stripped by the projection's shared rule; furniture lines stripped from
    # delivered text; the approval block and the appendix KEPT (F-A2-4)
    assert "[ACME Asset Procedure § 3.1 Record assets] (isection-31)" in payload["text"]
    assert "The team records each asset." in payload["text"]
    assert "PRIVATE - FOR INTERNAL USE ONLY" not in payload["text"]
    assert "Page 1 of 9" not in payload["text"]
    assert "isection-revlog" not in payload["text"]
    assert "Added CIP-002 Visio flow chart process" not in payload["text"]
    assert "Table of Contents" not in payload["text"]
    assert "Owner: ACME." in payload["text"]  # the approval/owner block is citable
    assert "Appendix 1" in payload["text"]  # the operator's own declaration, verbatim
    # the traceability-named document travels with the folder's
    assert "Cross Procedure" in payload["text"]
    origins = {doc["logical_id"]: doc["origin"] for doc in payload["documents_included"]}
    assert origins["CIP-902/Cross Procedure v2.pdf"] == "traceability"
    assert origins["CIP-901/ACME Asset Procedure v1.pdf"] == "folder"
    # (d) traceability facts, labelled as the operator's declaration
    assert (
        "your Cross Procedure maps CIP-901-1 R1 Part 1.1 to §2.1 Weekly register" in payload["text"]
    )
    assert "operator's own declaration" in payload["text"]
    # the window block prices against the declared limits
    assert payload["window"]["context_limit"] == 131_072
    assert payload["window"]["budget_tokens"] == 131_072 - 24_576 - dd.PERSONA_TOOLS_RESERVE_TOKENS
    assert payload["window"]["fits"] is True
    assert payload["documents_deferred"] == []


def test_query_path_resolves_the_named_standard(repo: Repository) -> None:
    try:
        payload = dd.build(repo, query=f"CIP-901-1 asset register {_REQUIREMENT}")
    finally:
        _close(repo)
    assert payload["resolved"] is True
    assert "CIP-901-1" in payload["standards"]
    assert "CIP-901-1 R1 Part 1.1" in payload["requirement_refs"]
    assert _REQUIREMENT in payload["text"]


def test_unresolvable_ref_reports_and_delivers_nothing(repo: Repository) -> None:
    try:
        payload = dd.build(repo, requirement_ref="NOT-A-STANDARD R9")
    finally:
        _close(repo)
    assert payload["resolved"] is False
    assert payload["error"]
    assert payload["requirement_ids"] == []


def test_oversize_budget_defers_whole_documents_never_clips(repo: Repository) -> None:
    try:
        payload = dd.build(repo, requirement_ref="CIP-901-1 R1", context_limit=24_601)
    finally:
        _close(repo)
    # budget = 24601 - 24576 - reserve < 0: even (a) exceeds the budget, so no
    # document is forced in; the standard side still travels (never clipped)
    assert payload["window"]["fits"] is False
    deferred = {doc["logical_id"] for doc in payload["documents_deferred"]}
    assert "CIP-902/Cross Procedure v2.pdf" in deferred
    assert "CIP-901/ACME Asset Procedure v1.pdf" in deferred
    assert _REQUIREMENT in payload["text"]  # (a) always travels
    # every section that travels, travels whole
    assert "The team records each asset." in payload["text"] or "isection-31" not in payload["text"]
    listed = {doc["title"] for doc in payload["documents_deferred"]}
    assert listed == {"Cross Procedure", "ACME Asset Procedure"}


def test_tight_budget_fits_traceability_doc_defers_folder_doc(
    repo: Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    # budget = context_limit - predict - reserve; set the reserve so the
    # budget lands between the traceability doc (small) and the folder doc
    # (fattened below), which is exactly the spec's degradation order
    monkeypatch.setattr(dd, "PERSONA_TOOLS_RESERVE_TOKENS", 14_924)
    try:
        payload = dd.build(repo, requirement_ref="CIP-901-1 R1", context_limit=40_000)
    finally:
        _close(repo)
    included = {doc["logical_id"] for doc in payload["documents_included"]}
    assert included == {"CIP-902/Cross Procedure v2.pdf"}
    assert "The register review happens weekly." in payload["text"]
    assert "The team records each asset." not in payload["text"]
    assert [doc["logical_id"] for doc in payload["documents_deferred"]] == [
        "CIP-901/ACME Asset Procedure v1.pdf"
    ]
