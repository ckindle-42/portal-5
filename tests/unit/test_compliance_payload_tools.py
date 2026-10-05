"""DATA_TRUTH Amendment 2 DD3c — every reader-facing tool that resolves a
requirement carries the dual-document payload, hermetically.

Coverage link standing: approved links and the operator's traceability
declarations set ``has_link``; similarity proposals are labelled and do not.
Timeline carries EVERY revision's normative anchors for the addressed
requirement. Requirement travels with the payload by address.
"""

from __future__ import annotations

import pathlib

import pytest

from portal.modules.compliance.core.models import SourceDocument, SourceSection
from portal.modules.compliance.core.repository import Repository

_LEAD_V1 = "Version one required recording each asset by hand."
_LEAD_V2 = "Version two requires recording each asset in the register."
_PART_V2 = "Record each asset in the operations register every week."


@pytest.fixture
def cross_repo(tmp_path: pathlib.Path) -> Repository:
    """Two revisions of one synthetic standard, each anchoring R1's words."""
    store = Repository(tmp_path / "dd3c.db")
    store.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-904-1",
            title="NERC/CIP-904-1",
            issuer="synthetic",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    store.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-904-2",
            title="NERC/CIP-904-2",
            issuer="synthetic",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    for logical_id, lead in (
        ("NERC/CIP-904-1", _LEAD_V1),
        ("NERC/CIP-904-2", _LEAD_V2),
    ):
        revision = store.add_document_revision(
            logical_id,
            f"/docs/{logical_id}.pdf",
            lead.encode("utf-8"),
            binding_effect="regulatory",
            effective_date="2025-01-01" if "904-1" in logical_id else "2026-01-01",
        )
        store.put_document_text(
            revision.revision_id,
            lead,
            page_count=1,
            extractor="fixture",
            extractor_version="0",
        )
        store.add_source_section(
            SourceSection(
                section_id=f"csection-{logical_id.split('-')[-1]}",
                revision_id=revision.revision_id,
                path="B. Requirements / R1",
                extractor="fixture",
                role="B_REQUIREMENTS_AND_MEASURES",
                title="R1",
                unit_kind="table_row",
                ordinal=0,
                char_start=0,
                char_end=len(lead),
                heading_path="R1",
            )
        )
        store._conn.execute(
            "insert into requirement_sections (requirement_id, revision_id, section_id,"
            " relation, char_start, char_end, occurrences, anchor_method, anchored_at,"
            " extractor_version) values (?,?,?,?,?,?,1,'exact','2026-10-05','fixture')",
            (
                f"{logical_id.split('/')[-1]} R1",
                revision.revision_id,
                f"csection-{logical_id.split('-')[-1]}",
                "governing",
                0,
                len(lead),
            ),
        )
    store._conn.commit()
    return store


def test_build_cross_revision_carries_both_revisions_normative_text(
    cross_repo: Repository,
) -> None:
    payload = dual_document_cross_revision(cross_repo, "CIP-904-2 R1")
    assert payload["resolved"] is True
    assert "CIP-904-1 R1" in payload["requirement_refs"]
    assert "CIP-904-2 R1" in payload["requirement_refs"]
    assert _LEAD_V1 in payload["text"]  # the predecessor's words travel
    assert _LEAD_V2 in payload["text"]
    assert "revision comparison" in payload["resolution"]


def dual_document_cross_revision(repo: Repository, ref: str) -> dict:
    from portal.modules.compliance.core import dual_document

    return dual_document.build_cross_revision(
        repo, ref, context_limit=131_072, predict_limit=24_576
    )


# ── coverage link standing ───────────────────────────────────────────────────


def test_coverage_counts_declarations_and_labels_proposals(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.compliance.core import runtime_config
    from portal.modules.compliance.core.models import SourceDocument
    from portal.modules.compliance.core.repository import Repository
    from portal.modules.compliance.tools import compliance_mcp

    store = Repository(tmp_path / "cov.db")
    store.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-905-1",
            title="NERC/CIP-905-1",
            issuer="synthetic",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    store.upsert_source_document(
        SourceDocument(
            logical_id="CIP-905/ACME Procedure v1.pdf",
            title="ACME Procedure",
            issuer="ACME",
            source_kind="operating_procedure",
            jurisdiction="internal",
        )
    )
    revision = store.add_document_revision(
        "CIP-905/ACME Procedure v1.pdf", "/docs/acme.pdf", b"ACME Procedure"
    )
    store.put_document_text(
        revision.revision_id,
        "The team records each asset.",
        page_count=1,
        extractor="fixture",
        extractor_version="0",
    )
    for sid, role in (
        ("isection-approved", "OPERATIVE_PROCEDURE"),
        ("isection-declared", "OPERATIVE_PROCEDURE"),
        ("isection-proposed", "OPERATIVE_PROCEDURE"),
    ):
        store.add_source_section(
            SourceSection(
                section_id=sid,
                revision_id=revision.revision_id,
                path="3.1 Body",
                extractor="fixture",
                role=role,
                title="3.1",
                unit_kind="prose",
                ordinal=0,
                char_start=0,
                char_end=27,
                heading_path="3.1",
            )
        )
    conn = store._conn
    for assertion_id, dst, status, derivation in (
        ("rel-a", "isection-approved", "approved", "reading"),
        ("rel-d", "isection-declared", "machine_determined", "operator_traceability"),
        ("rel-p", "isection-proposed", "proposed", "folder_cartesian"),
    ):
        conn.execute(
            "insert into relationship_assertions (assertion_id, relation_type, src_ref,"
            " dst_ref, status, derivation, recorded_from)"
            " values (?, 'IMPLEMENTS', 'CIP-905-1 R1', ?, ?, ?, '2026-10-05')",
            (assertion_id, dst, status, derivation),
        )
    conn.commit()

    monkeypatch.setattr(compliance_mcp, "_repo", lambda: store)
    monkeypatch.setattr(runtime_config, "reading_route_ceiling", lambda: None)

    result = compliance_mcp.compliance_coverage(standard="CIP-905-1", requirement="R1")
    (row,) = result["requirements"]
    assert row["has_link"] is True  # the declaration counts
    linked = {s["section_id"] for s in row["linked_sections"]}
    assert linked == {"isection-approved"}
    declared = {s["section_id"] for s in row["operator_declared_sections"]}
    assert declared == {"isection-declared"}
    assert all("declaration" in s["standing"] for s in row["operator_declared_sections"])
    proposals = {p["dst_ref"] for p in row["unverified_proposals"]}
    assert proposals == {"isection-proposed"}
    assert all("unverified" in p["standing"] for p in row["unverified_proposals"])
    # the payload rides along, priced and resolved
    assert result["dual_document"]["resolved"] is True
    assert result["dual_document"]["window"]["context_limit"] == 131_072
    store.close()
