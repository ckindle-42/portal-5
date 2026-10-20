"""auto-research::data production suite: sound under the controls gate, and its gold answers
reproduced independently by DuckDB (the engine behind the data MCP) from the very CSVs
each row is seeded with."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.wfe import controls

SUITE = Path(__file__).resolve().parents[1] / "suites" / "data_production.jsonl"
TASKS = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}

#: question fragment -> SQL that must reproduce the task's gold (DuckDB, over the seed).
SQL = {
    "total revenue (units times unit_price, summed": "SELECT sum(units * unit_price) FROM sales",
    "Which region has the highest total revenue": "SELECT region FROM sales GROUP BY region ORDER BY sum(units * unit_price) DESC LIMIT 1",
    "average unit_price, rounded": "SELECT round(avg(unit_price), 2) FROM sales",
    "below their reorder_point?": "SELECT count(*) FROM inventory WHERE on_hand < reorder_point",
    "average reorder_point": "SELECT round(avg(reorder_point), 2) FROM inventory",
    "still open (closed_day empty)": "SELECT count(*) FROM tickets WHERE closed_day IS NULL",
    "average resolution time": "SELECT round(avg(closed_day - opened_day), 2) FROM tickets WHERE closed_day IS NOT NULL",
    "Which team has the most open tickets": "SELECT team FROM tickets WHERE closed_day IS NULL GROUP BY team ORDER BY count(*) DESC LIMIT 1",
}


def _gold(task: dict):
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suite_is_sound():
    assert len(TASKS) >= 34
    assert sum(t["screen"] for t in TASKS.values()) >= 10
    assert controls.check_suite(SUITE) == []


@pytest.mark.parametrize("fragment", sorted(SQL))
def test_duckdb_reproduces_the_gold_from_the_seed(fragment, tmp_path):
    duckdb = pytest.importorskip("duckdb")
    (task,) = [t for t in TASKS.values() if fragment in t["instruction"]]
    name, body = next(iter(task["seed"].items()))
    (tmp_path / name).write_text(body)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE {name[:-4]} AS SELECT * FROM read_csv_auto('{tmp_path / name}')")
    got = con.execute(SQL[fragment]).fetchone()[0]
    gold = _gold(task)
    assert (round(float(got), 2) == gold) if isinstance(gold, float) else (got == gold), (got, gold)
    # what run_sql would show must satisfy the task's grounding evidence
    assert re.search(task["checkers"][1]["evidence"][0], json.dumps([[got]], default=str))


def test_an_answer_written_as_a_number_or_a_string_both_pass():
    from tests.wfe.checkers import CheckContext, apply_checkers
    from tests.wfe.schema import Outcome

    task = next(t for t in TASKS.values() if isinstance(_gold(t), int))
    trace = task["controls"]["pass"][0]["tool_calls"]
    for answer in ({"answer": _gold(task)}, {"answer": str(_gold(task))}):
        ctx = CheckContext(final_text=json.dumps(answer), task=task, tool_calls=trace)
        assert apply_checkers(task, ctx).outcome == Outcome.PASS, answer
