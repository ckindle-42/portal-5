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
    anchor_standard_attachment_gtb,
    attachment_targets_named,
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


def test_attachment_grammars_are_parsed_not_guessed() -> None:
    assert attachment_targets_named("Requirement R2, Attachment 1, Section 3 - ESPs") == {
        "attachment": "1",
        "section": "3",
        "part": None,
        "impact": None,
    }
    assert attachment_targets_named("Attachment 1, Criterion 2.1")["part"] == "2.1"
    assert attachment_targets_named("Medium Impact Rating (M)") == {
        "attachment": "1",
        "section": "2",
        "part": None,
        "impact": "medium impact rating",
    }
    assert attachment_targets_named("Requirement R2, Attachment 1")["attachment"] == "1"
    # no attachment named → this route stays out of it
    assert attachment_targets_named("Guidelines and Technical Basis")["attachment"] is None
    assert (
        attachment_targets_named("Requirement R2: identify BES Cyber Systems")["attachment"] is None
    )


@pytest.fixture
def standard_gtb(tmp_path: Path) -> tuple[Repository, str]:
    repo = Repository(tmp_path / "gtb.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-X-1",
            title="CIP-X-1",
            issuer="NERC",
            source_kind="standard",
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision("NERC/CIP-X-1", "/docs/std.pdf", b"std-bytes")
    store_capture(
        repo,
        revision.revision_id,
        _capture(
            Path("/docs/std.pdf"),
            [
                ("Guidelines and Technical Basis", "The guidance lives here."),
                (
                    "Requirement R2, Attachment 1",
                    "Attachment 1 contains the sections that must be included in the cyber "
                    "security policy, and this guidance explains how to apply each of those "
                    "sections to the entity's own policy document.",
                ),
                (
                    "Requirement R2, Attachment 1, Section 3 - Electronic Access Controls",
                    "Guidance for section 3 of the attachment, in the drafting team's own "
                    "words, explaining the electronic access control approaches the guidance "
                    "considers acceptable for a low impact BES Cyber System.",
                ),
                (
                    "Requirement R2, Attachment 1, Section 3 - Electronic Access Controls",
                    "A heading row",
                ),
                (
                    "Medium Impact Rating (M)",
                    "Guidance for the medium impact criteria, which the requirement's own "
                    "measures file under Attachment 1, Section 2, covering generation and "
                    "transmission thresholds in detail.",
                ),
                (
                    "Attachment 1, Criterion 2.1",
                    "Guidance addressed to criterion 2.1 and nothing else in the attachment, "
                    "with the reasoning behind the 3,000 MW threshold for BA Control Centres.",
                ),
                ("Overall Application", "No attachment named; nothing here is placed."),
            ],
        ),
    )
    return repo, revision.revision_id


_GTB_NODES = [
    _Node("CIP-X-1 R2 Part 2.1", "R2", "2.1"),
    _Node("CIP-X-1 Attachment 1 Part 3", "Attachment 1", "3"),
    _Node("CIP-X-1 Attachment 1 Part 3.1", "Attachment 1", "3.1"),
    _Node("CIP-X-1 Attachment 1 Part 2.1", "Attachment 1", "2.1"),
    _Node("CIP-X-1 Attachment 1 Part 2.2", "Attachment 1", "2.2"),
    _Node("CIP-X-1 Attachment 1 Section 2", "Attachment 1 Section 2"),
]


def test_standard_gtb_attachment_guidance_lands_on_the_nodes_its_headings_name(
    standard_gtb,
) -> None:
    repo, revision_id = standard_gtb
    anchors, unplaced = anchor_standard_attachment_gtb(repo, revision_id, _GTB_NODES)
    placed = {a.requirement_id: a for a in anchors}
    # the bare attachment heading guides every Attachment 1 part; section 3's
    # heading guides its parts; the impact-rating alias reaches section 2's
    # parent and parts; the criterion heading reaches exactly part 2.1
    assert set(placed) == {
        "CIP-X-1 Attachment 1 Part 3",
        "CIP-X-1 Attachment 1 Part 3.1",
        "CIP-X-1 Attachment 1 Part 2.1",
        "CIP-X-1 Attachment 1 Part 2.2",
        "CIP-X-1 Attachment 1 Section 2",
    }
    assert placed["CIP-X-1 Attachment 1 Part 2.1"].method == "heading"
    # bare attachment + impact alias (section 2) + the criterion's own heading
    assert len(placed["CIP-X-1 Attachment 1 Part 2.1"].section_ids) == 3
    assert len(placed["CIP-X-1 Attachment 1 Part 2.2"].section_ids) == 2  # bare + alias
    assert placed["CIP-X-1 Attachment 1 Section 2"].section_ids == [
        placed["CIP-X-1 Attachment 1 Section 2"].section_ids[0]
    ]  # the alias alone reaches the section parent
    assert placed["CIP-X-1 Attachment 1 Part 3.1"].relation == "technical_basis"
    # R-level nodes are never placed here — the exact route owns them
    assert "CIP-X-1 R2 Part 2.1" not in placed
    reasons = {u["heading"]: u["reason"] for u in unplaced}
    assert any("heading row" in r for r in reasons.values())
    assert "Overall Application" not in reasons  # not this route's business at all
    repo.close()


def test_standard_gtb_route_never_places_without_a_headed_node(standard_gtb) -> None:
    repo, revision_id = standard_gtb
    anchors, unplaced = anchor_standard_attachment_gtb(repo, revision_id, [_GTB_NODES[0]])
    assert anchors == []
    repo.close()
