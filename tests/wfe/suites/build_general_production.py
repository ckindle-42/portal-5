"""Build tests/wfe/suites/general_production.jsonl and general_core_production.jsonl.

The general family's production suite (general-fast, general-deep, auto-daily): 48 tasks, 16 in
the screen tier. `general_core_production` is its computed and memory half (36 tasks, 12 screen),
the suite for the uncensored general lanes, whose tools carry no KB or document-create tool.
Every gold is computed here, never written by hand; facts are fictional or seeded per row.

- python (14)    a number or word that needs real computation; graded on the answer and on an
                 execute_python call whose stdout shows it (the reference code is the gold's
                 proof: the attainability check runs it through the sandbox);
- notool (10)    short exact reasoning, `no_tools`, answer-graded only: the one allowed exception
                 to the two-checker rule;
- memory (12)    a fictional preference or fact in `memory_seed`, reached through recall. Two of
                 them (INJECTED) are answered by memory injection without a call, so they are
                 answer-graded until the live read of auto-context decides their grounding rule;
- kb (6)         a fictional fact in `kb_seed`, reached through kb_search;
- document (6)   three reads and three creates taken from the documents suite, with its
                 checkers, gold and reference calls.

    uv run python tests/wfe/suites/build_general_production.py
"""

from __future__ import annotations

import json
import math
import random
import re
from datetime import date, timedelta
from pathlib import Path

from tests.wfe.suites import build_documents_production as docs
from tests.wfe.suites import build_research_production as res

OUT = Path(__file__).with_name("general_production.jsonl")
OUT_CORE = Path(__file__).with_name("general_core_production.jsonl")
FORMAT = 'Answer only as JSON {"answer": ...}.'
COUNTS = {"python": 14, "notool": 10, "memory": 12, "kb": 6, "document": 6}
SCREEN = {"python": 5, "notool": 3, "memory": 4, "kb": 2, "document": 2}
INJECTED = (6, 7)  # memory tasks answered by memory injection; grounding pending the live read
LANE = {
    "python": "computed",
    "notool": "computed",
    "memory": "memory",
    "kb": "knowledge",
    "document": "document",
}
#: (document task id in documents_production) per general document task, reads first
DOC_SOURCE = [
    "doc-read-01",
    "doc-read-04",
    "doc-read-10",
    "doc-create-01",
    "doc-create-04",
    "doc-create-08",
]

DECIDING_FACTS: dict[str, list[res.Fact]] = {}
#: task id -> (create tool, arguments), copied from the documents suite for the document creates
REFERENCE_CALLS: dict[str, tuple[str, dict]] = {}


def _pattern(gold: str) -> str:
    return rf"(?<![\w.]){re.escape(gold)}(?![\w])"


def _answer(gold: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(gold)}"?(?![\w.-])'


def _task(
    tid: str, kind: str, n: int, ins: str, checkers: list[dict], gold: str, trace: list[dict]
) -> dict:
    t = {
        "id": tid,
        "kind": kind,
        "lane": LANE[kind],
        "agentic": kind != "notool",
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "requires_tools": sorted({c["name"] for c in trace}),
        "checkers": checkers,
        "controls": {
            "pass": [{"answer": json.dumps({"answer": gold}), "tool_calls": trace}],
            "fail": [{"answer": json.dumps({"answer": "wrong-value"}), "tool_calls": trace}],
        },
    }
    if any(c["type"] == "tool_grounded" for c in checkers):
        # the right answer without its trace must fail: it was not retrieved through a tool
        t["controls"]["fail"].insert(0, json.dumps({"answer": gold}))
    return t


def _imperative(n: int, question: str, command: str) -> str:
    return command if n % 3 == 0 else question


# ---------------------------------------------------------------- python


def python_case(n: int) -> tuple[str, str, str]:
    """(instruction body, reference code, gold) for python task n."""
    r = random.Random(7000 + n)
    if n >= 10:
        return _python_case_c(n, r)
    if n == 0:
        d1 = date(2031, 1, 1) + timedelta(days=r.randint(0, 3000))
        d2 = d1 + timedelta(days=r.randint(4000, 9000))
        body = f"how many days are there from {d1.isoformat()} to {d2.isoformat()}?"
        code = f"from datetime import date\nprint((date({d2.year},{d2.month},{d2.day})-date({d1.year},{d1.month},{d1.day})).days)"
        return body, code, str((d2 - d1).days)
    if n == 1:
        d = date(2041, 1, 1) + timedelta(days=r.randint(0, 17000))
        body = f"which day of the week is {d.isoformat()}? Give the English weekday name."
        code = f"from datetime import date\nprint(date({d.year},{d.month},{d.day}).strftime('%A'))"
        return body, code, d.strftime("%A")
    if n == 2:
        top, a, b = r.randint(3000, 9000), r.choice([6, 7, 9]), r.choice([11, 13, 14])
        gold = sum((i % a == 0) != (i % b == 0) for i in range(1, top + 1))
        body = f"how many integers from 1 to {top} are divisible by {a} or by {b}, but not by both?"
        code = f"print(sum((i%{a}==0)!=(i%{b}==0) for i in range(1,{top}+1)))"
        return body, code, str(gold)
    if n == 3:
        top = r.randint(2500, 4500)
        primes = [p for p in range(2, top) if all(p % q for q in range(2, int(p**0.5) + 1))]
        body = f"what is the sum of all prime numbers below {top}?"
        code = f"print(sum(p for p in range(2,{top}) if all(p%q for q in range(2,int(p**0.5)+1))))"
        return body, code, str(sum(primes))
    if n == 4:
        s = r.randint(18, 27)
        gold = sum(
            1
            for k in range(10000, 100000)
            if sum(map(int, str(k))) == s
            and all(a != b for a, b in zip(str(k), str(k)[1:], strict=False))
        )
        body = (
            f"how many five-digit numbers (10000 to 99999) have a digit sum of exactly {s} "
            f"and no two equal digits next to each other?"
        )
        code = (
            f"print(sum(1 for k in range(10000,100000) if sum(map(int,str(k)))=={s} "
            f"and all(a!=b for a,b in zip(str(k),str(k)[1:]))))"
        )
        return body, code, str(gold)
    return _python_case_b(n, r)


def _python_case_c(n: int, r: random.Random) -> tuple[str, str, str]:
    """Cases 10-13 (the decision-floor expansion of the computed half)."""
    if n == 10:
        k = r.randint(30, 60)
        body = f"what is the sum of the digits of 2 raised to the power {k}?"
        code = f"print(sum(int(c) for c in str(2**{k})))"
        return body, code, str(sum(int(c) for c in str(2**k)))
    if n == 11:
        d, h, m = r.randint(2, 9), r.randint(2, 20), r.randint(5, 55)
        body = f"how many seconds are there in {d} days, {h} hours and {m} minutes?"
        code = f"print({d}*86400 + {h}*3600 + {m}*60)"
        return body, code, str(d * 86400 + h * 3600 + m * 60)
    if n == 12:
        k = r.randint(6, 9)
        primes: list[int] = []
        cand = 2
        while len(primes) < k:
            if all(cand % p for p in primes if p * p <= cand):
                primes.append(cand)
            cand += 1
        prod = math.prod(primes)
        body = f"what is the product of the first {k} prime numbers?"
        code = f"import math\nprint(math.prod({primes}))"
        return body, code, str(prod)
    hours = r.choice([2, 4, 5, 8])
    dist = hours * r.randint(40, 120)
    body = (
        f"a fictional train covers {dist} kilometres in {hours} hours. "
        f"what is its average speed in kilometres per hour?"
    )
    code = f"print({dist} // {hours})"
    return body, code, str(dist // hours)


def _python_case_b(n: int, r: random.Random) -> tuple[str, str, str]:
    if n == 5:
        idx, m = r.randint(150, 400), r.randint(100003, 999983)
        a, b = 0, 1
        for _ in range(idx):
            a, b = b, (a + b) % m
        body = f"what is the {idx}th Fibonacci number modulo {m}? Use F(0)=0 and F(1)=1."
        code = f"a,b=0,1\nfor _ in range({idx}):\n    a,b=b,(a+b)%{m}\nprint(a)"
        return body, code, str(a)
    if n == 6:
        regions = ["north", "south", "east", "west"]
        rows = [(r.choice(regions), r.randint(2, 40), r.randint(3, 19)) for _ in range(9)]
        want = rows[0][0]
        gold = sum(u * p for g, u, p in rows if g == want)
        text = "region,units,price\n" + "\n".join(f"{g},{u},{p}" for g, u, p in rows)
        body = (
            f"given this CSV, what is the total of units times price over the rows whose "
            f"region is {want}?\n{text}"
        )
        code = (
            f"import csv,io\nt={text!r}\n"
            f"print(sum(int(x['units'])*int(x['price']) for x in csv.DictReader(io.StringIO(t)) "
            f"if x['region']=='{want}'))"
        )
        return body, code, str(gold)
    if n == 7:
        words = [
            "".join(r.choice("abcdefghilmnoprstuv") for _ in range(r.randint(3, 11)))
            for _ in range(24)
        ]
        text = " ".join(words)
        gold = sum(sum(c in "aeiou" for c in w) > 3 for w in words)
        body = f"how many of the words in this list contain more than 3 vowels (a, e, i, o, u)?\n{text}"
        code = f"print(sum(sum(c in 'aeiou' for c in w)>3 for w in '{text}'.split()))"
        return body, code, str(gold)
    if n == 8:
        start = r.randint(100000, 900000)
        steps, k = 0, start
        while k != 1:
            k = k // 2 if k % 2 == 0 else 3 * k + 1
            steps += 1
        body = (
            f"how many steps does the Collatz sequence take to reach 1 starting from {start}? "
            f"(Halve an even number, otherwise triple it and add 1.)"
        )
        code = f"k,s={start},0\nwhile k!=1:\n    k=k//2 if k%2==0 else 3*k+1\n    s+=1\nprint(s)"
        return body, code, str(steps)
    a, b, m = r.randint(10**6, 10**7), r.randint(10**5, 10**6), r.randint(10**8, 10**9)
    body = f"what is {a} raised to the power {b}, modulo {m}?"
    return body, f"print(pow({a},{b},{m}))", str(pow(a, b, m))


def build_python(n: int) -> dict:
    body, code, gold = python_case(n)
    ins = _imperative(
        n, f"Using Python, {body} {FORMAT}", f"Use Python to work this out: {body} {FORMAT}"
    )
    ins = ins[0].upper() + ins[1:]
    tid = f"gen-python-{n:02d}"
    out = json.dumps(
        {"success": True, "stdout": gold + "\n", "stderr": "", "exit_code": 0, "timed_out": False}
    )
    DECIDING_FACTS[tid] = [
        res.Fact("execute_python", {"code": code}, _pattern(gold), "the reference code's stdout")
    ]
    return _task(
        tid,
        "python",
        n,
        ins,
        [
            {"type": "answer_contains", "patterns": [_answer(gold)]},
            {"type": "tool_grounded", "tools": ["execute_python"], "evidence": [_pattern(gold)]},
        ],
        gold,
        [{"name": "execute_python", "args": {"code": code}, "output": out, "error": None}],
    )


# ---------------------------------------------------------------- notool

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_NAMES = ["Kestrel", "Brannoch", "Ysolde", "Tobren", "Selwyn", "Anja", "Corvin", "Leda"]


def notool_case(n: int) -> tuple[str, str]:
    r = random.Random(7100 + n)
    if n == 0:
        i, k = r.randrange(7), r.randint(20, 400)
        return (
            f"Today is {_DAYS[i]}. Which day of the week will it be {k} days from today?",
            _DAYS[(i + k) % 7],
        )
    if n == 1:
        diff = r.randint(3, 9)
        mins = r.randint(12, 60)
        out = r.randint(2, 6)
        return (
            f"A tank is empty. A pipe adds {out + diff} litres a minute while a drain removes "
            f"{out} litres a minute, both running together. The tank holds "
            f"{diff * mins} litres. How many minutes until it is full?",
            str(mins),
        )
    if n == 2:
        a, b, c, d = r.sample(_NAMES, 4)
        return (
            f"{a} is taller than {b}. {b} is taller than {c}. {d} is shorter than {c}. "
            f"Who is the shortest of the four?",
            d,
        )
    if n == 3:
        h, m = r.randint(0, 23), r.randint(0, 59)
        add = r.randint(200, 900)
        t = (h * 60 + m + add) % (24 * 60)
        return (
            f"A 24-hour clock shows {h:02d}:{m:02d}. What does it show {add} minutes later? "
            f"Write it as HH:MM.",
            f"{t // 60:02d}:{t % 60:02d}",
        )
    if n == 4:
        a0, ratio = r.randint(2, 9), r.randint(2, 4)
        seq = [a0 * ratio**i for i in range(4)]
        return (
            f"What is the next number in the sequence {', '.join(map(str, seq))}?",
            str(a0 * ratio**4),
        )
    if n == 6:
        v, c, d = r.randint(18, 45), r.randint(6, 12), r.randint(3, 7)
        return (
            f"A fictional ferry carries {v} vehicles per crossing and makes {c} crossings a day. "
            f"How many vehicles does it carry in {d} days?",
            str(v * c * d),
        )
    if n == 7:
        deposit = 100 * r.randint(5, 40)
        rate = r.choice([4, 5, 6, 8])
        years = r.randint(2, 5)
        return (
            f"A deposit of {deposit} credits earns {rate} percent simple interest each year. "
            f"How much interest does it earn over {years} years?",
            str(deposit * rate * years // 100),
        )
    if n == 8:
        h1, m1 = r.randint(6, 11), r.choice([0, 15, 30, 45])
        h2, m2 = r.randint(h1 + 1, 17), r.choice([0, 15, 30, 45])
        return (
            f"How many minutes are there between {h1:02d}:{m1:02d} and {h2:02d}:{m2:02d} "
            f"on the same day?",
            str((h2 * 60 + m2) - (h1 * 60 + m1)),
        )
    if n == 9:
        serves = r.choice([3, 4, 6])
        grams = serves * r.randint(30, 90)
        want = serves + r.randint(2, 5)
        return (
            f"A recipe for {serves} people uses {grams} grams of flour. "
            f"How many grams are needed for {want} people?",
            str(grams * want // serves),
        )
    while True:
        base = r.choice([200, 400, 600, 800, 1000, 1200])
        up, down = r.choice([10, 20, 25, 50]), r.choice([10, 20, 25, 50])
        final = base * (100 + up) * (100 - down) / 10000
        if final == int(final) and up != down:
            return (
                f"A coat costs {base} credits. The price goes up by {up} percent, then the new "
                f"price goes down by {down} percent. What is the final price in credits?",
                str(int(final)),
            )


def build_notool(n: int) -> dict:
    question, gold = notool_case(n)
    tid = f"gen-notool-{n:02d}"
    t = _task(
        tid,
        "notool",
        n,
        f"{question} {FORMAT}",
        [{"type": "answer_contains", "patterns": [_answer(gold)]}],
        gold,
        [],
    )
    t["no_tools"] = True
    return t


# ---------------------------------------------------------------- memory

#: (sentence with {v}, the instruction's own wording, answer format, value kind)
MEMORY_ITEMS = [
    ("My locker combination is {v}.", "my locker combination", "the digits only", "digits"),
    ("My favourite tea blend is called {v}.", "my favourite tea blend", "the name only", "word"),
    ("The vet who looks after my dog is Dr. {v}.", "my dog's vet", "the full name", "person"),
    ("My flight confirmation code is {v}.", "my flight confirmation code", "the code only", "code"),
    ("My daughter attends {v}.", "the school my daughter attends", "the school's name", "school"),
    (
        "The Wi-Fi password at the lake cabin is {v}.",
        "the lake cabin Wi-Fi password",
        "the password only",
        "passwd",
    ),
    ("My gym membership number is {v}.", "my gym membership number", "the number only", "digits"),
    ("My mechanic is {v}.", "the name of my mechanic", "the full name", "person"),
    ("My car's licence plate is {v}.", "my car's licence plate", "the plate only", "plate"),
    ("My library card number is {v}.", "my library card number", "the number only", "digits"),
    (
        "My insurance policy number is {v}.",
        "my insurance policy number",
        "the policy number only",
        "code",
    ),
    ("My dentist is Dr. {v}.", "my dentist", "the full name", "person"),
]


def memory_value(w: res.World, kind: str) -> str:
    r = w.rng
    if kind == "digits":
        return w._unique(lambda: str(r.randint(100000, 999999)))
    if kind == "word":
        return w._unique(lambda: w.word() + " blend")
    if kind == "person":
        return w.value("person")
    if kind == "code":
        return w._unique(
            lambda: "".join(r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        )
    if kind == "school":
        return w._unique(lambda: f"{w.word()} Academy")
    if kind == "plate":
        return w._unique(
            lambda: (
                "".join(r.choice("BCDFGKLMNPRSTVXZ") for _ in range(2)) + f"-{r.randint(100, 999)}"
            )
        )
    return w._unique(lambda: f"{w.word().lower()}-{r.randint(10, 99)}")


def build_memory(w: res.World, n: int) -> dict:
    sentence, core, fmt, kind = MEMORY_ITEMS[n]
    gold = memory_value(w, kind)
    notes = [f"Note to self: {sentence.format(v=gold)}"]
    for s2, _, _, k2 in [MEMORY_ITEMS[(n + j) % len(MEMORY_ITEMS)] for j in (1, 3, 5)]:
        notes.append(f"Note to self: {s2.format(v=memory_value(w, k2))}")
    ins = _imperative(
        n,
        f"What did I tell you {core} is? Give {fmt}. {FORMAT}",
        f"Check your stored memory notes for {core} and give {fmt}. {FORMAT}",
    )
    tid = f"gen-memory-{n:02d}"
    q = core
    DECIDING_FACTS[tid] = [res.Fact("recall", {"query": q}, re.escape(gold), f"memory: {core}")]
    checkers = [{"type": "answer_contains", "patterns": [_answer(gold)]}]
    if n not in INJECTED:
        checkers.append(res._grounded(res.MEM_TOOLS, [re.escape(gold)]))
    t = _task(
        tid,
        "memory",
        n,
        ins,
        checkers,
        gold,
        [res._call("recall", q, res.mem_output(notes, q))],
    )
    t["memory_seed"] = notes
    return t


# ---------------------------------------------------------------- knowledge base


def build_kb(w: res.World, n: int) -> dict:
    etype = ["org", "device"][n % 2]
    entity = w.org() if etype == "org" else w.device()
    attr = list(res.ATTRS[etype])[(n // 2) % len(res.ATTRS[etype])]
    facts = res.entity_facts(w, etype)
    gold, fmt = facts[attr], res.ATTRS[etype][attr][1]
    kb = {f"{res.slug(entity)}.md": res.doc_text(etype, entity, facts)}
    for _ in range(3):
        s = w.org() if etype == "org" else w.device()
        kb[f"{res.slug(s)}.md"] = res.doc_text(etype, s, res.entity_facts(w, etype))
    core = f"the {attr} of {entity}"
    ins = _imperative(
        n,
        f"According to the knowledge base, what is {core}? Give {fmt}. {FORMAT}",
        f"Look up {core} in the knowledge base and give {fmt}. {FORMAT}",
    )
    q = f"{attr} of {entity}"
    tid = f"gen-kb-{n:02d}"
    DECIDING_FACTS[tid] = [
        res.Fact("kb_search", {"query": q}, re.escape(gold), f"{entity}: {attr}")
    ]
    t = _task(
        tid,
        "kb",
        n,
        ins,
        [
            {"type": "answer_contains", "patterns": [_answer(gold)]},
            res._grounded(["kb_search"], res._ev(entity, gold)),
        ],
        gold,
        [res._call("kb_search", q, res.kb_output(dict(kb), q))],
    )
    t["kb_seed"] = kb
    return t


# ---------------------------------------------------------------- documents


def build_documents() -> list[dict]:
    by_id = {t["id"]: t for t in docs.build()}
    out = []
    for n, src in enumerate(DOC_SOURCE):
        t = json.loads(json.dumps(by_id[src]))
        tid = f"gen-document-{n:02d}"
        t.update({"id": tid, "kind": "document", "lane": LANE["document"], "screen": n in (0, 3)})
        DECIDING_FACTS[tid] = [
            res.Fact(f.tool, f.args, f.pattern, f.why) for f in docs.DECIDING_FACTS.get(src, [])
        ]
        if src in docs.REFERENCE_CALLS:
            REFERENCE_CALLS[tid] = docs.REFERENCE_CALLS[src]
        out.append(t)
    return out


def build() -> list[dict]:
    """The 36 tasks of general_production."""
    DECIDING_FACTS.clear()
    REFERENCE_CALLS.clear()
    w = res.World(20261018)
    tasks = [build_python(n) for n in range(COUNTS["python"])]
    tasks += [build_notool(n) for n in range(COUNTS["notool"])]
    tasks += [build_memory(w, n) for n in range(COUNTS["memory"])]
    tasks += [build_kb(w, n) for n in range(COUNTS["kb"])]
    tasks += build_documents()
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def build_core(tasks: list[dict] | None = None) -> list[dict]:
    """The computed and memory half: the uncensored lanes' suite."""
    return [t for t in tasks or build() if t["kind"] in ("python", "notool", "memory")]


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    core = build_core(tasks)
    OUT_CORE.write_text("".join(json.dumps(t) + "\n" for t in core))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")
    print(f"wrote {OUT_CORE.name}: {len(core)} tasks, {sum(t['screen'] for t in core)} screen")


if __name__ == "__main__":
    main()
