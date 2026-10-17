"""Build tests/wfe/suites/compliance_production.jsonl, auto-compliance's production suite.

Every gold answer is fixed by committed, public material, never by operator data:
- 12 determinations, one per planted-corpus document. The gold is the document's own
  `<!-- PLANT -->` answer key; the evaluation instance ingests the corpus with those
  headers stripped (N-32), and every determination forbids them in tool output.
- 24 register lookups: requirement parts whose verbatim text sets exactly one interval,
  chosen so the intervals differ (a model cannot pass by guessing the common one).
Every task is graded twice: the answer (answer_contains) and where it came from
(tool_grounded: a successful workspace-tool call whose output shows the fact).

    uv run python tests/wfe/suites/build_compliance_production.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "portal" / "modules" / "compliance" / "data"
OUT = Path(__file__).with_name("compliance_production.jsonl")
LOOKUP_TOOLS = ["nerc_cip_requirement", "compliance_requirement", "compliance_read"]
LEAKS = ["expected_coverage", "control_class", r"<!--\s*PLANT"]
INTERVAL = re.compile(r"\b(\d+)\s+(calendar\s+(?:days|months)|days|months|minutes|hours)\b", re.I)
SCREEN_CLASSES = ("covered", "hole", "tier_conflict", "applicability")
#: A control class whose gold only exists at a stated date. The corpus header carries
#: `as_of_effective` as the answer key's context, but the task never said so, so a model
#: working today could not reach the gold: the instruction now names the date.
AS_OF = {"future_effective": "2024-01-01"}  # test_compliance_planted: CIP-013-2 starts 2024-04-01


#: What each answer value means, in the engine's own words, so the instruction defines what it
#: enumerates. Undefined, NEEDS_REVIEW read as "there are no recorded links, so it needs review"
#: and the task measured that ambiguity instead of the model (Phase C r2: det 1/16, with the
#: wrong signal NEEDS_REVIEW on almost every row).
#:   coverage.py   FULL/PARTIAL/NONE/NOT_APPLICABLE are the cell's coverage; `applies` False is
#:                 NOT_APPLICABLE; a span that only names the requirement is not "substantive
#:                 overlap"; text_signals.is_aspirational: "names an intent, not an auditable
#:                 obligation"; _stale_citations: "cites a superseded standard id".
#:   tiers.py      "the standard says 15 calendar months, the procedure says 18" is a
#:                 COMPLIANCE_CONFLICT, never reconciled; coverage.py: a duration/modal mismatch.
#:   test_compliance_planted: future-effective is "not a 'today' gap"; an implicit change "must
#:                 land NEEDS_REVIEW" (approved against the old text of a Part that changed).
COVERAGE_VALUES = {
    "FULL": "the document's own operative language satisfies what the requirement requires",
    "PARTIAL": "the document addresses the requirement but a stated duration or obligation differs "
    "from it",
    "NONE": "no part of the document substantively addresses the requirement (it only names it, "
    "states an intent or hedge with no auditable obligation such as 'strives to', 'encouraged to' or "
    "'where practical', or covers a different obligation), or the "
    "requirement is not yet in force on the stated date",
    "NOT_APPLICABLE": "the requirement does not apply to the systems the document covers",
}
SIGNAL_VALUES = {
    "NONE": "no conflict, stale citation or change indicator applies",
    "COMPLIANCE_CONFLICT": "the document and the requirement make conflicting normative or "
    "quantitative claims about the same obligation (a differing duration, or should against shall)",
    "STALE": "the document cites a superseded version of the standard by its exact id",
    "NEEDS_REVIEW": "the requirement's text changed between versions and the document was "
    "approved against the older text and not re-reviewed",
}
LINKS_NOTE = (
    "The store holds no recorded or approved links between documents and requirements; their "
    "absence is expected and is not itself a signal. Judge from the document text and the "
    "requirement text."
)


def _defs(values: dict[str, str]) -> str:
    return "; ".join(f"{k} = {v}" for k, v in values.items())


def determination_instruction(doc: str, req: str, as_of: str) -> str:
    return (
        f"Using the compliance tools, determine how fully the operator corpus document {doc} "
        f"satisfies {req}{as_of}. Coverage is one of {', '.join(COVERAGE_VALUES)}: "
        f"{_defs(COVERAGE_VALUES)}. Signal is one of {', '.join(SIGNAL_VALUES)}: "
        f"{_defs(SIGNAL_VALUES)}. {LINKS_NOTE} Answer only as JSON with the keys "
        '"document", "requirement", "coverage" and "signal".'
    )


def undefined_values(instruction: str) -> list[str]:
    """Enumerated answer values (`... is one of A, B, C: ...`) with no `A = definition` in the
    text that follows their own list. The suite refuses to build while any exist."""
    missing = []
    lists = list(re.finditer(r"is one of ((?:[A-Z][A-Z_]+(?:, )?)+)[:.]", instruction))
    for n, m in enumerate(lists):
        end = lists[n + 1].start() if n + 1 < len(lists) else len(instruction)
        body = instruction[m.end() - 1 : end]
        for value in m.group(1).split(", "):
            if not re.search(rf"(?:^|[:;] ){re.escape(value)} = \S", body):
                missing.append(value)
    return missing


class Fact(NamedTuple):
    """One fact the gold depends on, and the offered tool call that must expose it.

    `pattern` is matched against the tool's output with JSON escapes and whitespace
    collapsed to single spaces. A fact that exists only in the PLANT header (the answer
    key) or in data no tool returns makes the task unattainable: the attainability check
    (tests/wfe/e2e/compliance_attainability.py) fails on it. Never pass it, never loosen it."""

    tool: str
    args: dict
    pattern: str
    why: str


def _doc(doc: str, pattern: str, why: str) -> Fact:
    return Fact("compliance_read", {"ref": doc}, pattern, why)


def _req(req: str, pattern: str, why: str, **extra) -> Fact:
    return Fact("nerc_cip_requirement", {"req_id": req, **extra}, pattern, why)


#: The deciding facts per determination, keyed by the planted document id. They are the inputs
#: tests/unit/test_compliance_planted.py and the engine use to derive each gold, by control class.
DECIDING_FACTS: dict[str, list[Fact]] = {
    # covered: the document's operative language and the Part's normative interval agree
    "OT-POL-007": [
        _doc(
            "OT-POL-007",
            r"shall evaluate security patches .{0,80}every 35 calendar days",
            "policy states the 35-day duty",
        ),
        _req(
            "CIP-007-6 R2 Part 2.2",
            r"at least once every 35 calendar days",
            "Part 2.2 sets 35 calendar days",
        ),
    ],
    "OT-PROC-007": [
        _doc(
            "OT-PROC-007",
            r"Every 35 calendar days .{0,40}pulls the list of security patches",
            "procedure performs the 35-day evaluation",
        ),
        _req(
            "CIP-007-6 R2 Part 2.2",
            r"at least once every 35 calendar days",
            "Part 2.2 sets 35 calendar days",
        ),
    ],
    # hole: the document says nothing about installing patches; Part 2.3 requires it
    "OT-POL-007b": [
        _doc(
            "OT-POL-007b",
            r"Backups shall be tested annually",
            "the document's only operative language is about backups",
        ),
        _req(
            "CIP-007-6 R2 Part 2.3",
            r"Apply the applicable patches",
            "Part 2.3 requires applying patches",
        ),
    ],
    # aspirational: hortatory words, no shall
    "OT-POL-004": [
        _doc(
            "OT-POL-004",
            r"strives to provide .{0,80}endeavors to keep .{0,80}encouraged to complete",
            "aspirational wording, no obligation",
        ),
        _req("CIP-004-7 R2 Part 2.1", r"Training content on", "Part 2.1 requires training content"),
    ],
    # lexical: the document only names the requirement, with no operative language of its own
    "OT-POL-005": [
        _doc(
            "OT-POL-005",
            r"addresses CIP-005-7 R1 Part 1\.1\. Refer to the network architecture drawings",
            "only a citation and a pointer",
        ),
        _req(
            "CIP-005-7 R1 Part 1.1",
            r"shall reside within a defined ESP",
            "Part 1.1 requires an ESP",
        ),
    ],
    # tier conflict: a procedure-tier document sets 18 months; the standard says 15 calendar months
    "OT-PROC-003": [
        _doc("OT-PROC-003", r"at least once every 18 months", "procedure sets 18 months"),
        _doc("OT-PROC-003", r'"authority_tier": ?"3"', "the document's tier is the procedure tier"),
        _req(
            "CIP-003-9 R1", r"at least once every 15 calendar months", "R1 sets 15 calendar months"
        ),
    ],
    # deontic: "should ... where practical" against a mandatory Part
    "OT-POL-012": [
        _doc("OT-POL-012", r"should protect .{0,120}where practical", "advisory modality"),
        _req(
            "CIP-012-2 R1 Part 1.1",
            r"Identification of method\(s\) used to mitigate the risk",
            "Part 1.1 is a mandatory identification",
        ),
    ],
    # applicability: the Part's applicable systems against the systems the document covers
    "OT-POL-006": [
        _doc(
            "OT-POL-006",
            r"Medium Impact BES Cyber Systems with External Routable Connectivity and their associated PACS",
            "the document's stated scope",
        ),
        _req(
            "CIP-006-6 R1 Part 1.2",
            r"Medium Impact BES Cyber Systems with External Routable Connectivity and their associated: 1\. EACMS; and 2\. PCA",
            "the Part's applicable systems",
        ),
    ],
    # temporal: the document cites CIP-003-8, which the register records as superseded
    "OT-POL-003old": [
        _doc(
            "OT-POL-003old",
            r"implements CIP-003-8 Attachment 1",
            "the document cites the retired version",
        ),
        _req(
            "CIP-003-9 R2",
            r'"version":\s*"8".{0,200}"as_known":\s*"SUPERSEDED_OR_RETIRED"',
            "CIP-003-8 is superseded or retired",
        ),
    ],
    # future effective: as of 2024-01-01 the revision that holds the Part is not yet in force
    "OT-POL-013fe": [
        _doc(
            "OT-POL-013fe",
            r"One or more processes, used in planning for the procurement",
            "the document restates Part 1.1",
        ),
        _req(
            "CIP-013-2 R1 Part 1.1",
            r'"future":\s*\[\{"family":\s*"CIP-013",\s*"version":\s*"2".{0,120}"valid_from":\s*"2024-04-01".{0,120}"as_known":\s*"FUTURE"',
            "the revision's effective date is after the as-of date",
            valid_at="2024-01-01",
        ),
    ],
    # implicit change: approved against the previous version's topic list; this Part is new in -9
    "OT-POL-003ic": [
        _doc(
            "OT-POL-003ic",
            r"against the CIP-003-8 topic list and has not been re-reviewed",
            "approved under the earlier version",
        ),
        _req(
            "CIP-003-9 R1 Part 1.2.6",
            r"Vendor electronic remote access security controls",
            "Part 1.2.6 is the added topic",
        ),
        _req(
            "CIP-003-9 R1 Part 1.2.6",
            r'"version":\s*"8".{0,200}"as_known":\s*"SUPERSEDED_OR_RETIRED"',
            "CIP-003-8 is the superseded revision",
        ),
    ],
    # cross reference: the referenced program document does not exist in the corpus
    "OT-POL-003xref": [
        _doc(
            "OT-POL-003xref",
            r"refer to our CIP-004 program documentation",
            "the document defers to another document",
        ),
        _req(
            "CIP-003-9 R1 Part 1.1.1",
            r"Personnel and training \(CIP.?004\)",
            "the Part names the topic",
        ),
        Fact(
            "compliance_read",
            {"ref": "CIP-004 program documentation"},
            r'"resolved": ?false',
            "the referenced document is not resolvable",
        ),
    ],
}


def _q(key: str, value: str) -> str:
    return rf'"{key}"\s*:\s*"{re.escape(value)}"'


def _plants() -> list[dict]:
    return [
        json.loads(re.search(r"<!--\s*PLANT\s+(\{.*?\})\s*-->", f.read_text(), re.S).group(1))
        for f in sorted((DATA / "planted_corpus").glob("*.md"))
    ]


def determination_targets() -> list[dict]:
    """The document and requirement each determination names (what the task text says)."""
    return [{"doc": p["doc_id"], "req": p["targets"]} for p in _plants()]


def determinations() -> list[dict]:
    out = []
    for plant in _plants():
        doc, req = plant["doc_id"], plant["targets"]
        cov, sig = plant.get("expected_coverage"), plant.get("expected_signal") or "NONE"
        gold = {
            "document": doc,
            "requirement": req,
            **({"coverage": cov} if cov else {}),
            "signal": sig,
        }
        as_of = f" as of {AS_OF[plant['control_class']]}" if plant["control_class"] in AS_OF else ""
        here = rf"{re.escape(doc)}(?![A-Za-z0-9])"
        trace = [
            {
                "name": "compliance_read",
                "args": {"ref": doc},
                "output": f"# {doc} ...",
                "error": None,
            }
        ]
        wrong = {
            **gold,
            **({"coverage": "FULL" if cov != "FULL" else "NONE"} if cov else {"signal": "NONE"}),
        }
        out.append(
            {
                "id": f"comp-prod-det-{plant['control_class'].replace('_', '-')}-{doc.lower()}",
                "kind": "determination",
                "lane": "compliance",
                "agentic": True,
                "screen": plant["control_class"] in SCREEN_CLASSES,
                "instruction": determination_instruction(doc, req, as_of),
                "requires_tools": ["compliance_read"],
                "checkers": [
                    {
                        "type": "answer_contains",
                        "patterns": ([_q("coverage", cov)] if cov else []) + [_q("signal", sig)],
                        "forbid_in_tool_output": LEAKS,
                    },
                    {"type": "tool_grounded", "evidence": [here]},
                ],
                "controls": {
                    "pass": [{"answer": json.dumps(gold), "tool_calls": trace}],
                    "fail": [json.dumps(gold), {"answer": json.dumps(wrong), "tool_calls": trace}],
                },
            }
        )
    return out


def lookups(n: int = 24) -> list[dict]:
    nodes = json.loads((DATA / "nerc_cip_register.json").read_text())["nodes"]
    pool = []
    for node in nodes:
        if node.get("lifecycle_state") != "EFFECTIVE" or not node.get("verbatim_text"):
            continue
        hits = {(m.group(1), m.group(2).lower()) for m in INTERVAL.finditer(node["verbatim_text"])}
        if len(hits) == 1:
            pool.append((node, *next(iter(hits))))
    seen: dict[tuple, int] = {}
    pool.sort(key=lambda t: (t[0]["standard"], t[0]["id"]))
    chosen = []
    for rnd in range(4):  # rarest intervals first, then fill, at most 3 per standard
        for node, num, unit in pool:
            per_std = sum(c[0]["standard"] == node["standard"] for c in chosen)
            if node in [c[0] for c in chosen] or per_std >= 3 or seen.get((num, unit), 0) > rnd:
                continue
            chosen.append((node, num, unit))
            seen[(num, unit)] = seen.get((num, unit), 0) + 1
            if len(chosen) == n:
                break
        if len(chosen) == n:
            break
    out = []
    others = sorted({(num, unit) for _, num, unit in pool})
    for i, (node, num, unit) in enumerate(chosen):
        rid, word = node["id"], unit.split()[-1]
        gold = {"requirement": rid, "interval": f"{num} {unit}"}
        wnum, wunit = next(o for o in others if o[0] != num)
        trace = [
            {
                "name": "nerc_cip_requirement",
                "args": {"req_id": rid},
                "output": json.dumps(
                    {"parts": [{"id": rid, "verbatim_text": node["verbatim_text"]}]}
                ),
                "error": None,
            }
        ]
        out.append(
            {
                "id": "comp-prod-lookup-" + re.sub(r"[^a-z0-9]+", "-", rid.lower()).strip("-"),
                "kind": "lookup",
                "lane": "compliance",
                "agentic": True,
                "screen": i < 6,
                "instruction": (
                    f"Using the compliance tools, look up {rid} and state the time interval it sets. "
                    f'Answer only as JSON with the keys "requirement" and "interval".'
                ),
                "requires_tools": ["nerc_cip_requirement"],
                "checkers": [
                    {
                        "type": "answer_contains",
                        "patterns": [rf'"interval"\s*:\s*"[^"]*\b{num}\b[^"]*{word}'],
                    },
                    {
                        "type": "tool_grounded",
                        "tools": LOOKUP_TOOLS,
                        "evidence": [re.escape(rid), rf"\b{num}\s+{re.escape(unit)}\b"],
                    },
                ],
                "controls": {
                    "pass": [{"answer": json.dumps(gold), "tool_calls": trace}],
                    "fail": [
                        json.dumps(gold),
                        {
                            "answer": json.dumps({**gold, "interval": f"{wnum} {wunit}"}),
                            "tool_calls": trace,
                        },
                    ],
                },
            }
        )
    return out


def main() -> None:
    tasks = determinations() + lookups()
    for t in tasks:
        if missing := undefined_values(t["instruction"]):
            raise SystemExit(f"{t['id']}: answer values used but not defined: {missing}")
    tasks.sort(key=lambda t: not t["screen"])  # the screen tier first
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(
        f"wrote {OUT.relative_to(REPO)}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen"
    )


if __name__ == "__main__":
    main()
