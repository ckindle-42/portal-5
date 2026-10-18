"""Build tests/wfe/suites/reasoning_math_production.jsonl, the reasoning/math family's
production suite (WFE P3 triage §2; master plan S8/O5).

One suite, two workspaces: auto-reasoning (DeepSeek-R1-0528-Qwen3-8B, ctx 64k, think on)
and auto-math (phi4-mini-reasoning, ctx 24k). Both offer zero tools, so every task is
`no_tools` — the harness runs them without a tool surface (tests/wfe/eval_mode.py:107)
and the no-tools exception to the trace checker applies. The family's second checker is
therefore not `tool_grounded` but `answer_after_reasoning` (tests/wfe/checkers.py): the
answer must appear after the reasoning, never only inside a <think> block.

Every problem is generated from fictional seeded values, so a model cannot pass from
training, and the gold is computed here — never written by hand — then asserted unique
across the suite. Three kinds, 12 tasks, 4 in the screen tier:

- arithmetic (4)      a multi-step exact computation on seeded numbers (percent chain,
                      fill rate, clock, modular power);
- combinatorics (4)   an exact count (handshakes, committee, podium, grid routes);
- logic-grid (4)      a four-runner finishing order pinned by generated clues; the
                      generator brute-forces all 24 permutations and keeps a puzzle
                      only when the clues admit exactly one solution.

The instruction never states the gold (a test enforces it), every enumerated answer
value is defined in its instruction ("the number only", "the name only", "HH:MM"), and
there are no tool arguments to name — the suite needs nothing a tool schema expresses.
The hard output cap is the workspaces' own predict_limit (16384 / 8192), applied by the
harness (tests/wfe/runner.py:1278); every chain these tasks need fits far inside it.

    uv run python tests/wfe/suites/build_reasoning_math_production.py
"""

from __future__ import annotations

import itertools
import json
import math
import random
import re
from collections.abc import Callable
from pathlib import Path

from tests.wfe.suites.build_research_production import Fact

OUT = Path(__file__).with_name("reasoning_math_production.jsonl")
FORMAT = 'Answer only as JSON {"answer": ...}.'
COUNTS = {"arithmetic": 4, "combinatorics": 4, "logic-grid": 4}
SCREEN = {"arithmetic": 1, "combinatorics": 1, "logic-grid": 2}
LANE = "reasoning"
SEEDS = {"arithmetic": 8800, "combinatorics": 8900, "logic-grid": 9100}
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth"}
#: The position each logic-grid task asks about, so the four gold names differ.
ASKED_POSITION = (2, 3, 1, 4)

DECIDING_FACTS: dict[str, list[Fact]] = {}

_LOGIC_NAMES = ["Vellisa", "Ondrey", "Sarait", "Mireau", "Kestrel", "Tobren"]


def _pattern(gold: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(gold)}"?(?![\w.-])'


def _answer(gold: str) -> str:
    return json.dumps({"answer": gold})


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


# ---------------------------------------------------------------- logic-grid


Clue = tuple[str, Callable[[dict[str, int]], bool]]


def _immediately_before(a: str, b: str) -> Clue:
    return (f"{a} finished immediately before {b}.", lambda p, a=a, b=b: p[a] + 1 == p[b])


def _somewhere_ahead(a: str, b: str) -> Clue:
    return (f"{a} finished somewhere ahead of {b}.", lambda p, a=a, b=b: p[a] < p[b])


def _not_position(a: str, p: int) -> Clue:
    return (f"{a} did not finish {ORDINALS[p]}.", lambda q, a=a, p=p: q[a] != p)


def _solutions(names: list[str], clues: list[Clue]) -> list[dict[str, int]]:
    """Every finishing order that satisfies every clue (4! = 24 candidates)."""
    out = []
    for perm in itertools.permutations(names):
        pos = {n: i + 1 for i, n in enumerate(perm)}
        if all(keep(pos) for _, keep in clues):
            out.append(pos)
    return out


def logic_case(n: int) -> tuple[list[str], list[str], int, str]:
    """(names, clue sentences, asked position, gold name) with a UNIQUE solution."""
    r = random.Random(SEEDS["logic-grid"] + n)
    names = sorted(r.sample(_LOGIC_NAMES, 4))
    order = r.sample(names, 4)
    truth = {name: i + 1 for i, name in enumerate(order)}
    pool: list[Clue] = []
    for a, b in itertools.permutations(names, 2):
        pool.append(_immediately_before(a, b))
        pool.append(_somewhere_ahead(a, b))
    for a in names:
        for p in (1, 2, 3, 4):
            if truth[a] != p:
                pool.append(_not_position(a, p))
    # Only clues that are TRUE of the generated order may be told; a false clue
    # would exclude the very order the gold was computed from.
    pool = [c for c in pool if c[1](truth)]
    r.shuffle(pool)
    clues: list[Clue] = []
    best: list[dict[str, int]] = _solutions(names, clues)
    for clue in pool:
        if len(best) == 1:
            break
        smaller = _solutions(names, clues + [clue])
        if len(smaller) < len(best):
            clues.append(clue)
            best = smaller
    if len(best) != 1 or best[0] != truth:
        raise RuntimeError(f"logic-grid-{n:02d}: clues admit {len(best)} solutions")
    asked = ASKED_POSITION[n % len(ASKED_POSITION)]
    gold = next(name for name, p in truth.items() if p == asked)
    return names, [text for text, _ in clues], asked, gold


# ---------------------------------------------------------------- cases


def arithmetic_case(n: int) -> tuple[str, str, str, str]:
    """(question, format phrase, gold, kind detail) for arithmetic task n."""
    r = random.Random(SEEDS["arithmetic"] + n)
    if n == 0:  # a percent chain, both steps applied to the running price
        while True:
            base = 20 * r.randint(15, 60)
            up = r.choice([10, 15, 20, 25])
            down = r.choice([10, 20, 25, 40])
            final = base * (100 + up) * (100 - down) / 10000
            if final == int(final) and final != base and up != down:
                break
        question = (
            f"A coat costs {base} credits. The price goes up by {up} percent, then the new "
            f"price goes down by {down} percent. What is the final price in credits?"
        )
        return question, "the number only", str(int(final)), "percent chain"
    if n == 1:  # two opposing flows; the NET rate fills the tank
        fast, slow, mins = r.randint(31, 80), r.randint(4, 30), r.randint(45, 240)
        while fast - slow < 3:
            slow = r.randint(4, 30)
        question = (
            f"An empty tank holds {(fast - slow) * mins} litres. A pipe adds {fast} litres "
            f"a minute while a drain removes {slow} litres a minute, both running together. "
            f"How many minutes until the tank is full?"
        )
        return question, "the number only", str(mins), "fill rate"
    if n == 2:  # clock arithmetic far past one wrap
        h, m, add = r.randint(0, 23), r.randint(0, 59), r.randint(1500, 6000)
        total = (h * 60 + m + add) % (24 * 60)
        question = (
            f"A 24-hour clock shows {h:02d}:{m:02d}. What time does it show exactly "
            f"{add} minutes later? Write the time as HH:MM."
        )
        return (
            question,
            "the time as HH:MM in 24-hour form",
            f"{total // 60:02d}:{total % 60:02d}",
            "clock",
        )
    a, b, m = r.randint(3, 9), r.randint(7, 14), r.randint(53, 97)
    question = f"What is the remainder when {a} raised to the power {b} is divided by {m}?"
    return question, "the number only", str(pow(a, b, m)), "modular power"


def combinatorics_case(n: int) -> tuple[str, str, str, str]:
    """(question, format phrase, gold, kind detail) for combinatorics task n."""
    r = random.Random(SEEDS["combinatorics"] + n)
    if n == 0:
        people = r.randint(21, 48)
        question = (
            f"At a gathering of {people} people, every pair of people shakes hands exactly "
            f"once. How many handshakes take place?"
        )
        return question, "the number only", str(people * (people - 1) // 2), "handshakes"
    if n == 1:
        members, size = r.randint(9, 14), r.randint(3, 5)
        question = (
            f"A club with {members} members is choosing a committee of {size} members. "
            f"How many different committees are possible?"
        )
        return question, "the number only", str(math.comb(members, size)), "committee"
    if n == 2:
        entrants = r.randint(9, 15)
        question = (
            f"A race has {entrants} entrants and awards gold, silver and bronze. How many "
            f"different first-second-third orderings are possible?"
        )
        return (
            question,
            "the number only",
            str(entrants * (entrants - 1) * (entrants - 2)),
            "podium",
        )
    w, d = r.randint(3, 7), r.randint(3, 7)
    question = (
        f"A city grid is {w} blocks wide and {d} blocks deep. Walking only east or south, "
        f"how many distinct routes lead from the north-west corner to the south-east corner?"
    )
    return question, "the number only", str(math.comb(w + d, w)), "grid routes"


# ---------------------------------------------------------------- assembly


def _givens(tid: str, facts: list[tuple[str, str]]) -> list[Fact]:
    """One deciding fact per stated given; `tool` is empty because the instruction
    itself is the only source a no_tools task has (the attainability check reads
    them from the instruction, not from a tool output)."""
    out = [Fact("", {}, re.escape(given), why) for given, why in facts]
    DECIDING_FACTS[tid] = out
    return out


def _task(tid: str, kind: str, n: int, ins: str, gold: str, givens: list[tuple[str, str]]) -> dict:
    checkers = [
        {"type": "answer_contains", "patterns": [_pattern(gold)]},
        {"type": "answer_after_reasoning", "patterns": [_pattern(gold)]},
    ]
    t = {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": False,
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "requires_tools": [],
        "checkers": checkers,
        "controls": {
            "pass": [{"answer": _answer(gold), "tool_calls": []}],
            # A no_tools task has no trace to withhold, so the failing controls are a
            # wrong answer — and the right answer buried inside the reasoning block,
            # which answer_after_reasoning exists to fail.
            "fail": [
                {"answer": _answer("wrong-value"), "tool_calls": []},
                {"answer": f"<think>{_answer(gold)}</think>", "tool_calls": []},
            ],
        },
        "no_tools": True,
    }
    _givens(tid, givens)
    return t


def build_arithmetic(n: int) -> dict:
    question, fmt, gold, detail = arithmetic_case(n)
    tid = f"rm-arithmetic-{n:02d}"
    numbers = re.findall(r"\d+", question)
    givens = [(v, f"given {i + 1} of the {detail}") for i, v in enumerate(numbers)]
    ins = _phrase(
        n % 3 == 0,
        f"{question} Give {fmt}. {FORMAT}",
        f"Work this out: {question} Give {fmt}. {FORMAT}",
    )
    return _task(tid, "arithmetic", n, ins, gold, givens)


def build_combinatorics(n: int) -> dict:
    question, fmt, gold, detail = combinatorics_case(n)
    tid = f"rm-combinatorics-{n:02d}"
    numbers = re.findall(r"\d+", question)
    givens = [(v, f"given {i + 1} of the {detail} count") for i, v in enumerate(numbers)]
    ins = _phrase(
        n % 3 == 0,
        f"{question} Give {fmt}. {FORMAT}",
        f"Count it out: {question} Give {fmt}. {FORMAT}",
    )
    return _task(tid, "combinatorics", n, ins, gold, givens)


def build_logic(n: int) -> dict:
    names, clues, asked, gold = logic_case(n)
    tid = f"rm-logic-grid-{n:02d}"
    roster = f"{', '.join(names[:-1])} and {names[-1]}"
    body = "\n".join(f"- {c}" for c in clues)
    ins = _phrase(
        n % 3 == 0,
        (
            f"Four runners — {roster} — finished a race with no ties, in positions "
            f"1 (first) to 4 (fourth). The clues are:\n{body}\n"
            f"Who finished {ORDINALS[asked]}? Give the name only. {FORMAT}"
        ),
        (
            f"Determine the finishing order of four runners — {roster} — from the clues, "
            f"positions 1 (first) to 4 (fourth), no ties:\n{body}\n"
            f"Then state who finished {ORDINALS[asked]}. Give the name only. {FORMAT}"
        ),
    )
    givens = [(c, f"clue: {c}") for c in clues]
    givens.append((roster, "the four runners named"))
    return _task(tid, "logic-grid", n, ins, gold, givens)


BUILDERS = {
    "arithmetic": build_arithmetic,
    "combinatorics": build_combinatorics,
    "logic-grid": build_logic,
}


def _leaks(t: dict) -> str | None:
    """How the instruction states the gold, if it does. A computed value (a number or
    a clock time) must not appear at all; a logic-grid runner's NAME must appear (the
    roster names all four), so the leak to forbid there is the direct binding — the
    asked position stated with the gold's name in one sentence."""
    gold = json.loads(t["controls"]["pass"][0]["answer"])["answer"]
    if re.fullmatch(r"[\d:]+", gold):
        return (
            f"the gold {gold!r} is stated in the instruction" if gold in t["instruction"] else None
        )
    asked = ASKED_POSITION[int(t["id"].rsplit("-", 1)[1]) % len(ASKED_POSITION)]
    binding = f"{gold} finished {ORDINALS[asked]}"
    return f"the binding {binding!r} is stated" if binding in t["instruction"] else None


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    tasks = [BUILDERS[k](n) for k, count in COUNTS.items() for n in range(count)]
    golds = [json.loads(t["controls"]["pass"][0]["answer"])["answer"] for t in tasks]
    if len(golds) != len(set(golds)):
        dupes = sorted({g for g in golds if golds.count(g) > 1})
        raise RuntimeError(f"duplicate gold answers across the suite: {dupes}")
    for t in tasks:
        if leak := _leaks(t):
            raise RuntimeError(f"{t['id']}: {leak}")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
