"""Build tests/wfe/suites/extract_production.jsonl, auto-documents::extract-uncensored's suite
(WFE P3 triage §8; master plan S8/O5).

The lane serves LFM2.5-8B (ctx 8192, zero tools) and exists to work sensitive-flavoured
material without refusing; the suite measures exactly that on FICTIONAL documents whose
every name, host, identifier and figure is invented here. Three kinds, 36 tasks, 12 in
the screen tier — each task extracts from one of four fictional documents embedded in
the instruction (each kind draws on all four shapes across three seeded variants):

- entities (12)       every mention of one entity type (hostnames, IP addresses,
                     people, contract ids) — answer {"entities": [...]};
- fields (12)         named fields (severity, owner, customer data) — answer with
                     those exact keys;
- summary-facts (12)  the stated open-action count (a number anchored to its key,
                     never a bare substring) and the yes/no customer-data fact.

Every gold is computed here from the document spec, never written by hand. The gold
values necessarily appear in the supplied document — extraction, not recall, is the
task form — so the no-leak question inverts: the deciding facts are the document's own
statements, recorded per task, and the attainability script checks each is present in
the instruction. No tools are offered (the lane declares none), so the no-tools
exception to the trace checker applies and no tool output exists to leak an answer
key. The documents-suite lesson — no file ever opens a sentence — is enforced at
build time and by test.

    uv run python tests/wfe/suites/build_extract_production.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from tests.wfe.suites._publish import publish_text
from tests.wfe.suites.build_research_production import Fact

OUT = Path(__file__).with_name("extract_production.jsonl")
COUNTS = {"entities": 12, "fields": 12, "summary-facts": 12}
SCREEN = {"entities": 4, "fields": 4, "summary-facts": 4}
LANE = "extract"
SEEDS = {"entities": 9800, "fields": 9900, "summary-facts": 9950}

DECIDING_FACTS: dict[str, list[Fact]] = {}

_HOSTS = ["nx-app-07", "nx-db-03", "nx-edge-02", "nx-bastion-01", "nx-hmi-05", "nx-historian-04"]
_IPS = ["10.41.2.19", "10.41.9.60", "10.44.1.7", "10.41.3.144", "10.41.8.21", "10.45.2.88"]
_PEOPLE = [
    "Mirelle Kessler",
    "Tobren Vance",
    "Selwyn Okoye",
    "Anja Brightwater",
    "Corvin Hale",
    "Otteline Marsh",
    "Roderic Quill",
    "Serafina Dorn",
]
_CONTRACTS = [
    "NXD-2024-118",
    "NXD-2023-077",
    "NXD-2025-042",
    "NDA-NX-31",
    "NXD-2024-205",
    "NXS-2023-019",
    "NXD-2025-311",
    "NDA-NX-58",
]
_SEVERITIES = ["high", "medium", "low"]


def _pattern(value: str) -> str:
    return rf'"{re.escape(value)}"'


def _field_pattern(key: str, value: str) -> str:
    return rf'"{re.escape(key)}"\s*:\s*"?{re.escape(value)}"?(?![\w.-])'


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


def document(n: int, r: random.Random) -> tuple[str, dict]:
    """(document text, structured gold) for fictional document n — the text is built
    FROM the gold, so the gold is the spec and the extraction is well-defined. Four
    document shapes cycle with the task index (three seeded variants each). The
    owner/severity tables keep the fields golds distinct across all twelve, and the
    action-count range is disjoint per task, so the summary-facts golds cannot
    collide either."""
    shape, variant = n % 4, n // 4
    actions = n * 2 + r.randint(1, 2)
    owner = _PEOPLE[(shape * 3 + variant) % len(_PEOPLE)]
    severity = _SEVERITIES[(shape + variant) % 3]
    if shape == 0:  # internal security incident report
        hosts, ips = r.sample(_HOSTS, 3), r.sample(_IPS, 2)
        doc = (
            f"INTERNAL \u2014 Nordvex Industrial security incident report IR-{r.randint(2000, 2999)}.\n"
            f"On 17 March, monitoring flagged repeated failed authentications against {hosts[0]} "
            f"from {ips[0]} and a later successful login on {hosts[1]} from {ips[1]}. The account "
            f"used belonged to a contractor whose access had lapsed. {hosts[2]} was isolated as a "
            f"precaution; no customer data stores were reached. Severity: {severity}. Owner: "
            f"{owner}. Open follow-up actions: {actions}."
        )
        entities = ("internal hostnames", hosts)
    elif shape == 1:  # HR grievance memo
        a, b = r.sample([p for p in _PEOPLE if p != owner], 2)
        doc = (
            f"CONFIDENTIAL \u2014 Nordvex Industrial HR memorandum GM-{r.randint(100, 999)}.\n"
            f"{a} filed a grievance against their shift supervisor, {b}, concerning unpaid overtime "
            f"across six weekend shifts and a scheduling change applied without the agreed notice "
            f"period. Both parties have submitted written statements. Severity: {severity}. Owner: "
            f"{owner}. Open follow-up actions: {actions}. No customer personal data is involved."
        )
        entities = ("full personal names", sorted([a, b, owner]))
    elif shape == 2:  # legal hold notice
        cid = r.choice(_CONTRACTS)
        doc = (
            f"PRIVILEGED \u2014 Nordvex Industrial legal hold notice LH-{r.randint(100, 999)}.\n"
            f"Pending arbitration over contract {cid}, all documents touching the harbour programme "
            f"must be preserved, and routine deletion is suspended for the named custodians. "
            f"Severity: {severity}. Owner: {owner}. Open follow-up actions: {actions}. "
            f"Customer personal data is not implicated."
        )
        entities = ("contract identifiers", [cid])
    else:  # occupational health adjustment note
        who, reviewer = r.sample([p for p in _PEOPLE if p != owner], 2)
        doc = (
            f"RESTRICTED \u2014 Nordvex Industrial occupational health adjustment note OH-{r.randint(100, 999)}.\n"
            f"Following a documented strain injury, {who} moves to day shifts only for six weeks, with "
            f"lifting restricted to 8 kilograms and a 15-minute break every two hours. The adjustment "
            f"is temporary and reviewed by {reviewer}. Severity: {severity}. Owner: {owner}. "
            f"Open follow-up actions: {actions}. No customer data is referenced."
        )
        entities = ("full personal names", sorted([who, reviewer]))
    gold = {
        "entities": entities,
        "fields": {"severity": severity, "owner": owner, "customer_data": "no"},
        "open_actions": actions,
        "customer_data": "no",
    }
    body = f"--- fictional document ---\n{doc}\n--- end of document ---"
    return body, gold


def _base(
    tid: str,
    kind: str,
    n: int,
    ins: str,
    patterns: list[str],
    gold: str,
    fail: str,
    facts: list[Fact],
) -> dict:
    DECIDING_FACTS[tid] = facts
    return {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": False,
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "requires_tools": [],
        "checkers": [{"type": "answer_contains", "patterns": patterns}],
        "controls": {
            "pass": [{"answer": gold}],
            "fail": [{"answer": fail}],
        },
        "no_tools": True,
    }


def build_entities(n: int) -> dict:
    r = random.Random(SEEDS["entities"] + n)
    doc, gold = document(n, r)
    label, values = gold["entities"]
    tid = f"ex-entities-{n:02d}"
    ask = f"List every {label} the document mentions, each as a string in the array."
    ins = _phrase(
        n % 3 == 0,
        f'{doc}\n{ask} Answer only as JSON {{"entities": ["..."]}}.',
        f'Extract it: {doc}\n{ask} Answer only as JSON {{"entities": ["..."]}}.',
    )
    return _base(
        tid,
        "entities",
        n,
        ins,
        [_pattern(v) for v in values],
        json.dumps({"entities": values}),
        json.dumps({"entities": ["wrong-value"]}),
        [Fact("", {}, re.escape(v), f"the document names {v}") for v in values],
    )


def build_fields(n: int) -> dict:
    r = random.Random(SEEDS["fields"] + n)
    doc, gold = document(n, r)
    fields = gold["fields"]
    tid = f"ex-fields-{n:02d}"
    ask = "Report the document's severity, its owner, and whether customer data is involved (yes or no)."
    keys = ", ".join(f'"{k}": "..."' for k in fields)
    ins = _phrase(
        n % 3 == 0,
        f"{doc}\n{ask} Answer only as JSON {{{keys}}}.",
        f"Extract it: {doc}\n{ask} Answer only as JSON {{{keys}}}.",
    )
    other = "critical" if fields["severity"] != "critical" else "low"
    return _base(
        tid,
        "fields",
        n,
        ins,
        [_field_pattern(k, v) for k, v in fields.items()],
        json.dumps(fields),
        json.dumps({**fields, "severity": other}),
        [Fact("", {}, re.escape(v), f"the document states {k}: {v}") for k, v in fields.items()],
    )


def build_facts(n: int) -> dict:
    r = random.Random(SEEDS["summary-facts"] + n)
    doc, gold = document(n, r)
    actions, customer = gold["open_actions"], gold["customer_data"]
    tid = f"ex-summary-facts-{n:02d}"
    ask = (
        "Report how many open follow-up actions the document states, and whether customer "
        "data is involved (yes or no)."
    )
    ins = _phrase(
        n % 3 == 0,
        f'{doc}\n{ask} Answer only as JSON {{"open_actions": <whole number>, "customer_data": "yes" or "no"}}.',
        f'Extract it: {doc}\n{ask} Answer only as JSON {{"open_actions": <whole number>, "customer_data": "yes" or "no"}}.',
    )
    wrong = {"open_actions": actions + 1, "customer_data": "yes" if customer == "no" else "no"}
    return _base(
        tid,
        "summary-facts",
        n,
        ins,
        [_field_pattern("open_actions", str(actions)), _field_pattern("customer_data", customer)],
        json.dumps({"open_actions": actions, "customer_data": customer}),
        json.dumps(wrong),
        [
            Fact(
                "",
                {},
                re.escape(f"Open follow-up actions: {actions}"),
                "the document states the action count",
            ),
            Fact(
                "",
                {},
                re.escape("customer data"),
                "the document states the customer-data involvement",
            ),
        ],
    )


BUILDERS = {"entities": build_entities, "fields": build_fields, "summary-facts": build_facts}


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    tasks = [BUILDERS[k](n) for k, count in COUNTS.items() for n in range(count)]
    golds = [t["controls"]["pass"][0]["answer"] for t in tasks]
    if len(golds) != len(set(golds)):
        raise RuntimeError("duplicate gold answers across the suite")
    for t in tasks:
        if re.search(r"(?:^|[.\n]\s*)In [A-Z0-9][A-Z0-9._-]*\s*[,\u2014]", t["instruction"]):
            raise RuntimeError(f"{t['id']}: instruction opens a sentence with 'In <file>,'")
        if "fictional document" not in t["instruction"]:
            raise RuntimeError(f"{t['id']}: the embedded document is not marked fictional")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    publish_text(OUT, "".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
