"""The campaign supervisor: what it stops for, and what it lets run."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "wfe_supervise", REPO / "scripts" / "wfe_supervise.py"
)
supervise = importlib.util.module_from_spec(_spec)
sys.modules["wfe_supervise"] = supervise
_spec.loader.exec_module(supervise)


def _row(
    outcome="PASS",
    tool_calls=1,
    arm="a",
    suite="s",
    tool_surface=True,
    task_id="t-01",
    text="a real answer, long enough to be one",
    notes="",
):
    return {
        "arm": arm,
        "suite": suite,
        "task_id": task_id,
        "outcome": outcome,
        "tool_calls": tool_calls,
        "tool_surface": tool_surface,
        "notes": notes,
        "text": text,
    }


def _rows(*specs):
    return {f"{i}.json": r for i, r in enumerate(specs)}


def test_a_healthy_cell_raises_nothing():
    rows = _rows(*[_row() for _ in range(20)])
    assert supervise.cell_problems(rows) == []


def test_a_near_zero_cell_is_called_an_instrument_suspect():
    rows = _rows(*[_row("FAIL") for _ in range(20)])
    (problem,) = supervise.cell_problems(rows)
    assert "0/20 PASS" in problem and "instrument suspect" in problem


def test_a_cell_is_judged_only_once_it_has_enough_graded_rows():
    rows = _rows(*[_row("FAIL") for _ in range(supervise.MIN_ROWS_FOR_RATE - 1)])
    assert supervise.cell_problems(rows) == []


def test_instrument_failures_are_not_counted_against_the_model():
    """TOOL_ERROR/HARNESS_ERROR/BLOCKED rows leave the cell short of evidence, not failing."""
    rows = _rows(*[_row("HARNESS_ERROR") for _ in range(20)])
    assert supervise.cell_problems(rows) == []


def test_rows_that_called_no_tool_are_a_delivery_problem():
    rows = _rows(*[_row("PASS", tool_calls=0) for _ in range(20)])
    (problem,) = supervise.cell_problems(rows)
    assert "called no tool" in problem and "delivery" in problem


def test_a_toolless_suite_is_not_judged_on_tool_calls():
    rows = _rows(*[_row("PASS", tool_calls=0, tool_surface=False) for _ in range(20)])
    assert supervise.cell_problems(rows) == []


def test_arms_and_suites_are_judged_apart():
    rows = _rows(
        *[_row("FAIL", arm="bad") for _ in range(20)],
        *[_row("PASS", arm="good") for _ in range(20)],
    )
    assert len(supervise.cell_problems(rows)) == 1


def test_a_clean_answer_smells_of_nothing():
    assert supervise.answer_smells(_row()) == []


def test_garbled_tool_names_leave_zero_width_characters_in_the_answer():
    (smell,) = supervise.answer_smells(_row(text="Download: /app/​data/​generated/x"))
    assert "zero-width" in smell


def test_raw_tool_call_markup_in_the_answer_is_a_smell():
    (smell,) = supervise.answer_smells(_row(text="<tool_call>{'name': 'read_pdf'}</tool_call>"))
    assert "raw <tool_call>" in smell


def test_a_download_link_answering_a_read_task_is_link_bleed():
    (smell,) = supervise.answer_smells(
        _row(task_id="doc-read-03", text="Download: /app/data/x.docx")
    )
    assert "link bleed" in smell
    assert (
        supervise.answer_smells(_row(task_id="doc-make-03", text="Download: /app/data/x.docx"))
        == []
    )


def test_a_pass_on_almost_no_answer_is_a_checker_smell():
    (smell,) = supervise.answer_smells(_row(text="ok"))
    assert "check the checker" in smell
    assert supervise.answer_smells(_row("FAIL", text="ok")) == []


def test_a_terse_json_answer_is_what_the_task_asked_for():
    # wfe_documents_20261017h: `{"answer": "Ilse Mott"}` to an "Answer only as JSON" read task
    # voided a clean granite cell at 27%.
    assert supervise.answer_smells(_row(text='{"answer": "Ilse Mott"}')) == []
    assert supervise.answer_smells(_row(text='["x"]'))  # a bare list is still a smell


def test_a_cell_whose_answers_are_spoiled_is_called_void_though_it_passes():
    """The expensive failure: every row PASSes, every exit code is clean, the evidence is not."""
    rows = _rows(*[_row(text=f"Download: /app/​data/{i}") for i in range(20)])
    problems = supervise.cell_problems(rows)
    assert any("evidence is void" in p and "zero-width" in p for p in problems)


def test_a_few_spoiled_rows_do_not_void_a_cell():
    rows = _rows(
        *[_row(text="Download: /app/​data/x") for _ in range(2)],
        *[_row() for _ in range(18)],
    )
    assert supervise.cell_problems(rows) == []


def test_one_answer_repeated_across_tasks_means_a_stuck_seat():
    rows = [_row(task_id=f"t-{i}", text="the same answer every time, verbatim") for i in range(3)]
    (problem,) = supervise.stuck_answers("a", rows)
    assert "3 different tasks" in problem and "stuck" in problem


def test_the_same_task_answered_the_same_way_twice_is_just_a_repeat():
    rows = [_row(task_id="t-1", text="the same answer every time, verbatim") for _ in range(5)]
    assert supervise.stuck_answers("a", rows) == []


def test_short_answers_are_not_counted_as_stuck():
    rows = [_row(task_id=f"t-{i}", text="yes") for i in range(5)]
    assert supervise.stuck_answers("a", rows) == []


def test_the_sample_prints_the_newest_rows_with_their_smells(tmp_path):
    (tmp_path / "rows").mkdir()
    for i in range(4):
        (tmp_path / "rows" / f"r{i}.json").write_text(
            json.dumps(
                {
                    "arm": "a",
                    "suite": "s",
                    "task_id": f"doc-read-0{i}",
                    "outcome": "PASS",
                    "tool_calls": 2,
                    "notes": f"note {i}",
                    "final_text": f"Download: /app/​data/{i}",
                }
            )
        )
    out = supervise.sample(tmp_path, 2)
    assert out.count("PASS") == 2 and "note 3" in out and "note 1" not in out
    assert "zero-width" in out and "link bleed" in out


def test_the_sample_of_an_empty_campaign_says_so(tmp_path):
    (tmp_path / "rows").mkdir()
    assert supervise.sample(tmp_path, 5) == "no rows yet"


def test_only_halts_appended_since_the_last_tick_are_reported(tmp_path):
    log = tmp_path / "arm_exits.log"
    log.write_text("HALT a k1 pass rate 0/4 <= 1/4\n")
    halts, seen = supervise.new_halts(tmp_path, 0)
    assert halts == ["HALT a k1 pass rate 0/4 <= 1/4"] and seen == 1

    halts, seen = supervise.new_halts(tmp_path, seen)
    assert halts == [] and seen == 1

    with log.open("a") as fh:
        fh.write("HALT b k2 0 tool calls on all 4 rows\n")
    halts, seen = supervise.new_halts(tmp_path, seen)
    assert halts == ["HALT b k2 0 tool calls on all 4 rows"] and seen == 2


def test_a_missing_exit_log_is_not_a_problem(tmp_path):
    assert supervise.new_halts(tmp_path, 0) == ([], 0)


def test_a_row_being_written_right_now_is_skipped_and_read_next_tick(tmp_path):
    (tmp_path / "rows").mkdir()
    half = tmp_path / "rows" / "half.json"
    half.write_text('{"arm": "a", "suite"')
    cache: dict = {}
    assert supervise.load_rows(tmp_path, cache) == {}

    half.write_text(json.dumps({"arm": "a", "suite": "s", "outcome": "PASS", "tool_calls": 2}))
    assert supervise.load_rows(tmp_path, cache)["half.json"]["outcome"] == "PASS"


def test_a_row_already_read_is_not_read_again(tmp_path):
    (tmp_path / "rows").mkdir()
    f = tmp_path / "rows" / "r.json"
    f.write_text(json.dumps({"arm": "a", "suite": "s", "outcome": "PASS", "tool_calls": 1}))
    cache = supervise.load_rows(tmp_path, {})
    f.write_text(json.dumps({"arm": "a", "suite": "s", "outcome": "FAIL", "tool_calls": 1}))
    assert supervise.load_rows(tmp_path, cache)["r.json"]["outcome"] == "PASS"


def test_a_halt_stops_the_tick_even_while_health_says_ok(tmp_path, monkeypatch):
    (tmp_path / "rows").mkdir()
    (tmp_path / "arm_exits.log").write_text("HALT a doc-read pass rate 0/4 <= 1/4\n")
    monkeypatch.setattr(
        supervise, "health", lambda _d: {"verdict": "OK", "problems": [], "done": 4, "total": 60}
    )
    verdict, problems, digest = supervise.tick(tmp_path, {}, {})
    assert verdict == "ATTENTION"
    assert problems == ["HALT HALT a doc-read pass rate 0/4 <= 1/4"]
    assert "4/60 rows" in digest and "!1" in digest


def test_a_clean_tick_reports_ok_and_a_finished_one_reports_done(tmp_path, monkeypatch):
    (tmp_path / "rows").mkdir()
    base = {"problems": [], "done": 60, "total": 60}
    monkeypatch.setattr(supervise, "health", lambda _d: {"verdict": "OK", **base})
    assert supervise.tick(tmp_path, {}, {})[0] == "OK"
    monkeypatch.setattr(supervise, "health", lambda _d: {"verdict": "DONE", **base})
    assert supervise.tick(tmp_path, {}, {})[0] == "DONE"


def test_health_problems_reach_the_tick(tmp_path, monkeypatch):
    (tmp_path / "rows").mkdir()
    monkeypatch.setattr(
        supervise,
        "health",
        lambda _d: {
            "verdict": "STALLED",
            "problems": ["no row completed in 1h00m"],
            "done": 4,
            "total": 60,
        },
    )
    verdict, problems, _ = supervise.tick(tmp_path, {}, {})
    assert verdict == "ATTENTION" and problems == ["no row completed in 1h00m"]
