"""office_contains parses produced office files; it never greps the binary."""

from __future__ import annotations

import pytest

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, check_office_contains
from tests.wfe.schema import Outcome

docx = pytest.importorskip("docx")
openpyxl = pytest.importorskip("openpyxl")
pptx = pytest.importorskip("pptx")


def _run(tmp_path, kind, expect, name):
    spec = {"type": "office_contains", "path": name, "kind": kind, "expect": expect}
    return check_office_contains(spec, CheckContext(sandbox_root=tmp_path))


def test_docx_paragraphs_and_table_cells(tmp_path):
    d = docx.Document()
    d.add_heading("Quarterly Plan", 1)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Owner", "Mara Quill"
    d.save(tmp_path / "a.docx")
    assert (
        _run(tmp_path, "docx", ["Quarterly Plan", "Mara Quill"], "a.docx").outcome == Outcome.PASS
    )
    assert _run(tmp_path, "docx", ["Mara Quill", "Nobody"], "a.docx").outcome == Outcome.FAIL


def test_xlsx_cells_and_pptx_titles(tmp_path):
    wb = openpyxl.Workbook()
    wb.active["B2"] = 4417
    wb.save(tmp_path / "a.xlsx")
    assert _run(tmp_path, "xlsx", ["4417"], "a.xlsx").outcome == Outcome.PASS
    assert _run(tmp_path, "xlsx", ["4418"], "a.xlsx").outcome == Outcome.FAIL
    p = pptx.Presentation()
    p.slides.add_slide(p.slide_layouts[5]).shapes.title.text = "Roadmap"
    p.save(tmp_path / "a.pptx")
    assert _run(tmp_path, "pptx", ["Roadmap"], "a.pptx").outcome == Outcome.PASS


def test_exact_values_must_be_a_whole_cell_not_a_substring(tmp_path):
    # wfe_documents_20261017h doc-trip-01: expect "3" passed a workbook holding "13"
    wb = openpyxl.Workbook()
    wb.active.append(["Large orders", 13])
    wb.save(tmp_path / "a.xlsx")
    spec = {"type": "office_contains", "path": "a.xlsx", "kind": "xlsx", "expect": ["Large"]}
    ctx = CheckContext(sandbox_root=tmp_path)
    assert check_office_contains({**spec, "exact": ["3"]}, ctx).outcome == Outcome.FAIL
    assert check_office_contains({**spec, "exact": ["13"]}, ctx).outcome == Outcome.PASS
    assert check_office_contains({**spec, "exact": ["13.0"]}, ctx).outcome == Outcome.PASS


def test_a_grep_of_the_binary_would_not_pass_but_parsing_does(tmp_path):
    d = docx.Document()
    d.add_paragraph("needle-value-77")
    d.save(tmp_path / "a.docx")
    assert b"needle-value-77" not in (tmp_path / "a.docx").read_bytes()  # zip-compressed
    assert _run(tmp_path, "docx", ["needle-value-77"], "a.docx").outcome == Outcome.PASS


def test_missing_corrupt_and_escaping_files_fail(tmp_path):
    assert _run(tmp_path, "docx", ["x"], "none.docx").outcome == Outcome.FAIL
    (tmp_path / "bad.xlsx").write_bytes(b"not a zip")
    assert _run(tmp_path, "xlsx", ["x"], "bad.xlsx").outcome == Outcome.FAIL
    assert _run(tmp_path, "docx", ["x"], "../../etc/passwd").outcome == Outcome.FAIL


def test_registered_in_the_schema_gate():
    task = {
        "id": "t",
        "instruction": "i",
        "checkers": [
            {"type": "office_contains", "kind": "docx", "expect": ["a"], "path": "a.docx"}
        ],
    }
    assert not controls.schema_failures(task)
    task["checkers"] = [{"type": "office_contains", "kind": "docx"}]
    assert controls.schema_failures(task)


def test_structural_names_headings_sheets_titles(tmp_path):
    d = docx.Document()
    d.add_heading("Plan", 1)
    d.add_paragraph("Goals")  # text only, not a heading
    d.save(tmp_path / "a.docx")
    spec = {"type": "office_contains", "kind": "docx", "expect": ["Goals"], "path": "a.docx"}
    assert (
        check_office_contains(
            {**spec, "headings": ["Plan"]}, CheckContext(sandbox_root=tmp_path)
        ).outcome
        == Outcome.PASS
    )
    assert (
        check_office_contains(
            {**spec, "headings": ["Goals"]}, CheckContext(sandbox_root=tmp_path)
        ).outcome
        == Outcome.FAIL
    )
    wb = openpyxl.Workbook()
    wb.active.title = "North"
    wb.save(tmp_path / "a.xlsx")
    x = {"type": "office_contains", "kind": "xlsx", "expect": [], "sheets": ["North"]}
    assert check_office_contains(x, CheckContext(sandbox_root=tmp_path)).outcome == Outcome.PASS
    assert (
        check_office_contains(
            {**x, "sheets": ["South"]}, CheckContext(sandbox_root=tmp_path)
        ).outcome
        == Outcome.FAIL
    )
    p = pptx.Presentation()
    p.slides.add_slide(p.slide_layouts[5]).shapes.title.text = "Roadmap"
    p.save(tmp_path / "a.pptx")
    t = {"type": "office_contains", "kind": "pptx", "expect": [], "titles": ["Roadmap"]}
    assert check_office_contains(t, CheckContext(sandbox_root=tmp_path)).outcome == Outcome.PASS
    assert (
        check_office_contains(
            {**t, "titles": ["Other"]}, CheckContext(sandbox_root=tmp_path)
        ).outcome
        == Outcome.FAIL
    )


def test_one_file_must_satisfy_everything(tmp_path):
    for n, text in (("a", "alpha"), ("b", "beta")):
        d = docx.Document()
        d.add_paragraph(text)
        d.save(tmp_path / f"{n}.docx")
    spec = {"type": "office_contains", "kind": "docx", "expect": ["alpha", "beta"]}
    assert check_office_contains(spec, CheckContext(sandbox_root=tmp_path)).outcome == Outcome.FAIL
    assert (
        check_office_contains(
            {**spec, "expect": ["beta"]}, CheckContext(sandbox_root=tmp_path)
        ).outcome
        == Outcome.PASS
    )
