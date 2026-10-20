"""Build tests/wfe/suites/data_production.jsonl, auto-research::data's production suite.

Three small, deterministic datasets (sales, inventory, tickets) are seeded into each
row's run directory; every question has one gold answer computed here and cross-checked
by DuckDB in the tests. Money is integer, so totals are exact; averages are asked for
rounded to two decimals. Every task is graded on its answer (a number or a quoted string
both pass) and on where it came from: a successful run_sql or profile_table call whose
output shows the value (tool_grounded).

    uv run python tests/wfe/suites/build_data_production.py
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

OUT = Path(__file__).with_name("data_production.jsonl")
_TIES: dict[float, float] = {}  # half-up gold -> the half-even reading of the same exact tie
TOOLS = ["run_sql", "profile_table"]
REGIONS, PRODUCTS = ["east", "west", "north", "south"], ["anvil", "bracket", "cog", "dial", "ember"]
TEAMS = ["network", "systems", "grc"]


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows([header, *rows])
    return buf.getvalue()


def datasets() -> dict[str, tuple[list[str], list[list]]]:
    sales = [
        [REGIONS[i % 4], PRODUCTS[(i * 3) % 5], 1 + i % 6, 3 + (i * 7) % 11, 20 + (i * 13) % 37]
        for i in range(40)
    ]
    inventory = [
        [p, w, (i * 17 + 5 * j) % 60, 15 + (i * 3 + j) % 10]
        for i, p in enumerate(PRODUCTS)
        for j, w in enumerate(["dock", "yard"])
    ]
    tickets = [
        [
            1000 + i,
            ["low", "medium", "high"][i % 3],
            TEAMS[(i * 2) % 3],
            1 + i,
            "" if i % 7 == 3 else 1 + i + (i * 5) % 9,
        ]
        for i in range(30)
    ]
    return {
        "sales": (["region", "product", "month", "units", "unit_price"], sales),
        "inventory": (["product", "warehouse", "on_hand", "reorder_point"], inventory),
        "tickets": (["ticket_id", "priority", "team", "opened_day", "closed_day"], tickets),
    }


def avg2(total: int, n: int) -> float:
    """An average rounded to 2 decimals the way SQL's ROUND does (half up), computed
    exactly. At an exact tie (37.625) a model may round either way, and both pass."""
    from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

    exact = Decimal(total) / Decimal(n)
    up = float(exact.quantize(Decimal("0.01"), ROUND_HALF_UP))
    even = float(exact.quantize(Decimal("0.01"), ROUND_HALF_EVEN))
    if up != even:
        _TIES[up] = even
    return up


def questions(d: dict) -> list[tuple[str, str, object]]:
    """(table, question, gold) — gold is an int, a 2-decimal float, or a string."""
    s, inv, t = d["sales"][1], d["inventory"][1], d["tickets"][1]

    def rev(rows: list[list]) -> int:
        return sum(r[3] * r[4] for r in rows)

    def by(rows: list[list], k: int, f) -> dict:
        return {key: f([r for r in rows if r[k] == key]) for key in {r[k] for r in rows}}

    region_rev, product_rev = by(s, 0, rev), by(s, 1, rev)
    month_units = by(s, 2, lambda rs: sum(r[3] for r in rs))
    closed = [r for r in t if r[4] != ""]
    team_open = by(t, 2, lambda rs: sum(r[4] == "" for r in rs))
    low = [r for r in inv if r[2] < r[3]]
    q = [
        (
            "sales",
            "What is the total revenue (units times unit_price, summed over all rows)?",
            rev(s),
        ),
        ("sales", "How many rows does the table have?", len(s)),
        (
            "sales",
            "Which region has the highest total revenue?",
            max(region_rev, key=region_rev.get),
        ),
        ("sales", "What is the total revenue of the west region?", region_rev["west"]),
        (
            "sales",
            "Which product has the highest total revenue?",
            max(product_rev, key=product_rev.get),
        ),
        ("sales", "What is the total revenue of the product cog?", product_rev["cog"]),
        (
            "sales",
            "Which month (1 to 6) has the most units sold?",
            max(month_units, key=month_units.get),
        ),
        ("sales", "How many units were sold in total?", sum(r[3] for r in s)),
        (
            "sales",
            "What is the average unit_price, rounded to 2 decimals?",
            avg2(sum(r[4] for r in s), len(s)),
        ),
        (
            "sales",
            "What is the largest single-row revenue (units times unit_price)?",
            max(r[3] * r[4] for r in s),
        ),
        ("sales", "How many rows have more than 10 units?", sum(r[3] > 10 for r in s)),
        (
            "sales",
            "How many distinct products appear in month 3?",
            len({r[1] for r in s if r[2] == 3}),
        ),
        (
            "inventory",
            "What is the total on_hand quantity across all rows?",
            sum(r[2] for r in inv),
        ),
        ("inventory", "How many rows have on_hand below their reorder_point?", len(low)),
        (
            "inventory",
            "Which product has the lowest combined on_hand across both warehouses?",
            min(PRODUCTS, key=lambda p: sum(r[2] for r in inv if r[0] == p)),
        ),
        (
            "inventory",
            "What is the total on_hand in the yard warehouse?",
            sum(r[2] for r in inv if r[1] == "yard"),
        ),
        (
            "inventory",
            "What is the largest shortfall (reorder_point minus on_hand) of any row?",
            max(r[3] - r[2] for r in inv),
        ),
        (
            "inventory",
            "What is the average reorder_point, rounded to 2 decimals?",
            avg2(sum(r[3] for r in inv), len(inv)),
        ),
        (
            "inventory",
            "How many distinct products have at least one row below its reorder_point?",
            len({r[0] for r in low}),
        ),
        (
            "inventory",
            "What is the on_hand quantity of bracket in the dock warehouse?",
            next(r[2] for r in inv if r[0] == "bracket" and r[1] == "dock"),
        ),
        (
            "inventory",
            "Which warehouse holds more on_hand in total?",
            max(["dock", "yard"], key=lambda w: sum(r[2] for r in inv if r[1] == w)),
        ),
        (
            "inventory",
            "What is the total on_hand of the product ember?",
            sum(r[2] for r in inv if r[0] == "ember"),
        ),
        ("inventory", "How many rows have on_hand of zero?", sum(r[2] == 0 for r in inv)),
        ("inventory", "What is the maximum on_hand of any row?", max(r[2] for r in inv)),
        (
            "tickets",
            "How many tickets are still open (closed_day empty)?",
            sum(r[4] == "" for r in t),
        ),
        ("tickets", "How many tickets have priority high?", sum(r[1] == "high" for r in t)),
        ("tickets", "Which team has the most open tickets?", max(team_open, key=team_open.get)),
        (
            "tickets",
            "What is the average resolution time in days (closed_day minus opened_day) over closed tickets, rounded to 2 decimals?",
            avg2(sum(r[4] - r[3] for r in closed), len(closed)),
        ),
        (
            "tickets",
            "What is the longest resolution time in days of any closed ticket?",
            max(r[4] - r[3] for r in closed),
        ),
        ("tickets", "How many tickets does the grc team have?", sum(r[2] == "grc" for r in t)),
        (
            "tickets",
            "How many closed tickets took more than 5 days to resolve?",
            sum(r[4] - r[3] > 5 for r in closed),
        ),
        (
            "tickets",
            "What is the ticket_id of the open ticket with the lowest opened_day?",
            min((r for r in t if r[4] == ""), key=lambda r: r[3])[0],
        ),
        (
            "tickets",
            "How many medium-priority tickets are closed?",
            sum(r[1] == "medium" and r[4] != "" for r in t),
        ),
        ("tickets", "What is the highest closed_day of any ticket?", max(r[4] for r in closed)),
        (
            "tickets",
            "How many distinct teams have at least one open ticket?",
            sum(v > 0 for v in team_open.values()),
        ),
        (
            "tickets",
            "What is the average opened_day of high-priority tickets, rounded to 2 decimals?",
            avg2(sum(r[3] for r in t if r[1] == "high"), sum(r[1] == "high" for r in t)),
        ),
    ]
    return q


def _patterns(gold: object) -> tuple[str, str]:
    """(answer pattern, tool-output evidence pattern) for a gold value."""
    if isinstance(gold, str):
        return rf'"answer"\s*:\s*"{re.escape(gold)}"', rf"\b{re.escape(gold)}\b"
    if isinstance(gold, float):
        whole, frac = f"{gold:.2f}".split(".")
        fr = frac.rstrip("0")  # 18.50 is written 18.5; trailing zeros are optional
        num = (
            rf"{whole}\.{fr}\d*"
            if len(fr) == 2
            else rf"{whole}\.{fr}0*(?!\d)"
            if fr
            else rf"{whole}(\.0+)?(?![\d.])"
        )
        if gold in _TIES:  # an exact tie: half-up (SQL) or half-even (Python) both pass
            other = f"{_TIES[gold]:.2f}".replace(".", r"\.")
            num = rf"(?:{num}|{other}0*(?!\d))"
        return rf'"answer"\s*:\s*"?{num}"?', rf"\b{whole}\.{frac[0]}"
    return rf'"answer"\s*:\s*"?{gold}(\.0+)?"?(?![\d.])', rf"(?<![\d.]){gold}(\.0+)?(?![\d])"


def _wrong(gold: object) -> object:
    if isinstance(gold, str):
        return "none"
    return round(gold + 1.5, 2) if isinstance(gold, float) else gold + 7


def build() -> list[dict]:
    d = datasets()
    tasks = []
    for i, (table, question, gold) in enumerate(questions(d)):
        header, rows = d[table]
        answer, evidence = _patterns(gold)
        good = json.dumps({"answer": gold})
        trace = [
            {
                "name": "run_sql",
                "args": {"sql": "..."},
                "output": json.dumps([[gold]]),
                "error": None,
            }
        ]
        tasks.append(
            {
                "id": f"data-prod-{table}-{i:02d}",
                "kind": f"data-{table}",
                "lane": "data",
                "agentic": True,
                "screen": i % 12 < 4,  # four per dataset in the screen tier
                "instruction": (
                    f"Attach {table}.csv as table {table} using the data tools, then answer: {question} "
                    f'Answer only as JSON {{"answer": ...}}.'
                ),
                "requires_tools": ["attach_source", "run_sql"],
                "seed": {f"{table}.csv": _csv(header, rows)},
                "checkers": [
                    {"type": "answer_contains", "patterns": [answer]},
                    {"type": "tool_grounded", "tools": TOOLS, "evidence": [evidence]},
                ],
                "controls": {
                    "pass": [{"answer": good, "tool_calls": trace}],
                    "fail": [
                        good,
                        {"answer": json.dumps({"answer": _wrong(gold)}), "tool_calls": trace},
                    ],
                },
            }
        )
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
