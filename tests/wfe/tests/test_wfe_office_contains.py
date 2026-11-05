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
    corrupt = _run(tmp_path, "xlsx", ["x"], "bad.xlsx")
    assert corrupt.outcome == Outcome.FAIL
    assert "unparseable" in corrupt.notes
    assert _run(tmp_path, "docx", ["x"], "../../etc/passwd").outcome == Outcome.FAIL


def test_a_missing_parser_is_an_instrument_error(tmp_path, monkeypatch):
    (tmp_path / "x.docx").write_bytes(b"PK not really")

    def boom(_path, _kind):
        raise ModuleNotFoundError("No module named 'docx'")

    monkeypatch.setattr("tests.wfe.checkers._office_parts", boom)
    result = _run(tmp_path, "docx", ["x"], "x.docx")
    assert result.outcome == Outcome.HARNESS_ERROR
    assert "docx" in result.notes
    assert "unparseable" not in result.notes
    assert "docx" in result.evidence["parser_error"]


def test_a_parser_value_error_stays_a_model_fail(tmp_path, monkeypatch):
    (tmp_path / "bad.docx").write_bytes(b"not a zip")

    def boom(_path, _kind):
        raise ValueError("bad zip")

    monkeypatch.setattr("tests.wfe.checkers._office_parts", boom)
    result = _run(tmp_path, "docx", ["x"], "bad.docx")
    assert result.outcome == Outcome.FAIL
    assert "unparseable" in result.notes


def test_preflight_names_a_missing_office_parser(monkeypatch):
    import tests.wfe.checkers as checkers

    real = checkers.importlib.import_module

    def fake(name, package=None):
        if name == "docx":
            raise ImportError("No module named 'docx'")
        return real(name, package)

    monkeypatch.setattr(checkers.importlib, "import_module", fake)
    assert checkers.missing_office_parsers() == ["docx"]


def test_campaign_preflight_refuses_a_missing_office_parser(tmp_path, monkeypatch):
    import tests.wfe.checkers as checkers
    from tests.wfe import campaign

    monkeypatch.setattr(checkers, "missing_office_parsers", lambda: ["docx", "pymupdf"])
    with pytest.raises(campaign.GateRefused, match="missing module docx, pymupdf") as exc:
        campaign.gate_execution(tmp_path)
    assert exc.value.code == campaign.EXIT_GATE


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


def test_an_expect_phrase_may_span_one_heading_group(tmp_path):
    """ready_autodaily_20261105 ru-v1-032: heading "Monday" + bullet "Meeting prep" is the
    fact "Monday meeting prep" written across structure. The rule: within ONE section group
    (a heading plus its lines, bullets joined as single spaces) the phrase's normalized
    words must appear in order and adjacent — not scattered (no bag-of-words), not across
    sections."""
    d = docx.Document()
    d.add_heading("Monday", 1)
    d.add_paragraph("Meeting prep", style="List Bullet")
    d.add_heading("Tuesday", 1)
    d.add_paragraph("Coding project, 9:00 AM - 12:00 PM")
    d.save(tmp_path / "w.docx")
    ctx = CheckContext(sandbox_root=tmp_path)
    spec = {"type": "office_contains", "kind": "docx", "path": "w.docx"}
    assert (
        check_office_contains({**spec, "expect": ["Monday meeting prep"]}, ctx).outcome
        == Outcome.PASS
    )
    assert check_office_contains({**spec, "expect": ["9 to 12"]}, ctx).outcome == Outcome.PASS
    assert check_office_contains({**spec, "expect": ["11am"]}, ctx).outcome == Outcome.FAIL
    # words from two different sections never join
    assert (
        check_office_contains({**spec, "expect": ["Monday coding project"]}, ctx).outcome
        == Outcome.FAIL
    )
    # other words between the phrase's words break the span: not bag-of-words
    scattered = docx.Document()
    scattered.add_paragraph("Monday filler meeting prep")
    scattered.save(tmp_path / "s.docx")
    assert (
        check_office_contains(
            {**spec, "path": "s.docx", "expect": ["Monday meeting prep"]}, ctx
        ).outcome
        == Outcome.FAIL
    )
    # a wrong time in the section still fails
    assert (
        check_office_contains({**spec, "expect": ["Tuesday coding project 9 to 5"]}, ctx).outcome
        == Outcome.FAIL
    )


def test_inline_day_labels_match_the_phrase(tmp_path):
    """ready4 ru-v1-032 Nemotron Week_Plan_3f2a985c.docx bullets, exact paragraph text."""
    d = docx.Document()
    d.add_heading("Week Plan", 1)
    for line in (
        "Monday: Meeting prep",
        "Tuesday: Coding project (9\u202fAM\u201312\u202fPM)",
        "Wednesday: Travel admin (leave by 8\u202fAM)",
        "Thursday: Research",
        "Friday: Wrap\u2011up (ends at 1\u202fPM)",
    ):
        d.add_paragraph(line, style="List Bullet")
    d.save(tmp_path / "w.docx")
    ctx = CheckContext(sandbox_root=tmp_path)
    spec = {"type": "office_contains", "kind": "docx", "path": "w.docx"}
    assert (
        check_office_contains(
            {
                **spec,
                "expect": [
                    "Monday meeting prep",
                    "Tuesday coding project",
                    "Wednesday travel admin",
                    "Thursday research",
                    "Friday wrap-up",
                    "9 to 12",
                    "8am",
                    "1pm",
                ],
            },
            ctx,
        ).outcome
        == Outcome.PASS
    )
    assert (
        check_office_contains({**spec, "expect": ["Saturday meeting prep"]}, ctx).outcome
        == Outcome.FAIL
    )
    assert (
        check_office_contains({**spec, "expect": ["Monday coding project"]}, ctx).outcome
        == Outcome.FAIL
    )


def test_qwen_week_plan_bare_clocks_match(tmp_path):
    """realuse_autodaily_upload_20261105 Qwen3.8 ru-v1-032 r0 table cells."""
    d = docx.Document()
    d.add_heading("Week Plan", 1)
    table = d.add_table(rows=6, cols=3)
    for i, row in enumerate(
        (
            ("Day", "Task", "Time"),
            ("Monday", "Meeting prep", "—"),
            ("Tuesday", "Coding project", "9:00 – 12:00 only"),
            ("Wednesday", "Travel admin", "Leave by 8:00"),
            ("Thursday", "Research", "—"),
            ("Friday", "Wrap-up", "Ends at 1:00"),
        )
    ):
        for j, value in enumerate(row):
            table.rows[i].cells[j].text = value
    d.save(tmp_path / "w.docx")
    spec = {"type": "office_contains", "kind": "docx", "path": "w.docx"}
    ctx = CheckContext(sandbox_root=tmp_path)
    assert (
        check_office_contains(
            {
                **spec,
                "expect": [
                    "Monday meeting prep",
                    "Tuesday coding project",
                    "9 to 12",
                    "8am",
                    "1pm",
                ],
                "headings": ["Week Plan"],
            },
            ctx,
        ).outcome
        == Outcome.PASS
    )
    revised = docx.Document()
    revised.add_heading("Week Plan Revised", 1)
    revised.add_paragraph("Tuesday coding project 9:00–12:00, break at 11:00")
    revised.save(tmp_path / "r.docx")
    assert (
        check_office_contains(
            {**spec, "path": "r.docx", "expect": ["11am"], "headings": ["Week Plan Revised"]},
            ctx,
        ).outcome
        == Outcome.PASS
    )
    wrong = docx.Document()
    wrong.add_paragraph("Tuesday coding project 9:30-12:00, leave by 8:00 PM, ends at 1:30")
    wrong.save(tmp_path / "bad.docx")
    assert (
        check_office_contains(
            {**spec, "path": "bad.docx", "expect": ["9 to 12", "8am", "1pm"]}, ctx
        ).outcome
        == Outcome.FAIL
    )


def test_a_time_written_one_way_matches_expect_written_another(tmp_path):
    d = docx.Document()
    d.add_paragraph("Wednesday travel admin, leave by 8:00 AM")
    d.save(tmp_path / "w.docx")
    assert _run(tmp_path, "docx", ["8am"], "w.docx").outcome == Outcome.PASS
    assert _run(tmp_path, "docx", ["9am"], "w.docx").outcome == Outcome.FAIL


def test_section_groups_per_kind(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Float"
    ws.append(["change", 71])
    wb.save(tmp_path / "a.xlsx")
    assert _run(tmp_path, "xlsx", ["Float change"], "a.xlsx").outcome == Outcome.PASS
    assert _run(tmp_path, "xlsx", ["change nowhere"], "a.xlsx").outcome == Outcome.FAIL
    p = pptx.Presentation()
    slide = p.slides.add_slide(p.slide_layouts[5])
    slide.shapes.title.text = "Car Camp"
    p.save(tmp_path / "a.pptx")
    assert _run(tmp_path, "pptx", ["Car Camp"], "a.pptx").outcome == Outcome.PASS
