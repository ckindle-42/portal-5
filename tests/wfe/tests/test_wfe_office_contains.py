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


def test_twenty_four_hour_end_time_matches_1pm(tmp_path):
    """realuse_autodaily_prod_20261105 ru-v1-032 r0 docx: Ends at 13:00 failed expect 1pm."""
    d = docx.Document()
    d.add_paragraph("Friday wrap-up. Ends at 13:00")
    d.save(tmp_path / "w.docx")
    assert _run(tmp_path, "docx", ["1pm"], "w.docx").outcome == Outcome.PASS
    late = docx.Document()
    late.add_paragraph("Ends at 13:30")
    late.save(tmp_path / "late.docx")
    assert _run(tmp_path, "docx", ["1pm"], "late.docx").outcome == Outcome.FAIL
    three = docx.Document()
    three.add_paragraph("Ends at 3:00")
    three.save(tmp_path / "three.docx")
    assert _run(tmp_path, "docx", ["1pm"], "three.docx").outcome == Outcome.FAIL
    for written, expect in (
        ("08:00", "8am"),
        ("11:00", "11am"),
        ("13:00h", "1pm"),
        ("1300", "1pm"),
    ):
        doc = docx.Document()
        doc.add_paragraph(f"Ends at {written}")
        doc.save(tmp_path / "t.docx")
        assert _run(tmp_path, "docx", [expect], "t.docx").outcome == Outcome.PASS
