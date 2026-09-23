"""Technical basis reaches every requirement it exists for, and no reading runs truncated.

Covers ``requirement_anchor.requirements_named`` / ``anchor_rationale_document``
(a separate Technical Rationale placed by its own headings),
``reading_assembly``'s fixed body dropping a TR once it travels per requirement,
``materialize_regulatory_corpus.capture_registered``'s hash guard, and
``sweep.window_fit`` (Ollama truncates an oversized prompt silently).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository
from portal.modules.compliance.core.requirement_anchor import (
    anchor_rationale_document,
    requirements_named,
)
from portal.modules.compliance.core.sweep import window_fit


@dataclass
class _Node:
    id: str
    requirement: str
    part: str = ""


def _capture(path: Path, units: list[tuple[str, str]]) -> CapturedDocument:
    out, buf, cursor = [], [], 0
    for ordinal, (heading, body) in enumerate(units):
        piece = body + "\n"
        out.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="prose",
                heading_path=heading,
                title=heading,
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path, page_count=1, full_text="".join(buf), units=out, reader_strings=()
    )


@pytest.fixture
def rationale(tmp_path: Path) -> tuple[Repository, str]:
    repo = Repository(tmp_path / "tb.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-010-4 technical rationale",
            title="TR",
            issuer="NERC",
            source_kind="technical_rationale",
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision(
        "NERC/CIP-010-4 technical rationale", "/docs/tr.pdf", b"tr-bytes"
    )
    store_capture(
        repo,
        revision.revision_id,
        _capture(
            Path("/docs/tr.pdf"),
            [
                ("Preface", "NERC is a not-for-profit international regulatory authority."),
                ("Rationale for Requirement R1", "Baselines let an entity detect change."),
                ("General Considerations for Requirements R1 and R2", "Monitoring follows."),
                ("Rational for Requirement 1 and Requirement 2", "Misspelled, still placed."),
                ("Requirement R4, Attachment 1, Section 1 - Managed TCAs", "TCA handling."),
                ("Section 4 - Scope of Applicability", "Applies to BES Cyber Systems."),
                ("Rationale for Requirement R9", "A requirement this version lacks."),
            ],
        ),
    )
    return repo, revision.revision_id


_NODES = [
    _Node("CIP-010-4 R1 Part 1.1", "R1", "1.1"),
    _Node("CIP-010-4 R1 Part 1.2", "R1", "1.2"),
    _Node("CIP-010-4 R2 Part 2.1", "R2", "2.1"),
    _Node("CIP-010-4 R4", "R4"),
    _Node("CIP-010-4 Attachment 1 Section 1", "Attachment 1 Section 1"),
]


def test_headings_name_requirements_and_attachment_sections() -> None:
    assert requirements_named("Rationale for Requirement R4") == ({"R4"}, None)
    assert requirements_named("General Considerations for Requirements R1 and R2")[0] == {
        "R1",
        "R2",
    }
    assert requirements_named("Rational for Requirement 1 and Requirement 2")[0] == {"R1", "R2"}
    assert requirements_named("Attachment 1 Section 6 Part 6.3 - Detecting") == (set(), ("1", "6"))
    # a standard's name is not a requirement, and a heading without the word places nothing
    assert requirements_named("Technical Rationale for Reliability Standard CIP-010-3") == (
        set(),
        None,
    )
    assert requirements_named("Preface") == (set(), None)


def test_rationale_sections_land_on_every_part_their_heading_names(rationale) -> None:
    repo, revision_id = rationale
    anchors, unplaced = anchor_rationale_document(repo, revision_id, _NODES)
    placed = {a.requirement_id: len(a.section_ids) for a in anchors}
    # R1 heading + "R1 and R2" + the misspelled "1 and 2" -> 3 sections on each R1 Part
    assert placed["CIP-010-4 R1 Part 1.1"] == 3 and placed["CIP-010-4 R1 Part 1.2"] == 3
    assert placed["CIP-010-4 R2 Part 2.1"] == 2
    assert placed["CIP-010-4 R4"] == 1
    assert placed["CIP-010-4 Attachment 1 Section 1"] == 1
    assert all(a.method == "heading" and a.relation == "technical_basis" for a in anchors)
    reasons = {u["heading"]: u["reason"] for u in unplaced}
    assert reasons["Preface"] == "heading names no requirement"
    # "Section 4" alone is the standard's applicability section, never guessed onto a Part
    assert reasons["Section 4 - Scope of Applicability"] == "heading names no requirement"
    assert "does not carry" in reasons["Rationale for Requirement R9"]
    repo.close()


def test_heading_placed_anchors_are_recorded_as_such(rationale) -> None:
    repo, revision_id = rationale
    anchors, _ = anchor_rationale_document(repo, revision_id, _NODES)
    repo.record_anchors(anchors)
    methods = {
        str(r[0])
        for r in repo._conn.execute(
            "SELECT DISTINCT anchor_method FROM requirement_sections WHERE revision_id = ?",
            (revision_id,),
        )
    }
    assert methods == {"heading"}
    from portal.modules.compliance.core.reading_assembly import _anchored_per_requirement

    assert _anchored_per_requirement(repo, revision_id)
    repo.close()


def test_capture_registered_never_captures_from_the_wrong_bytes(tmp_path: Path) -> None:
    from scripts.materialize_regulatory_corpus import capture_registered

    repo = Repository(tmp_path / "reg.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-013-2 technical rationale",
            title="TR",
            issuer="NERC",
            source_kind="technical_rationale",
            jurisdiction="US",
        )
    )
    moved = tmp_path / "moved.pdf"
    moved.write_bytes(b"different bytes now")
    repo.add_document_revision("NERC/CIP-013-2 technical rationale", str(moved), b"original")
    gone = tmp_path / "gone.pdf"
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-012-2 technical rationale",
            title="TR",
            issuer="NERC",
            source_kind="technical_rationale",
            jurisdiction="US",
        )
    )
    repo.add_document_revision("NERC/CIP-012-2 technical rationale", str(gone), b"x")
    result = capture_registered(repo)
    assert result["captured"] == []
    reasons = sorted(s["reason"].split(":")[0] for s in result["skipped"])
    assert reasons == ["bytes on disk no longer match the revision", "file missing"]
    repo.close()


def test_window_fit_refuses_what_ollama_would_truncate() -> None:
    # CIP-003-8 R1: 155,333 bytes, counted at 16,387 tokens after silent truncation
    assert window_fit(155_333, 32_768, 3_072)["fits"] is False
    assert window_fit(155_333, 65_536, 3_072)["fits"] is True
    # CIP-007-6 R5 Part 5.1: 90,894 bytes, 25,160 real tokens — fits
    assert window_fit(90_894, 32_768, 3_072)["fits"] is True
