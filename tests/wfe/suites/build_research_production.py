"""Build tests/wfe/suites/research_production.jsonl, auto-research's production suite.

Every fact is fictional (an invented organisation, project, device, person, city or date), so
a model cannot pass from training. Facts are seeded per row into the row's own scope: documents
through `kb_seed`, notes through `memory_seed`. Gold is computed here from the seeded data and
never written by hand. Five kinds, 36 tasks, 12 in the screen tier:

- lookup (8)     one KB document holds the fact;
- multihop (10)  a project document names its lead organisation, an organisation document holds
                 the value: two documents, two grounded calls;
- memory (6)     the fact lives only in a stored note (recall / graph_recall);
- conflict (6)   two documents give different values; the instruction says the latest effective
                 date wins, and the loser is a forbidden answer;
- absent (6)     the asked-for entity is in neither store; sibling entities carry the decoy
                 values. The defined answer is NOT_FOUND, graded with the decoys forbidden.

Every task is graded on its answer (answer_contains) and on where it came from (tool_grounded on
the row's own exec_audit trace). Web tools are not in the auto-research allowlist (a live page
cannot hold a fixed gold), so the tool set is the KB and memory tools only.

    uv run python tests/wfe/suites/build_research_production.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import NamedTuple

OUT = Path(__file__).with_name("research_production.jsonl")
KB_TOOLS = ["kb_search", "kb_search_all"]
MEM_TOOLS = ["recall", "graph_recall"]
NOT_FOUND = "NOT_FOUND"
FORMAT = 'Answer only as JSON {"answer": "..."}'
SCREEN = {"lookup": 2, "multihop": 3, "memory": 2, "conflict": 2, "absent": 3}
COUNTS = {"lookup": 8, "multihop": 10, "memory": 6, "conflict": 6, "absent": 6}


class Fact(NamedTuple):
    """One fact the gold depends on, and the offered tool call that must expose it.

    `pattern` is searched in the tool's output (JSON escapes and whitespace collapsed). With
    `absent` set the fact must NOT be exposed: the asked-for entity exists in neither store."""

    tool: str
    args: dict
    pattern: str
    why: str
    absent: bool = False


DECIDING_FACTS: dict[str, list[Fact]] = {}

_SYL = ["or", "van", "qui", "lle", "mar", "tho", "zen", "bra", "kel", "dru", "fy", "nas", "wex"]
_END = ["ane", "ith", "ova", "ex", "ura", "eld", "ion", "ack"]
_FIRST = [
    "Ilse",
    "Tobren",
    "Maruk",
    "Selwyn",
    "Anja",
    "Corvin",
    "Leda",
    "Haskel",
    "Odrun",
    "Pell",
    "Wystan",
    "Ysolde",
    "Brannoch",
    "Kaelith",
    "Dorrin",
    "Evander",
    "Fenna",
    "Gorvald",
]
_LAST = [
    "Vandermeer",
    "Okonkwo-Reyes",
    "Thale",
    "Brunnemark",
    "Castellane",
    "Ruddock",
    "Sivarin",
    "Aldercott",
    "Mbeki-Lund",
    "Quarrington",
    "Hollis-Park",
    "Ferrante",
    "Dzhurov",
    "Ashgrove",
    "Nakagawa-Bell",
    "Tremaine",
]
_ORG = ["Institute", "Consortium", "Works", "Observatory", "Foundry", "Cooperative"]
_DEV = ["Array", "Drone", "Relay", "Crawler", "Buoy", "Lift"]

#: attribute -> (noun phrase, sentence template, answer format, value kind)
ATTRS = {
    "org": {
        "headquarters city": ("{e} is headquartered in {v}.", "the city name only", "city"),
        "founding year": ("{e} was founded in {v}.", "the four-digit year", "year"),
        "director": ("The director of {e} is {v}.", "the full name", "person"),
        "annual budget in millions of credits": (
            "{e} operates on an annual budget of {v} million credits.",
            "the number only",
            "int",
        ),
    },
    "device": {
        "maximum payload in kilograms": (
            "The {e} carries a maximum payload of {v} kilograms.",
            "the number only",
            "int",
        ),
        "release date": (
            "The {e} was released on {v}.",
            "an ISO date, YYYY-MM-DD",
            "date",
        ),
        "lead engineer": ("The lead engineer of the {e} is {v}.", "the full name", "person"),
    },
}


class World:
    """Seeded generator of unique invented names and values."""

    def __init__(self, seed: int = 20261017) -> None:
        self.rng = random.Random(seed)
        self.used: set[str] = set()

    def _unique(self, make) -> str:
        for _ in range(10_000):
            if (v := make()) not in self.used:
                break
        else:
            raise RuntimeError("value space exhausted")
        self.used.add(v)
        return v

    def word(self) -> str:
        r = self.rng
        return "".join(r.choice(_SYL) for _ in range(2)).capitalize() + r.choice(_END)

    def value(self, kind: str) -> str:
        r = self.rng
        if kind == "city":
            return self._unique(lambda: self.word() + r.choice(["haven", "ford", "mere", "stad"]))
        if kind == "person":
            return self._unique(lambda: f"{r.choice(_FIRST)} {r.choice(_LAST)}")
        if kind == "year":
            return self._unique(lambda: str(r.randint(1101, 2019)))
        if kind == "int":
            return self._unique(lambda: str(r.randint(1137, 9986)))
        if kind == "date":
            return self._unique(
                lambda: f"{r.randint(2011, 2025)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"
            )
        raise ValueError(kind)

    def org(self) -> str:
        return self._unique(lambda: f"{self.word()} {self.rng.choice(_ORG)}")

    def device(self) -> str:
        return self._unique(
            lambda: f"{self.word()}-{self.rng.randint(2, 9)} {self.rng.choice(_DEV)}"
        )

    def project(self) -> str:
        return self._unique(lambda: f"Project {self.word()}")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sentence(etype: str, attr: str, entity: str, value: str) -> str:
    return ATTRS[etype][attr][0].format(e=entity, v=value)


def entity_facts(w: World, etype: str) -> dict[str, str]:
    return {a: w.value(spec[2]) for a, spec in ATTRS[etype].items()}


def doc_text(etype: str, entity: str, facts: dict[str, str]) -> str:
    body = " ".join(sentence(etype, a, entity, v) for a, v in facts.items())
    return f"# {entity}\n\n{body}\n"


def note(etype: str, attr: str, entity: str, value: str) -> str:
    return f"Note to self: {sentence(etype, attr, entity, value)}"


def _json_answer(value: str) -> str:
    return json.dumps({"answer": value})


def _answer_pattern(value: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(value)}"?(?![\w.-])'


def _ev(*parts: str) -> list[str]:
    return [re.escape(p) for p in parts]


def kb_output(docs: dict[str, str], query: str) -> str:
    """What kb_search_all returns for `query` (rag_multimodal._search_all's documented shape)."""
    rows = [
        {"kb_id": "run", "source_file": n, "text": t, "fused_score": 0.5, "kind": "text"}
        for n, t in docs.items()
    ]
    return json.dumps({"query": query, "num_results": len(rows), "results": rows})


def mem_output(notes: list[str], query: str) -> str:
    """What recall returns (graph_memory._recall's `memories` rows)."""
    mem = [
        {"id": str(i), "text": t, "category": "fact", "tags": [], "similarity": 0.8}
        for i, t in enumerate(notes)
    ]
    return json.dumps({"query": query, "memories": mem})


def _grounded(tools: list[str], evidence: list[str]) -> dict:
    return {"type": "tool_grounded", "tools": tools, "evidence": evidence}


def _task(
    tid: str,
    kind: str,
    n: int,
    instruction: str,
    checkers: list[dict],
    gold: str,
    trace: list[dict],
    kb: dict[str, str] | None = None,
    mem: list[str] | None = None,
    wrong: str = "unknown-value",
) -> dict:
    t = {
        "id": tid,
        "kind": kind,
        "lane": "research",
        "agentic": True,
        "screen": n < SCREEN[kind],
        "instruction": instruction,
        "requires_tools": sorted({c["name"] for c in trace}),
        "checkers": checkers,
        "controls": {
            "pass": [{"answer": _json_answer(gold), "tool_calls": trace}],
            "fail": [
                _json_answer(gold),
                {"answer": _json_answer(wrong), "tool_calls": trace},
            ],
        },
    }
    if kb:
        t["kb_seed"] = kb
    if mem:
        t["memory_seed"] = mem
    return t


def _call(name: str, query: str, output: str) -> dict:
    return {"name": name, "args": {"query": query}, "output": output, "error": None}


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


def build_lookup(w: World, n: int) -> dict:
    etype = ["org", "device"][n % 2]
    entity = w.org() if etype == "org" else w.device()
    attrs = list(ATTRS[etype])
    attr = attrs[n % len(attrs)]
    facts = entity_facts(w, etype)
    sibs = {w.org() if etype == "org" else w.device(): None for _ in range(3)}
    docs = {f"{slug(entity)}.md": doc_text(etype, entity, facts)}
    for s in sibs:
        docs[f"{slug(s)}.md"] = doc_text(etype, s, entity_facts(w, etype))
    gold, fmt = facts[attr], ATTRS[etype][attr][1]
    core = f"the {attr} of {entity}"
    ins = _phrase(
        n % 3 == 0,
        f"According to the knowledge base, what is {core}? Give {fmt}. {FORMAT}.",
        f"Look up {core} in the knowledge base and give {fmt}. {FORMAT}.",
    )
    q = f"{attr} of {entity}"
    tid = f"res-lookup-{n:02d}"
    DECIDING_FACTS[tid] = [
        Fact("kb_search_all", {"query": q}, re.escape(gold), f"{entity}: {attr} in the KB")
    ]
    return _task(
        tid,
        "lookup",
        n,
        ins,
        [
            {"type": "answer_contains", "patterns": [_answer_pattern(gold)]},
            _grounded(KB_TOOLS, _ev(entity, gold)),
        ],
        gold,
        [_call("kb_search_all", q, kb_output(dict(docs), q))],
        kb=docs,
    )


def build_multihop(w: World, n: int) -> dict:
    org, project = w.org(), w.project()
    attr = list(ATTRS["org"])[n % 4]
    facts = entity_facts(w, "org")
    gold, fmt = facts[attr], ATTRS["org"][attr][1]
    docs = {
        f"{slug(project)}.md": (
            f"# {project}\n\n{project} is led by the {org}. "
            f"It was approved in {w.value('year')} and is reviewed twice a year.\n"
        ),
        f"{slug(org)}.md": doc_text("org", org, facts),
    }
    for _ in range(2):
        p, o = w.project(), w.org()
        docs[f"{slug(p)}.md"] = f"# {p}\n\n{p} is led by the {o}.\n"
        docs[f"{slug(o)}.md"] = doc_text("org", o, entity_facts(w, "org"))
    core = f"the {attr} of the organisation that leads {project}"
    ins = _phrase(
        n % 3 == 0,
        f"According to the knowledge base, what is {core}? Give {fmt}. {FORMAT}.",
        f"Find {core} in the knowledge base and give {fmt}. {FORMAT}.",
    )
    q1, q2 = f"organisation that leads {project}", f"{attr} of {org}"
    tid = f"res-multihop-{n:02d}"
    DECIDING_FACTS[tid] = [
        Fact("kb_search_all", {"query": q1}, re.escape(org), f"{project} names its lead"),
        Fact("kb_search_all", {"query": q2}, re.escape(gold), f"{org}: {attr}"),
    ]
    first = {k: v for k, v in docs.items() if k.startswith(slug(project))}
    second = {k: v for k, v in docs.items() if k.startswith(slug(org))}
    return _task(
        tid,
        "multihop",
        n,
        ins,
        [
            {"type": "answer_contains", "patterns": [_answer_pattern(gold)]},
            _grounded(KB_TOOLS, _ev(project, org)),
            _grounded(KB_TOOLS, _ev(org, gold)),
        ],
        gold,
        [
            _call("kb_search_all", q1, kb_output(first, q1)),
            _call("kb_search_all", q2, kb_output(second, q2)),
        ],
        kb=docs,
    )


def build_memory(w: World, n: int) -> dict:
    etype = ["org", "device"][n % 2]
    entity = w.org() if etype == "org" else w.device()
    attr = list(ATTRS[etype])[(n // 2) % len(ATTRS[etype])]
    facts = entity_facts(w, etype)
    gold, fmt = facts[attr], ATTRS[etype][attr][1]
    notes = [note(etype, attr, entity, gold)]
    for _ in range(3):
        s = w.org() if etype == "org" else w.device()
        notes.append(note(etype, attr, s, w.value(ATTRS[etype][attr][2])))
    core = f"the {attr} of {entity}"
    ins = _phrase(
        n % 3 == 0,
        f"From the notes you stored in memory, what is {core}? Give {fmt}. {FORMAT}.",
        f"Check your stored memory notes for {core} and give {fmt}. {FORMAT}.",
    )
    q = f"{attr} of {entity}"
    tid = f"res-memory-{n:02d}"
    DECIDING_FACTS[tid] = [
        Fact("recall", {"query": q}, re.escape(gold), f"{entity}: {attr} in memory")
    ]
    return _task(
        tid,
        "memory",
        n,
        ins,
        [
            {"type": "answer_contains", "patterns": [_answer_pattern(gold)]},
            _grounded(MEM_TOOLS, _ev(entity, gold)),
        ],
        gold,
        [_call("recall", q, mem_output(notes, q))],
        mem=notes,
    )


def build_conflict(w: World, n: int) -> dict:
    etype = ["org", "device"][n % 2]
    entity = w.org() if etype == "org" else w.device()
    attr = list(ATTRS[etype])[(n // 2) % len(ATTRS[etype])]
    kind = ATTRS[etype][attr][2]
    old_v, new_v = w.value(kind), w.value(kind)
    d_old, d_new = f"2024-0{1 + n % 4}-1{n % 9}", f"2026-0{5 + n % 4}-2{n % 9}"
    swap = n % 2 == 1  # which file name holds the newer record
    names = (f"{slug(entity)}-rev-a.md", f"{slug(entity)}-rev-b.md")
    new_name, old_name = (names[1], names[0]) if swap else (names[0], names[1])

    def rec(date: str, v: str) -> str:
        return (
            f"# {entity} record\n\nEffective date: {date}\n\n{sentence(etype, attr, entity, v)}\n"
        )

    docs = {new_name: rec(d_new, new_v), old_name: rec(d_old, old_v)}
    for _ in range(2):
        s = w.org() if etype == "org" else w.device()
        docs[f"{slug(s)}.md"] = doc_text(etype, s, entity_facts(w, etype))
    fmt = ATTRS[etype][attr][1]
    core = f"the {attr} of {entity}"
    rule = "If the records disagree, the one with the latest effective date is correct."
    ins = _phrase(
        n % 3 == 0,
        f"According to the knowledge base, what is {core}? {rule} Give {fmt}. {FORMAT}.",
        f"Look up {core} in the knowledge base. {rule} Give {fmt}. {FORMAT}.",
    )
    q = f"{attr} of {entity}"
    tid = f"res-conflict-{n:02d}"
    DECIDING_FACTS[tid] = [
        Fact("kb_search_all", {"query": q}, re.escape(new_v), f"{entity}: newer record"),
        Fact("kb_search_all", {"query": q}, re.escape(old_v), f"{entity}: older record"),
    ]
    both = {k: docs[k] for k in (new_name, old_name)}
    return _task(
        tid,
        "conflict",
        n,
        ins,
        [
            {
                "type": "answer_contains",
                "patterns": [_answer_pattern(new_v)],
                "forbid": [_answer_pattern(old_v)],
            },
            _grounded(KB_TOOLS, _ev(entity, new_v, d_new)),
        ],
        new_v,
        [_call("kb_search_all", q, kb_output(both, q))],
        kb=docs,
        wrong=old_v,
    )


def build_absent(w: World, n: int) -> dict:
    etype = ["org", "device"][n % 2]
    entity = w.org() if etype == "org" else w.device()  # in neither store
    attr = list(ATTRS[etype])[(n // 2) % len(ATTRS[etype])]
    kind = ATTRS[etype][attr][2]
    sibs = [w.org() if etype == "org" else w.device() for _ in range(3)]
    decoys = [w.value(kind) for _ in sibs]
    docs = {
        f"{slug(s)}.md": doc_text(
            etype,
            s,
            {a: (d if a == attr else w.value(spec[2])) for a, spec in ATTRS[etype].items()},
        )
        for s, d in zip(sibs, decoys, strict=True)
    }
    notes = [note(etype, attr, s, d) for s, d in zip(sibs[:2], decoys[:2], strict=True)]
    core = f"the {attr} of {entity}"
    rule = f'If neither holds it, answer exactly {{"answer": "{NOT_FOUND}"}}.'
    ins = _phrase(
        n % 3 == 0,
        f"What is {core}? Check the knowledge base and your stored memory notes. {rule} "
        f"Otherwise give {ATTRS[etype][attr][1]}. {FORMAT}.",
        f"Find {core} in the knowledge base or your stored memory notes. {rule} "
        f"Otherwise give {ATTRS[etype][attr][1]}. {FORMAT}.",
    )
    q = f"{attr} of {entity}"
    tid = f"res-absent-{n:02d}"
    DECIDING_FACTS[tid] = [
        Fact("kb_search_all", {"query": q}, re.escape(entity), f"{entity} is not in the KB", True),
        Fact("recall", {"query": q}, re.escape(entity), f"{entity} is not in memory", True),
    ]
    return _task(
        tid,
        "absent",
        n,
        ins,
        [
            {
                "type": "answer_contains",
                "patterns": [_answer_pattern(NOT_FOUND)],
                "forbid": [_answer_pattern(d) for d in decoys],
                "forbid_in_tool_output": [NOT_FOUND],
            },
            _grounded(KB_TOOLS + MEM_TOOLS, [r"\S"]),
        ],
        NOT_FOUND,
        [_call("kb_search_all", q, kb_output(docs, q))],
        kb=docs,
        mem=notes,
        wrong=decoys[0],
    )


BUILDERS = {
    "lookup": build_lookup,
    "multihop": build_multihop,
    "memory": build_memory,
    "conflict": build_conflict,
    "absent": build_absent,
}


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    w = World()
    tasks = [BUILDERS[k](w, n) for k, count in COUNTS.items() for n in range(count)]
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
