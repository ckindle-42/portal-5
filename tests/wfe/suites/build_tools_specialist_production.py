"""Build tests/wfe/suites/tools_specialist_production.jsonl, the tools-specialist lane's
production suite (WFE P3 triage §5; master plan S8/O5).

tools-specialist serves granite4.1:8b at ctx 8192 with exactly three tools —
execute_python, remember, recall — so the suite measures the tool loop itself. Every
value is computed here from seeded fictional numbers or generated fictional tokens,
never written by hand. Three kinds, 36 tasks, 12 in the screen tier (four per kind on screen):

- compute (12)        an exact computation posed in the instruction; the reference
                     execute_python code prints the gold on stdout;
- store-recall (12)   a fictional fact the model must store with remember and confirm
                     with recall — the answer token is GIVEN (the store path is the
                     test, per the triage's task form), the grounding is the read-back;
- chain (12)          compute with Python, store the result, recall it back, answer:
                     grounded twice, on the computation's stdout and the recall's text.

Every task is graded on its answer (answer_contains) AND on where it came from
(tool_grounded on the row's own exec_audit trace). The gold values live in the tool
outputs BY DESIGN — that is the grounding — so, unlike the research absent-kind, no
checker forbids them in tool output; the no-leak rule enforced here is that compute
and chain golds are derived values never stated in the instruction (tested), while the
store-recall payload is stated because storing it IS the task.

Tool output shapes are declared from the MCP sources — execute_python returns
{success, stdout, stderr, exit_code, timed_out}
(portal/modules/coding/tools/code_sandbox_mcp.py:533-556), remember returns
{id, stored, category, graph_updated} (portal/platform/memory/graph_memory.py:389-420),
recall returns {query, memories:[{id, text, category, tags, similarity}]}
(graph_memory.py:423-468) — and backlogged in coding_task/WFE_LIVE_BACKLOG.md for
live verification, along with the P-4 window (8k, the tightest seat in the fleet).

    uv run python tests/wfe/suites/build_tools_specialist_production.py
"""

from __future__ import annotations

import json
import math
import random
import re
from fractions import Fraction
from pathlib import Path

from tests.wfe.suites._publish import publish_text
from tests.wfe.suites.build_research_production import Fact

OUT = Path(__file__).with_name("tools_specialist_production.jsonl")
COUNTS = {"compute": 12, "store-recall": 12, "chain": 12}
SCREEN = {"compute": 4, "store-recall": 4, "chain": 4}
LANE = "tools"
SEEDS = {"compute": 9500, "store-recall": 9600, "chain": 9700}
FORMAT = 'Answer only as JSON {"answer": "<value>"}.'

DECIDING_FACTS: dict[str, list[Fact]] = {}

#: Store tokens already used by a built task (reset by build()); the token drawer
#: re-seeds on a collision so the suite's golds stay unique.
_USED_GOLDS: set[str] = set()


def _pattern(gold: str) -> str:
    return rf"(?<![\w.]){re.escape(gold)}(?![\w])"


def _answer_pattern(gold: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(gold)}"?(?![\w.-])'


def _stdout_evidence(gold: str) -> str:
    """The gold appears in stdout as a whole value. The instruction never asks the model
    to print only the result, so a seat that printed ``{'answer': 572}`` or the raw float
    next to the rounded value computed it with the tool just the same (wfe_tools_20261018b
    graded two such rows ungrounded). Bounded on both sides: an escaped newline/tab or a
    non-word character before, no word character or decimal part after, so ``5720``,
    ``1572`` and ``3714.5`` do not ground 572 or 3714."""
    return (
        r'"stdout"\s*:\s*"(?:[^"\\]|\\.)*?(?:(?<=\\n)|(?<=\\t)|(?<![\w.]))'
        + re.escape(gold)
        + r"(?![\w]|\.\d)"
    )


def _text_evidence(gold: str) -> str:
    return rf'"text"\s*:\s*"[^"]*{re.escape(gold)}'


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


# ---------------------------------------------------------------- compute


def compute_case(n: int) -> dict:
    """(instruction body, reference python, gold, near-miss wrong, fmt) for task n."""
    r = random.Random(SEEDS["compute"] + n)
    n = n % 4
    if n == 0:
        rows = [(r.randint(12, 40), r.randint(3, 19)) for _ in range(3)]
        gold = sum(u * p for u, p in rows)
        wrong = sum(u for u, _ in rows)
        body = (
            f"Three orders came in: {rows[0][0]} units at {rows[0][1]} credits, "
            f"{rows[1][0]} units at {rows[1][1]} credits, and {rows[2][0]} units at "
            f"{rows[2][1]} credits. What is the total revenue in credits?"
        )
        code = f"print({rows[0][0]}*{rows[0][1]} + {rows[1][0]}*{rows[1][1]} + {rows[2][0]}*{rows[2][1]})"
        return {
            "body": body,
            "code": code,
            "gold": str(gold),
            "wrong": str(wrong),
            "fmt": "the number of credits only",
        }
    if n == 1:
        secs = r.randint(100000, 999999)
        h, m, s = secs // 3600, secs % 3600 // 60, secs % 60
        gold = f"{h:02d}:{m:02d}:{s:02d}"
        wrong = f"{h:02d}:{s:02d}:{m:02d}"  # minutes and seconds swapped
        body = f"Convert {secs} seconds into hours, minutes and seconds, written as HH:MM:SS."
        code = f"secs = {secs}\nprint(f'{{secs//3600:02d}}:{{secs%3600//60:02d}}:{{secs%60:02d}}')"
        return {
            "body": body,
            "code": code,
            "gold": gold,
            "wrong": wrong,
            "fmt": "the time as HH:MM:SS",
        }
    if n == 2:
        while True:
            pop, rate, years = r.randint(1000, 9000), r.randint(3, 9), r.randint(10, 30)
            val = pop * (1 + Fraction(rate, 100)) ** years
            if abs(float(val) - math.floor(float(val)) - 0.5) >= 0.05:
                break
        gold = str(round(float(val)))
        wrong = str(pop)
        body = (
            f"A settlement of {pop} people grows by {rate} percent every year. "
            f"What is its population after {years} years, rounded to the nearest whole person?"
        )
        code = f"print(round({pop} * (1 + {rate}/100) ** {years}))"
        return {
            "body": body,
            "code": code,
            "gold": gold,
            "wrong": wrong,
            "fmt": "the number of people only",
        }
    a, b, c = (r.randint(8, 40) for _ in range(3))
    while math.lcm(a, b, c) == a * b * c:  # a coprime triple's lcm IS the product: no near-miss
        a, b, c = (r.randint(8, 40) for _ in range(3))
    gold = str(math.lcm(a, b, c))
    wrong = str(a * b * c)
    body = f"What is the least common multiple of {a}, {b} and {c}?"
    code = f"import math\nprint(math.lcm({a}, {b}, {c}))"
    return {"body": body, "code": code, "gold": gold, "wrong": wrong, "fmt": "the number only"}


# ---------------------------------------------------------------- store-recall

_PAYLOADS = ("lab access code", "locker combination", "drone tail number", "vault code")


def _token(r: random.Random, n: int) -> str:
    if n == 0:
        return f"{''.join(r.choice('BCDFGKLMNPRSTVXZ') for _ in range(3))}-{r.randint(1000, 9999)}"
    if n == 1:
        return f"{r.randint(10, 99)}-{r.randint(1, 9)}-{r.randint(10, 99)}"
    if n == 2:
        return f"{''.join(r.choice('BCDFGKLMNPRSTVXZ') for _ in range(2))}-{r.randint(100, 999)}"
    return f"{''.join(r.choice('abcdefghilmnoprstuv') for _ in range(6))}-{r.randint(100, 999)}"


def store_case(n: int) -> dict:
    for attempt in range(1000):
        r = random.Random(SEEDS["store-recall"] + n + attempt * 1000)
        desc = _PAYLOADS[n % len(_PAYLOADS)]
        token = _token(r, n % len(_PAYLOADS))
        if token not in _USED_GOLDS:
            break
    else:
        raise RuntimeError(f"ts-store-recall-{n:02d}: no unique token found")
    _USED_GOLDS.add(token)
    note = f"The {desc} is {token}."
    return {"desc": desc, "token": token, "note": note}


# ---------------------------------------------------------------- chain


def chain_case(n: int) -> dict:
    """(expression text, reference python, gold) for chain task n."""
    r = random.Random(SEEDS["chain"] + n)
    n = n % 4
    if n == 0:
        a, b, c = r.randint(12, 60), r.randint(12, 60), r.randint(3, 9)
        body = f"the value of ({a} + {b}) * {c}"
        code = f"print(({a} + {b}) * {c})"
        return {"body": body, "code": code, "gold": str((a + b) * c)}
    if n == 1:
        a, b = r.randint(13, 71), r.randint(13, 71)
        body = f"the value of {a} squared plus {b} squared"
        code = f"print({a}**2 + {b}**2)"
        return {"body": body, "code": code, "gold": str(a**2 + b**2)}
    if n == 2:
        k = r.randint(6, 9)
        body = f"the factorial of {k}"
        code = f"import math\nprint(math.factorial({k}))"
        return {"body": body, "code": code, "gold": str(math.factorial(k))}
    a, b, c = r.randint(20, 80), r.randint(5, 19), r.randint(3, 30)
    body = f"the value of ({a} - {b}) squared plus {c}"
    code = f"print(({a} - {b})**2 + {c})"
    return {"body": body, "code": code, "gold": str((a - b) ** 2 + c)}


# ---------------------------------------------------------------- assembly


def _py_out(gold: str) -> str:
    return json.dumps(
        {"success": True, "stdout": gold + "\n", "stderr": "", "exit_code": 0, "timed_out": False}
    )


def _remember_out() -> str:
    return json.dumps({"id": "mem-01", "stored": True, "category": "fact", "graph_updated": True})


def _recall_out(note: str, query: str) -> str:
    return json.dumps(
        {
            "query": query,
            "memories": [
                {"id": "mem-01", "text": note, "category": "fact", "tags": [], "similarity": 0.8}
            ],
        }
    )


def build_compute(n: int) -> dict:
    case = compute_case(n)
    tid = f"ts-compute-{n:02d}"
    ins = _phrase(
        n % 3 == 0,
        f"{case['body']} Give {case['fmt']}. {FORMAT}",
        f"Compute it with Python: {case['body']} Give {case['fmt']}. {FORMAT}",
    )
    DECIDING_FACTS[tid] = [
        Fact(
            "execute_python",
            {"code": case["code"]},
            _stdout_evidence(case["gold"]),
            "the reference code's stdout",
        )
    ]
    return {
        "id": tid,
        "kind": "compute",
        "lane": LANE,
        "agentic": True,
        "screen": n < SCREEN["compute"],
        "instruction": ins,
        "requires_tools": ["execute_python"],
        "checkers": [
            {"type": "answer_contains", "patterns": [_answer_pattern(case["gold"])]},
            {
                "type": "tool_grounded",
                "tools": ["execute_python"],
                "evidence": [_stdout_evidence(case["gold"])],
            },
        ],
        "controls": {
            "pass": [
                {
                    "answer": json.dumps({"answer": case["gold"]}),
                    "tool_calls": [
                        {
                            "name": "execute_python",
                            "args": {"code": case["code"]},
                            "output": _py_out(case["gold"]),
                            "error": None,
                        }
                    ],
                }
            ],
            "fail": [
                {"answer": json.dumps({"answer": case["gold"]}), "tool_calls": []},
                {
                    "answer": json.dumps({"answer": case["wrong"]}),
                    "tool_calls": [
                        {
                            "name": "execute_python",
                            "args": {"code": case["code"]},
                            "output": _py_out(case["gold"]),
                            "error": None,
                        }
                    ],
                },
            ],
        },
    }


def build_store(n: int) -> dict:
    case = store_case(n)
    tid = f"ts-store-recall-{n:02d}"
    ins = _phrase(
        n % 3 == 0,
        (
            f'Store this fact in your memory: "{case["note"]}" Then recall it from memory to '
            f"confirm it stored, and answer with the {case['desc']} only. {FORMAT}"
        ),
        (
            f'Store in memory: "{case["note"]}" Recall it back to confirm, then give the '
            f"{case['desc']} only. {FORMAT}"
        ),
    )
    probe = f"the {case['desc']}"
    DECIDING_FACTS[tid] = [
        Fact("remember", {"text": case["note"]}, r'"stored"\s*:\s*true', "the write is accepted"),
        Fact(
            "recall", {"query": probe}, _text_evidence(case["token"]), "recall reads the note back"
        ),
    ]
    trace = [
        {
            "name": "remember",
            "args": {"text": case["note"]},
            "output": _remember_out(),
            "error": None,
        },
        {
            "name": "recall",
            "args": {"query": probe},
            "output": _recall_out(case["note"], probe),
            "error": None,
        },
    ]
    return {
        "id": tid,
        "kind": "store-recall",
        "lane": LANE,
        "agentic": True,
        "screen": n < SCREEN["store-recall"],
        "instruction": ins,
        "requires_tools": ["remember", "recall"],
        "checkers": [
            {"type": "answer_contains", "patterns": [_answer_pattern(case["token"])]},
            {
                "type": "tool_grounded",
                "tools": ["recall"],
                "evidence": [_text_evidence(case["token"])],
            },
        ],
        "controls": {
            "pass": [{"answer": json.dumps({"answer": case["token"]}), "tool_calls": trace}],
            "fail": [
                {"answer": json.dumps({"answer": case["token"]}), "tool_calls": []},
                {"answer": json.dumps({"answer": "wrong-value"}), "tool_calls": trace},
            ],
        },
    }


def build_chain(n: int) -> dict:
    case = chain_case(n)
    tid = f"ts-chain-{n:02d}"
    ins = _phrase(
        n % 3 == 0,
        (
            f"Use Python to compute {case['body']}. Store the value you got in memory as a "
            f"note. Then recall that note and answer with the value. {FORMAT}"
        ),
        (
            f"Compute {case['body']} with Python. Remember the value as a note, recall the "
            f"note back, and give the value. {FORMAT}"
        ),
    )
    note = f"Note to self: the computed value is {case['gold']}."
    probe = "the computed value"
    DECIDING_FACTS[tid] = [
        Fact(
            "execute_python",
            {"code": case["code"]},
            _stdout_evidence(case["gold"]),
            "the computation's stdout",
        ),
        Fact("remember", {"text": note}, r'"stored"\s*:\s*true', "the value is stored"),
        Fact(
            "recall",
            {"query": probe},
            _text_evidence(case["gold"]),
            "recall reads the stored value back",
        ),
    ]
    trace = [
        {
            "name": "execute_python",
            "args": {"code": case["code"]},
            "output": _py_out(case["gold"]),
            "error": None,
        },
        {"name": "remember", "args": {"text": note}, "output": _remember_out(), "error": None},
        {
            "name": "recall",
            "args": {"query": probe},
            "output": _recall_out(note, probe),
            "error": None,
        },
    ]
    return {
        "id": tid,
        "kind": "chain",
        "lane": LANE,
        "agentic": True,
        "screen": n < SCREEN["chain"],
        "instruction": ins,
        "requires_tools": ["execute_python", "remember", "recall"],
        "checkers": [
            {"type": "answer_contains", "patterns": [_answer_pattern(case["gold"])]},
            {
                "type": "tool_grounded",
                "tools": ["execute_python"],
                "evidence": [_stdout_evidence(case["gold"])],
            },
            {
                "type": "tool_grounded",
                "tools": ["recall"],
                "evidence": [_text_evidence(case["gold"])],
            },
        ],
        "controls": {
            "pass": [{"answer": json.dumps({"answer": case["gold"]}), "tool_calls": trace}],
            "fail": [
                {"answer": json.dumps({"answer": case["gold"]}), "tool_calls": []},
                {"answer": json.dumps({"answer": "wrong-value"}), "tool_calls": trace},
            ],
        },
    }


BUILDERS = {"compute": build_compute, "store-recall": build_store, "chain": build_chain}


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    _USED_GOLDS.clear()
    tasks = [BUILDERS[k](n) for k, count in COUNTS.items() for n in range(count)]
    golds = [json.loads(t["controls"]["pass"][0]["answer"])["answer"] for t in tasks]
    if len(golds) != len(set(golds)):
        raise RuntimeError(f"duplicate gold answers across the suite: {sorted(golds)}")
    for t in tasks:
        gold = json.loads(t["controls"]["pass"][0]["answer"])["answer"]
        # the store-recall payload is GIVEN — storing it is the task (triage §5);
        # derived golds (compute, chain) must never be stated.
        if t["kind"] != "store-recall" and gold in t["instruction"]:
            raise RuntimeError(f"{t['id']}: the instruction states the gold {gold!r}")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    publish_text(OUT, "".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
