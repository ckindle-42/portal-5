"""Fidelity gates for whole-document capture (BILATERAL_CORPUS_V1 P1).

These are hermetic: a stub layout document stands in for docling, so the gates
run with no network, no models and no PDFs. The same gates run against the real
regulatory PDFs in ``scripts/verify_compliance_bilateral.py --live``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import capture as cap


class _Prov:
    def __init__(self, page_no: int) -> None:
        self.page_no = page_no


class _Cell:
    def __init__(self, text: str, column_header: bool = False) -> None:
        self.text = text
        self.column_header = column_header


class _TableData:
    def __init__(self, grid: list[list[_Cell]]) -> None:
        self.grid = grid


class _Item:
    def __init__(self, kind: str, page: int, **kw: object) -> None:
        self._kind = kind
        self.prov = [_Prov(page)]
        for key, value in kw.items():
            setattr(self, key, value)


def _named(kind: str) -> type:
    return type(
        kind,
        (_Item,),
        {"__init__": lambda self, page, **kw: _Item.__init__(self, kind, page, **kw)},
    )


SectionHeaderItem = _named("SectionHeaderItem")
TextItem = _named("TextItem")
ListItem = _named("ListItem")
TableItem = _named("TableItem")


class _Doc:
    def __init__(self, items: list[tuple[object, int]], pages: int) -> None:
        self._items = items
        self.pages = dict.fromkeys(range(1, pages + 1), None)

    def iterate_items(self):  # noqa: ANN201 - mirrors the docling API
        return iter(self._items)


def _requirements_table(ref: str, caption: str, part: str) -> TableItem:
    header = [_Cell(caption, True)] * 4
    columns = [
        _Cell("Part", True),
        _Cell("Applicable Systems", True),
        _Cell("Requirements", True),
        _Cell("Measures", True),
    ]
    body = [
        _Cell(part),
        _Cell("High Impact BES Cyber Systems"),
        _Cell(f"Do the thing described by {part}."),
        _Cell(f"Evidence for {part} may include dated records."),
    ]
    return TableItem(3, data=_TableData([header, columns, body]), self_ref=ref)


@pytest.fixture
def doc() -> _Doc:
    items: list[tuple[object, int]] = [
        (SectionHeaderItem(1, text="A. Introduction", level=1), 1),
        (ListItem(1, text="Title: Cyber Security"), 1),
        (SectionHeaderItem(1, text="6. Background:", level=1), 2),
        (
            TextItem(
                2,
                text=(
                    "Items in a requirement that are linked with an 'or' are "
                    "alternatives; numbered items are cumulative."
                ),
            ),
            1,
        ),
        (SectionHeaderItem(1, text="B. Requirements and Measures", level=1), 3),
        (_requirements_table("#/tables/0", "Table R2 - Security Patch Management", "2.1"), 1),
        (_requirements_table("#/tables/1", "Table R2 - Security Patch Management", "2.2"), 1),
        (SectionHeaderItem(1, text="Violation Severity Levels", level=1), 4),
        (TextItem(4, text="Lower VSL: the entity did the thing late."), 1),
        (SectionHeaderItem(1, text="Version History", level=1), 5),
        (TextItem(5, text="Version 5 revised to use RBS Template."), 1),
    ]
    return _Doc(items, pages=5)


@pytest.fixture
def captured(doc: _Doc, tmp_path: Path) -> cap.CapturedDocument:
    pdf = tmp_path / "cip-stub.pdf"
    pdf.write_bytes(b"%PDF-stub")
    return cap.capture_document(pdf, doc=doc, page_count=5)


class TestFidelityGates:
    def test_character_coverage_is_total(self, captured: cap.CapturedDocument) -> None:
        report = cap.fidelity_report(captured)
        assert report["character_coverage_pct"] == 100.0
        assert report["gaps"] == []

    def test_no_character_is_double_assigned(self, captured: cap.CapturedDocument) -> None:
        assert cap.fidelity_report(captured)["overlaps"] == []
        seen = [0] * len(captured.full_text)
        for unit in captured.units:
            for i in range(unit.char_start, unit.char_end):
                seen[i] += 1
        assert set(seen) == {1}

    def test_every_page_is_covered(self, captured: cap.CapturedDocument) -> None:
        assert cap.fidelity_report(captured)["missing_pages"] == []

    def test_reconstruction_diff_is_empty(self, captured: cap.CapturedDocument) -> None:
        report = cap.fidelity_report(captured)
        assert report["reconstruction_diff"] == ""
        ordered = sorted(captured.units, key=lambda u: u.ordinal)
        assert "".join(u.text for u in ordered) == captured.full_text

    def test_every_reader_string_survives(self, captured: cap.CapturedDocument) -> None:
        report = cap.fidelity_report(captured)
        assert report["reader_strings"] > 0
        assert report["reader_strings_absent"] == 0

    def test_assert_faithful_passes(self, captured: cap.CapturedDocument) -> None:
        assert cap.assert_faithful(captured)["reconstruction_diff"] == ""


class TestNothingIsDiscarded:
    """The passages the pre-P1 extractor terminated on are present."""

    @pytest.mark.parametrize(
        "needle",
        [
            "Lower VSL",
            "Version 5 revised to use RBS Template",
            "alternatives",
            "Table R2 - Security Patch Management",
        ],
    )
    def test_passage_is_captured(self, captured: cap.CapturedDocument, needle: str) -> None:
        assert needle in captured.full_text
        assert any(needle in u.text for u in captured.units)


class TestTableRoundTrip:
    def test_table_shape_is_preserved(self, captured: cap.CapturedDocument) -> None:
        shape = cap.table_shape(captured, "#/tables/0")
        assert shape["columns"] == ["Part", "Applicable Systems", "Requirements", "Measures"]
        assert shape["rows"] == 1
        assert shape["cells_per_row"] == [4]

    def test_r2_yields_one_part_row_per_part_with_its_own_cells(
        self, captured: cap.CapturedDocument
    ) -> None:
        rows = [u for u in captured.units if u.unit_kind == "table_row"]
        assert [r.cells[0] for r in rows] == ["2.1", "2.2"]
        for row in rows:
            assert len(row.cells) == 4
            assert row.columns == ["Part", "Applicable Systems", "Requirements", "Measures"]
            # the Measure stays attached to ITS Part, not to the table at large
            assert row.cells[0] in row.cells[3]

    def test_a_row_resolves_to_its_parent_table(self, captured: cap.CapturedDocument) -> None:
        rows = [u for u in captured.units if u.unit_kind == "table_row"]
        parents = {u.table_ref for u in captured.units if u.unit_kind == "table"}
        assert {r.table_ref for r in rows} <= parents


class TestPositionalOnly:
    def test_unit_kinds_are_the_declared_set(self, captured: cap.CapturedDocument) -> None:
        assert {u.unit_kind for u in captured.units} <= set(cap.UNIT_KINDS)

    def test_heading_path_comes_from_the_documents_own_outline(
        self, captured: cap.CapturedDocument
    ) -> None:
        paths = {u.heading_path for u in captured.units}
        assert "B. Requirements and Measures" in paths
        assert "Version History" in paths

    def test_role_is_a_positional_fact(self) -> None:
        assert (
            cap.positional_role("B. Requirements and Measures > R2")
            == "B_REQUIREMENTS_AND_MEASURES"
        )
        assert cap.positional_role("") == "FRONT_MATTER"


class TestUncoveredPagesAreFilledNotSkipped:
    def test_a_page_the_reader_ignored_still_gets_a_unit(self, tmp_path: Path) -> None:
        doc = _Doc([(TextItem(1, text="only page one has an item"), 1)], pages=2)
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-stub")
        captured = cap.capture_document(pdf, doc=doc, page_count=2)
        report = cap.fidelity_report(captured)
        assert report["missing_pages"] == []
        assert any(u.page_start == 2 for u in captured.units)


class TestLossyCaptureCannotReachTheStore:
    def test_assert_faithful_raises_on_a_gap(self, captured: cap.CapturedDocument) -> None:
        broken = cap.CapturedDocument(
            path=captured.path,
            page_count=captured.page_count,
            full_text=captured.full_text,
            units=captured.units[:-1],
            reader_strings=captured.reader_strings,
        )
        with pytest.raises(ValueError, match="not faithful"):
            cap.assert_faithful(broken)


class TestInternalCorpusTilesCompletely:
    def test_sectionize_leaves_no_gap(self) -> None:
        from portal.modules.compliance.core.internal_corpus import sectionize

        pages = [
            "LSPG Procedure\nDocument Type: Procedure\n",
            "Table of Contents\n1.0 Purpose ...... 3\n2.0 Scope ...... 4\n",
            "trailing text nobody gave a heading\n1.0 Purpose\nThe purpose is to do the thing.\n",
            "2.0 Scope\nApplies to everything.\ntail matter after the last heading\n",
        ]
        full = "\n".join(pages)
        sections = sectionize(pages, operative_role="OPERATIVE_PROCEDURE")
        cursor = 0
        for section in sorted(sections, key=lambda s: s.char_start):
            assert section.char_start == cursor, f"gap or overlap at {section.path}"
            assert section.text == full[section.char_start : section.char_end]
            cursor = section.char_end
        assert cursor == len(full)

    def test_the_table_of_contents_no_longer_hides_the_cover_block(self) -> None:
        from portal.modules.compliance.core.internal_corpus import sectionize

        pages = ["cover\n", "Table of Contents\n1.0 x ... 3\n", "1.0 Purpose\nbody\n"]
        sections = sectionize(pages, operative_role="OPERATIVE_PROCEDURE")
        roles = [s.role for s in sorted(sections, key=lambda s: s.char_start)]
        assert roles[0] == "DOCUMENT_CONTROL"
        assert "TABLE_OF_CONTENTS" in roles
