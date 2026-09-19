"""The reading assembly and the addressability surface (BILATERAL_CORPUS_V1 P5).

Hermetic: a miniature standard is captured into a tmp store, so the assembly's
structural selection, its budget behaviour and its refusal to suppress anything
are all checked without PDFs, models or a live index.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import reading_assembly as ra
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository

#: (heading_path, unit_kind, text) in reading order — a standard's own outline.
STANDARD = [
    ("A. Introduction", "prose", "A. Introduction"),
    ("A. Introduction > 4. Applicability:", "prose", "4. Applicability:"),
    (
        "A. Introduction > 4. Applicability:",
        "prose",
        "4.2.3 Exemptions: Cyber Assets at Facilities regulated by the NRC are exempt.",
    ),
    ("A. Introduction > 6. Background:", "prose", "6. Background:"),
    (
        "A. Introduction > 6. Background:",
        "prose",
        "Items in a requirement that are linked with an 'or' are alternatives; "
        "numbered items are cumulative.",
    ),
    ("A. Introduction > 5. Effective Dates:", "prose", "See the Implementation Plan."),
    ("B. Requirements and Measures", "prose", "B. Requirements and Measures"),
    (
        "B. Requirements and Measures",
        "prose",
        "R2. Each Responsible Entity shall implement one or more documented processes.",
    ),
    ("B. Requirements and Measures", "table", "CIP-007-6 Table R2 - Security Patch Management"),
    (
        "B. Requirements and Measures",
        "table_row",
        "2.1 | High Impact BES Cyber Systems | A patch management process. | Evidence of a process.",
    ),
    (
        "B. Requirements and Measures",
        "table_row",
        "2.2 | High Impact BES Cyber Systems | At least once every 35 calendar days, evaluate "
        "security patches. | An evaluation record.",
    ),
    (
        "B. Requirements and Measures",
        "prose",
        "R3. Each Responsible Entity shall do another thing.",
    ),
    ("C. Compliance > 1.2. Evidence Retention:", "prose", "Keep data for three calendar years."),
    ("C. Compliance > 2. Table of Compliance Elements", "table", "R # | Lower VSL | Severe VSL"),
    (
        "C. Compliance > 2. Table of Compliance Elements",
        "table_row",
        "R2 | The entity evaluated patches in 36 days. | The entity did not evaluate patches.",
    ),
    (
        "C. Compliance > 2. Table of Compliance Elements",
        "table_row",
        "R3 | Something about R3. | Something worse about R3.",
    ),
    ("Version History", "prose", "Version 5 revised to use RBS Template."),
    (
        "Guidelines and Technical Basis > Requirement R2:",
        "prose",
        "The intent is to know, track and mitigate the known software vulnerabilities. "
        'It is not strictly an "install every security patch" requirement.',
    ),
    (
        "Guidelines and Technical Basis > Rationale for Requirement R2:",
        "prose",
        "Rationale: security patch management protects against known vulnerabilities.",
    ),
]


def _capture(path: Path, rows: list[tuple[str, str, str]]) -> CapturedDocument:
    units: list[CapturedUnit] = []
    buf: list[str] = []
    cursor = 0
    for ordinal, (heading, kind, body) in enumerate(rows):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind=kind,
                heading_path=heading,
                title=heading.rsplit(" > ", 1)[-1],
                page_start=(ordinal // 3) + 1,
                page_end=(ordinal // 3) + 1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
                table_ref="#/tables/0" if kind in ("table", "table_row") else "",
                row_index=ordinal if kind == "table_row" else -1,
                columns=["Part", "Applicable Systems", "Requirements", "Measures"]
                if kind == "table_row"
                else [],
                cells=[c.strip() for c in body.split("|")] if kind == "table_row" else [],
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=(len(rows) // 3) + 1,
        full_text="".join(buf),
        units=units,
        reader_strings=tuple(b for _h, _k, b in rows),
    )


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="NERC/CIP-007-6",
            title="CIP-007-6",
            issuer="NERC",
            source_kind="regulatory_standard",
            jurisdiction="US",
        )
    )
    revision = repo.add_document_revision("NERC/CIP-007-6", "/docs/cip-007-6.pdf", b"cip0076")
    repo.set_regulatory_lifecycle(
        revision.revision_id, effective_date="2016-07-01", inactive_date="2028-06-30"
    )
    store_capture(repo, revision.revision_id, _capture(Path("/docs/cip-007-6.pdf"), STANDARD))
    yield repo
    repo.close()


class TestAddressing:
    @pytest.mark.parametrize(
        ("ref", "standard", "requirement", "part"),
        [
            ("CIP-007-6", "CIP-007-6", "", ""),
            ("CIP-007-6 R2", "CIP-007-6", "2", ""),
            ("CIP-007-6 R2 Part 2.2", "CIP-007-6", "2", "2.2"),
            ("cip-007-7.1 r5 part 5.1.1", "CIP-007-7.1", "5", "5.1.1"),
        ],
    )
    def test_a_regulatory_address_parses(
        self, ref: str, standard: str, requirement: str, part: str
    ) -> None:
        parsed = ra.parse_ref(ref)
        assert parsed is not None
        assert (parsed.standard, parsed.requirement, parsed.part) == (standard, requirement, part)

    def test_an_attachment_address_parses_and_round_trips(self) -> None:
        # A5 (COMPLIANCE_FAMILY_CENSUS_V1 §5): the register carries CIP-002-5.1a's
        # Attachment 1 structure as requirement nodes; the grammar refusing them
        # made the categorisation root unreadable by the sweep.
        for ref in (
            "CIP-002-5.1a Attachment 1 Part 2.3",
            "cip-002-5.1a attachment 1 part 2.3",
        ):
            parsed = ra.parse_ref(ref)
            assert parsed is not None
            assert str(parsed) == "CIP-002-5.1a Attachment 1 Part 2.3"
            assert parsed.attachment == "1"
            assert parsed.part == "2.3"
        section = ra.parse_ref("CIP-002-5.1a Attachment 1 Section 1")
        assert section is not None
        assert str(section) == "CIP-002-5.1a Attachment 1 Section 1"
        assert section.section == "1"

    def test_a_non_address_is_not_forced_into_one(self) -> None:
        assert ra.parse_ref("csection-abc123") is None
        assert ra.parse_ref("LSPG Patching Procedure v3") is None


class TestTheWholeNeighbourhood:
    def test_every_component_the_question_needs_is_present(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2")
        present = {c["component"] for c in out["components"]}
        for component in (
            "requirement",
            "technical_basis",
            "rationale",
            "vsl",
            "applicability",
            "background",
            "compliance_and_evidence_retention",
            "version_history",
        ):
            assert component in present, component

    def test_the_intent_of_the_requirement_is_reachable(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2")
        text = "\n".join(s["text"] for c in out["components"] for s in c["sections"])
        assert "not strictly an" in text
        assert "know, track and mitigate" in text

    def test_the_standards_own_reading_convention_is_reachable(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2")
        text = "\n".join(s["text"] for c in out["components"] for s in c["sections"])
        assert "linked with an 'or' are alternatives" in text

    def test_nothing_is_marked_ineligible_to_cite(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2")
        for component in out["components"]:
            for section in component["sections"]:
                assert "not selectable" not in str(section).lower()
                assert section["section_id"]


class TestStructuralSelection:
    def test_only_this_requirements_rows_are_gathered(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2", include=["requirement"])
        text = "\n".join(s["text"] for c in out["components"] for s in c["sections"])
        assert "R2." in text
        assert "R3. Each Responsible Entity" not in text

    def test_a_part_narrows_to_its_own_row(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2 Part 2.2", include=["requirement"])
        rows = [
            s for c in out["components"] for s in c["sections"] if s["unit_kind"] == "table_row"
        ]
        assert [r["cells"][0]["text"] for r in rows] == ["2.2"]

    def test_a_row_carries_its_cells_under_their_column_names(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2 Part 2.2", include=["requirement"])
        row = next(
            s for c in out["components"] for s in c["sections"] if s["unit_kind"] == "table_row"
        )
        columns = [cell["column"] for cell in row["cells"]]
        assert columns == ["Part", "Applicable Systems", "Requirements", "Measures"]
        measures = next(c["text"] for c in row["cells"] if c["column"] == "Measures")
        assert measures == "An evaluation record."

    def test_only_this_requirements_vsl_rows_are_gathered(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2", include=["vsl"])
        text = "\n".join(s["text"] for c in out["components"] for s in c["sections"])
        assert "The entity evaluated patches in 36 days" in text
        assert "Something about R3" not in text


class TestTheBudget:
    def test_a_tight_budget_names_what_it_dropped(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2", budget_tokens=40)
        assert out["omitted"], "a budget that dropped nothing proves nothing"
        for entry in out["omitted"]:
            assert entry["component"]
            assert entry["tokens"] >= 0
            assert "budget" in entry["reason"]

    def test_the_requirement_itself_is_never_dropped(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2", budget_tokens=1)
        assert [c["component"] for c in out["components"]][:1] == ["requirement"]

    def test_a_generous_budget_omits_nothing(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2", budget_tokens=1_000_000)
        assert out["omitted"] == []
        assert out["tokens_used"] <= 1_000_000


class TestProvenanceOnEveryUnit:
    def test_a_regulatory_unit_carries_enough_to_cite_it(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-007-6 R2", include=["requirement"])
        section = out["components"][0]["sections"][0]
        assert section["section_id"]
        assert section["revision_id"]
        assert section["page"]
        assert section["headings"]
        assert out["revision"]["effective_date"] == "2016-07-01"
        assert out["revision"]["inactive_date"] == "2028-06-30"

    def test_an_unknown_standard_is_an_error_not_an_empty_assembly(self, store: Repository) -> None:
        out = ra.assemble(store, "CIP-999-1 R1")
        assert "error" in out
        assert "not in the store" in out["error"]


class TestNoModelCallAndNoScore:
    def test_the_assembly_is_deterministic(self, store: Repository) -> None:
        a = ra.assemble(store, "CIP-007-6 R2")
        b = ra.assemble(store, "CIP-007-6 R2")
        assert [c["component"] for c in a["components"]] == [
            c["component"] for c in b["components"]
        ]
        assert a["tokens_used"] == b["tokens_used"]
        assert a["assembly"].startswith("deterministic")
