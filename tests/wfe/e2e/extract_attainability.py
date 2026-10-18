"""Is each extract task answerable from the document the instruction embeds?

A no-tools family has no store to reach: the suite's deciding facts are the document's
own statements, so a task is attainable only when every one of them appears in the
instruction (the document arrived whole), every gold value is present in the embedded
document (the extraction is well-defined), the answer's JSON keys are named by the
instruction's format line, and the prompt plus the default 2048-token output budget
stay inside the 8k window. The live P-4 prompt-token measure is backlogged. Nothing
here touches the network.

    uv run python -m tests.wfe.e2e.extract_attainability            # offline
    uv run python -m tests.wfe.e2e.extract_attainability --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import yaml

from tests.wfe.runner import load_suite
from tests.wfe.suites import build_extract_production as gen

REPO = __import__("pathlib").Path(__file__).resolve().parents[3]
SUITE = "tests/wfe/suites/extract_production.jsonl"
WORKSPACE = "auto-extract-uncensored"


def _gold(task: dict) -> dict:
    return json.loads(task["controls"]["pass"][0]["answer"])


def check_task(task: dict, portal: dict, built: dict[str, dict]) -> list[str]:
    """Failures for one task (empty = attainable)."""
    tid, ins = task["id"], task["instruction"]
    failures = []
    facts = gen.DECIDING_FACTS.get(tid) or []
    if not facts:
        failures.append("no deciding facts recorded")
    for fact in facts:
        if not re.search(fact.pattern, ins, re.I | re.S):
            failures.append(f"fact not in the embedded document: {fact.why} lacks /{fact.pattern}/")
    gold = _gold(task)
    if built.get(tid) != gold:
        failures.append("gold drift: the suite's gold is not the generator's")
    # every extracted value must exist in the supplied document
    doc = ins.split("--- fictional document ---")[-1].split("--- end of document ---")[0]
    values = gold.get("entities") or list(gold.values())
    for v in values:
        if str(v) not in doc:
            failures.append(f"gold value absent from the embedded document: {v!r}")
    # the format line names the answer's keys
    for key in gold:
        if key not in ins:
            failures.append(f"the instruction's format line never names the key {key!r}")
    w = portal[WORKSPACE]
    limit = int(w.get("context_limit") or 0)
    prompt = (len(w.get("owui_system_prompt") or "") + len(ins)) / 4
    if prompt + 2048 > limit:
        failures.append(f"prompt ~{int(prompt)} tokens + output budget 2048 exceeds {limit}")
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
    portal = yaml.safe_load(open(f"{REPO}/config/portal.yaml"))["workspaces"]
    built = {t["id"]: json.loads(t["controls"]["pass"][0]["answer"]) for t in gen.build()}
    tasks = [t for t in load_suite(SUITE) if only is None or t["id"] in only]
    return {t["id"]: check_task(t, portal, built) for t in tasks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    res = run(only=set(a.only) if a.only else None)
    bad = {k: v for k, v in res.items() if v}
    if a.json:
        print(json.dumps({"tasks": len(res), "unattainable": bad}, indent=1))
    else:
        for tid, f in res.items():
            print(f"{'FAIL' if f else 'ok  '} {tid}")
            for x in f:
                print(f"       {x}")
        print(f"\n{len(res) - len(bad)}/{len(res)} attainable")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
