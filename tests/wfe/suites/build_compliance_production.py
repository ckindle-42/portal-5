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

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "portal" / "modules" / "compliance" / "data"
OUT = Path(__file__).with_name("compliance_production.jsonl")
LOOKUP_TOOLS = ["nerc_cip_requirement", "compliance_requirement", "compliance_read"]
LEAKS = ["expected_coverage", "control_class", r"<!--\s*PLANT"]
INTERVAL = re.compile(r"\b(\d+)\s+(calendar\s+(?:days|months)|days|months|minutes|hours)\b", re.I)
SCREEN_CLASSES = ("covered", "hole", "tier_conflict", "applicability")


def _q(key: str, value: str) -> str:
    return rf'"{key}"\s*:\s*"{re.escape(value)}"'


def determinations() -> list[dict]:
    out = []
    for f in sorted((DATA / "planted_corpus").glob("*.md")):
        plant = json.loads(
            re.search(r"<!--\s*PLANT\s+(\{.*?\})\s*-->", f.read_text(), re.S).group(1)
        )
        doc, req = plant["doc_id"], plant["targets"]
        cov, sig = plant.get("expected_coverage"), plant.get("expected_signal") or "NONE"
        gold = {
            "document": doc,
            "requirement": req,
            **({"coverage": cov} if cov else {}),
            "signal": sig,
        }
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
                "lane": "compliance",
                "agentic": True,
                "screen": plant["control_class"] in SCREEN_CLASSES,
                "instruction": (
                    f"Using the compliance tools, determine how fully the operator corpus document "
                    f"{doc} satisfies {req}. Coverage is one of FULL, PARTIAL, NONE or NOT_APPLICABLE; "
                    f"signal is one of NONE, COMPLIANCE_CONFLICT, STALE or NEEDS_REVIEW. Answer only as "
                    f'JSON with the keys "document", "requirement", "coverage" and "signal".'
                ),
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
    tasks.sort(key=lambda t: not t["screen"])  # the screen tier first
    OUT.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    print(
        f"wrote {OUT.relative_to(REPO)}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen"
    )


if __name__ == "__main__":
    main()
