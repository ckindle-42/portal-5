"""Build tests/wfe/suites/reading_long_production.jsonl, auto-compliance::reading's long-context
reading suite (WFE new-instruments brief, I-LONGREAD).

reading_production reads short tool outputs; the seat decision at the 128k window (gemma4
26b-a4b ctx128k vs Qwen3.8-27B ctx128k) needs documents that actually fill it. Every document
here is synthetic and fictional — sites, people, codes, items and dates are invented by this
generator from a seed — so the gold is known and nothing can be recalled or licensed. Three
kinds, 36 tasks, 12 in the screen tier (four per kind), each at one of three sizes (about 40k,
80k and 112k tokens at the measured density below; 112k leaves room in the 131072 window for the
system prompt and a short answer):

- needle (12)       one fact (a site's vault code) placed at a recorded depth (10-90 %, in the
                    task id) among thousands of similar entries, including near-name decoys
                    (same site name with another sector or suffix) whose codes differ;
- aggregation (12)  3-5 log entries for one exactly-named item, spread through the log among
                    near-name decoy items, combined as a sum, a latest date, or a count;
- quote (12)        the one sentence that states when a named site closes its loading dock,
                    among near-identical sentences for decoy sites; graded as the exact string.

The documents are NOT committed. A task carries a `doc_spec` (generator module, seed, size,
placement) and an instruction with a {{DOCUMENT}} marker; tests.wfe.runner.load_suite renders
the document from the spec at load time and checks its sha256, so a generator change that
alters a document fails loudly instead of silently moving the gold. The gold is computed here
and re-derived from the rendered text (build() raises if they disagree). No tools are offered:
the document is in the prompt, which is what is being measured.

    uv run python tests/wfe/suites/build_reading_long_production.py
"""

from __future__ import annotations

import functools
import hashlib
import json
import random
import re
from pathlib import Path

from tests.wfe.suites._publish import publish_text

OUT = Path(__file__).with_name("reading_long_production.jsonl")
GENERATOR = "tests.wfe.suites.build_reading_long_production"
COUNTS = {"needle": 12, "aggregation": 12, "quote": 12}
SCREEN = {"needle": 4, "aggregation": 4, "quote": 4}
LANE = "reading"
SEEDS = {"needle": 5100, "aggregation": 5200, "quote": 5300}
TIERS = (40_000, 80_000, 112_000)  # tokens, by the measured density below
#: Characters per token measured on rendered documents with the Gemma-3 (= EmbeddingGemma-2)
#: and Qwen3.6 tokenizers (2026-10-18; the lower of the two, per kind). IDs, dates and invented
#: names tokenize at 2.6-3.2 characters per token, not the usual 4, so a "4 chars/token"
#: size would put the 112k tier near 150k real tokens and past the window.
CHARS_PER_TOKEN = {"needle": 2.68, "aggregation": 2.57, "quote": 3.14}
#: Needle/quote depth (percent) per task index; the first four (the screen) span the range.
DEPTHS = (10, 50, 90, 30, 70, 20, 80, 40, 60, 15, 85, 50)
DOC_MARK = "{{DOCUMENT}}"
FORMAT = 'Answer only as JSON {"answer": ...}.'

_A = ["Ost", "Quill", "Marr", "Tal", "Vess", "Brin", "Hadr", "Corv", "Pell", "Ember", "Wyn", "Dray"]
_B = ["rel", "mere", "ow", "ick", "ane", "ford", "wick", "stow", "moor", "ley"]
_SUFFIX = ["Annex", "Yard", "Quay", "Point", "Wharf", "Gate"]
_PEOPLE = [
    "Mirelle Kessler",
    "Tobren Vance",
    "Selwyn Okoye",
    "Anja Brightwater",
    "Corvin Hale",
    "Otteline Marsh",
    "Roderic Quill",
    "Serafina Dorn",
    "Jasper Linde",
    "Wilhelmina Prowse",
    "Alaric Fenn",
    "Bettina Moss",
]
_WORDS = [
    "amber",
    "heron",
    "cedar",
    "falcon",
    "marble",
    "lantern",
    "willow",
    "copper",
    "ember",
    "gannet",
    "harbor",
    "juniper",
    "kestrel",
    "linen",
    "mallow",
    "nettle",
    "osprey",
    "pewter",
    "quartz",
    "russet",
    "saffron",
    "thistle",
    "umber",
    "velvet",
]
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
#: (asked item, near-name decoys) — no decoy contains the asked phrase.
_ITEM_FAMILIES = [
    ("tallow lamps", ["tallow lamp wicks", "brass lamps", "tallow candles"]),
    ("copper kettles", ["copper kettle lids", "iron kettles", "copper pans"]),
    ("rope coils", ["rope coil hooks", "chain coils", "rope ladders"]),
    ("salt barrels", ["salt barrel lids", "flour barrels", "salt sacks"]),
    ("glass floats", ["glass float nets", "cork floats", "glass buoys"]),
    ("wool blankets", ["wool blanket pins", "cotton blankets", "wool scarves"]),
    ("tin buckets", ["tin bucket handles", "zinc buckets", "tin funnels"]),
    ("oak planks", ["oak plank clamps", "pine planks", "oak beams"]),
    ("lamp oil drums", ["lamp oil drum taps", "paint drums", "lamp oil jugs"]),
    ("signal flags", ["signal flag poles", "signal rockets", "harbor flags"]),
    ("brass hinges", ["brass hinge screws", "iron hinges", "brass latches"]),
    ("sail needles", ["sail needle cases", "sail thread", "bone needles"]),
]
_GENERIC_ITEMS = [
    "rivet tins",
    "paint pots",
    "chalk boxes",
    "tarred twine",
    "cask staves",
    "net weights",
    "tool rolls",
    "wax blocks",
    "spare keys",
    "ledger books",
]


def _site(a: str, b: str, suffix: str, sector: int) -> str:
    return f"{a}{b} {suffix}, sector {sector}"


def _site_pool(r: random.Random, asked: tuple, decoys: int = 3) -> tuple[str, list[str]]:
    """(asked site name, shuffled other sites with the asked site's near-name decoys first)."""
    a, b, suf, sec = asked
    near = [
        _site(a, b, suf, sec + 1 if sec < 99 else sec - 1),
        _site(a, b, next(s for s in _SUFFIX if s != suf), sec),
        _site(a, next(x for x in _B if x != b), suf, sec),
    ][:decoys]
    asked_name = _site(a, b, suf, sec)
    grid = [(x, y, s, n) for x in _A for y in _B for s in _SUFFIX for n in range(10, 100)]
    rest = [_site(*g) for g in r.sample(grid, 6000)]
    rest = [s for s in dict.fromkeys(rest) if s != asked_name and s not in near]
    return asked_name, near + rest


def _date(r: random.Random) -> str:
    return f"2026-{r.randint(1, 9):02d}-{r.randint(1, 28):02d}"


def _code_pool(r: random.Random, count: int) -> list[str]:
    seen: set[str] = set()
    while len(seen) < count:
        seen.add(f"{r.choice(_WORDS)}-{r.choice(_WORDS)}-{r.randint(10, 99)}")
    return sorted(sorted(seen), key=lambda _: r.random())  # sorted first: set order is per-process


def _sections(entries: list[str], per: int, heading) -> str:
    out = []
    for i in range(0, len(entries), per):
        out.append(f"{heading(i // per + 1)}\n" + "\n".join(entries[i : i + per]))
    return "\n\n".join(out)


def _asked_site(r: random.Random) -> tuple:
    return (r.choice(_A), r.choice(_B), r.choice(_SUFFIX), r.randint(10, 99))


def _needle(spec: dict) -> tuple[str, dict]:
    r = random.Random(spec["seed"])
    target = int(spec["tokens"] * CHARS_PER_TOKEN[spec["kind"]])
    asked_t = _asked_site(r)
    asked, others = _site_pool(r, asked_t)
    codes = _code_pool(r, len(others) + 1)
    gold = codes.pop()

    def entry(i: int, site: str, code: str) -> str:
        return (
            f"Register entry {i:05d}: the vault at {site} uses the access code {code}, "
            f"last rotated {_date(r)} by {r.choice(_PEOPLE)}."
        )

    entries, total = [], 0
    while total < target:
        entries.append(entry(len(entries), others[len(entries) % len(others)], codes[len(entries)]))
        total += len(entries[-1]) + 1
    at = round(spec["depth"] / 100 * len(entries))
    entries.insert(at, entry(at, asked, gold))
    text = _sections(entries, 8, lambda k: f"Section {k} - district register")
    return text, {"site": asked, "gold": gold}


def _aggregation(spec: dict) -> tuple[str, dict]:
    r = random.Random(spec["seed"])
    target = int(spec["tokens"] * CHARS_PER_TOKEN[spec["kind"]])
    item, decoy_items = _ITEM_FAMILIES[spec["family"]]
    others = [
        i for fam, ds in _ITEM_FAMILIES for i in (*ds, *([fam] if fam != item else []))
    ] + _GENERIC_ITEMS
    sites = [f"{a}{b} {s}" for a in _A for b in _B for s in _SUFFIX]
    k = spec["k"]
    qtys = [r.randint(11, 96) for _ in range(k)]
    dates = sorted(
        r.sample([f"2026-{m:02d}-{d:02d}" for m in range(1, 10) for d in range(1, 29)], k)
    )
    r.shuffle(dates)  # the latest is not always the last one placed

    def entry(i: int, it: str, qty: int, date: str) -> str:
        return (
            f"On {date} the {r.choice(sites)} depot logged {qty} units of {it} "
            f"(entry {i:05d}), signed off by {r.choice(_PEOPLE)}."
        )

    # a decoy-heavy mix: every decoy of the asked item recurs throughout the log
    pool = decoy_items + others
    entries, total = [], 0
    while total < target:
        entries.append(entry(len(entries), r.choice(pool), r.randint(11, 96), _date(r)))
        total += len(entries[-1]) + 1
    slots = sorted(r.sample(range(len(entries)), k))
    for j, slot in enumerate(slots):
        entries[slot] = entry(slot, item, qtys[j], dates[j])
    text = _sections(entries, 8, lambda s: f"Ledger page {s}")
    return text, {
        "item": item,
        "sum": sum(qtys),
        "latest": max(dates),
        "count": k,
    }


def _quote(spec: dict) -> tuple[str, dict]:
    r = random.Random(spec["seed"])
    target = int(spec["tokens"] * CHARS_PER_TOKEN[spec["kind"]])
    asked_t = _asked_site(r)
    asked, others = _site_pool(r, asked_t)

    def closing(site: str) -> str:
        return (
            f"The {site} depot closes its loading dock at {r.randint(15, 21)}:{r.choice(['00', '15', '30', '45'])} "
            f"on {r.choice(_WEEKDAYS)}s."
        )

    def filler(site: str) -> str:
        return r.choice(
            [
                f"Inspector {r.choice(_PEOPLE)} visited the {site} depot on {_date(r)} and reported nothing unusual.",
                f"The {site} depot reopened its cold store on {_date(r)} after a routine check.",
                f"Staff at the {site} depot were reminded on {_date(r)} to log every lamp and rope delivery.",
            ]
        )

    sentence = closing(asked)
    paragraphs, total, i = [], 0, 0
    while total < target:
        sites = [others[(i + j) % len(others)] for j in range(5)]
        i += 5
        sents = [
            closing(sites[0]),
            filler(sites[1]),
            closing(sites[2]),
            filler(sites[3]),
            filler(sites[4]),
        ]
        par = " ".join(sents)
        paragraphs.append(par)
        total += len(par) + 2
    at = round(spec["depth"] / 100 * len(paragraphs))
    paragraphs.insert(at, " ".join([filler(others[-1]), sentence, filler(others[-2])]))
    text = "\n\n".join(paragraphs)
    return text, {"site": asked, "sentence": sentence}


_BUILDERS = {"needle": _needle, "aggregation": _aggregation, "quote": _quote}


@functools.lru_cache(maxsize=8)
def _cached(spec_json: str) -> tuple[str, dict]:
    spec = json.loads(spec_json)
    return _BUILDERS[spec["kind"]](spec)


def render_document(spec: dict) -> str:
    """The document for a task's doc_spec (everything but `generator` and `sha256` is input)."""
    key = {k: v for k, v in spec.items() if k not in ("generator", "sha256")}
    return _cached(json.dumps(key, sort_keys=True))[0]


def _facts(spec: dict) -> dict:
    key = {k: v for k, v in spec.items() if k not in ("generator", "sha256")}
    return _cached(json.dumps(key, sort_keys=True))[1]


# ------------------------------------------------------------------------ tasks


def _pattern(value: str) -> str:
    return rf'"answer"\s*:\s*"?{re.escape(value)}"?(?![\w.-])'


def _quote_pattern(sentence: str) -> str:
    return rf'"answer"\s*:\s*"{re.escape(sentence).replace(chr(92) + " ", r"\s+")}"'


def _spec(kind: str, n: int) -> dict:
    tier = TIERS[n % 3]
    base = {"generator": GENERATOR, "kind": kind, "seed": SEEDS[kind] + n, "tokens": tier}
    if kind == "aggregation":
        return {**base, "family": n, "k": 3 + (n // 2) % 3, "variant": (n // 3) % 3}
    return {**base, "depth": DEPTHS[n]}


def _question(kind: str, spec: dict, facts: dict) -> tuple[str, str, str, str]:
    """(question, answer text, answer pattern, wrong answer)."""
    if kind == "needle":
        return (
            f"What is the access code for the vault at {facts['site']}? Answer with the code "
            "exactly as written (lower case words joined by hyphens, then a number).",
            facts["gold"],
            _pattern(facts["gold"]),
            "amber-heron-00",
        )
    if kind == "quote":
        return (
            f"Quote exactly the one sentence that states when the {facts['site']} depot closes "
            "its loading dock. Answer with that sentence as written, including its final period.",
            facts["sentence"],
            _quote_pattern(facts["sentence"]),
            "The depot never closes its loading dock.",
        )
    item = facts["item"]
    scope = f"Count only log entries whose item is exactly '{item}'. "
    if spec["variant"] == 0:
        return (
            f"{scope}What is the total number of units logged across those entries? Answer with the number.",
            str(facts["sum"]),
            _pattern(str(facts["sum"])),
            str(facts["sum"] + 1),
        )
    if spec["variant"] == 1:
        return (
            f"{scope}What is the latest date among those entries? Answer as YYYY-MM-DD.",
            facts["latest"],
            _pattern(facts["latest"]),
            "2026-01-01",
        )
    return (
        f"{scope}How many such entries are there? Answer with the number.",
        str(facts["count"]),
        _pattern(str(facts["count"])),
        str(facts["count"] + 1),
    )


def _verify(kind: str, spec: dict, text: str, facts: dict, answer: str) -> None:
    """Re-derive the gold from the rendered text; raise on any disagreement."""
    if kind == "needle":
        hits = re.findall(
            rf"the vault at {re.escape(facts['site'])}(?!\d) uses the access code ([\w-]+),", text
        )
        ok = hits == [facts["gold"]]
    elif kind == "quote":
        ok = (
            text.count(facts["sentence"]) == 1
            and len(re.findall(re.escape(facts["site"]) + r"(?!\d)", text)) >= 1
        )
    else:
        rows = re.findall(
            rf"On (\S+) the .*? depot logged (\d+) units of {re.escape(facts['item'])} \(entry",
            text,
        )
        ok = (
            len(rows) == facts["count"]
            and sum(int(q) for _, q in rows) == facts["sum"]
            and max(d for d, _ in rows) == facts["latest"]
        )
    if not ok:
        raise RuntimeError(f"{kind}: the rendered document disagrees with the gold {answer!r}")


def build_task(kind: str, n: int) -> dict:
    spec = _spec(kind, n)
    text, facts = render_document(spec), _facts(spec)
    question, answer, pattern, wrong = _question(kind, spec, facts)
    _verify(kind, spec, text, facts, answer)
    spec = {**spec, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    depth = f"-d{spec['depth']}" if "depth" in spec else ""
    tid = f"lr-{kind}-{n:02d}-t{spec['tokens'] // 1000}k{depth}"
    return {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": False,
        "screen": n < SCREEN[kind],
        "instruction": (
            "Read the whole fictional document below, then answer the question that follows it.\n"
            f"--- fictional document ---\n{DOC_MARK}\n--- end of document ---\n"
            f"{question} {FORMAT}"
        ),
        "doc_spec": spec,
        "requires_tools": [],
        "checkers": [{"type": "answer_contains", "patterns": [pattern]}],
        "controls": {
            "pass": [{"answer": json.dumps({"answer": answer})}],
            "fail": [{"answer": json.dumps({"answer": wrong})}],
        },
        "no_tools": True,
    }


def build() -> list[dict]:
    tasks = [build_task(k, n) for k, count in COUNTS.items() for n in range(count)]
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    publish_text(OUT, "".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
