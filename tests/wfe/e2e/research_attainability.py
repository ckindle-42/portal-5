"""Is each research task attainable through the tools auto-research offers?

The controls gate proves grading works; it cannot prove the gold can be reached. A task is
attainable only when, on the live RAG and memory MCPs under an evaluation scope (the way the
pipeline calls them), after the task's own kb_seed / memory_seed are written:

  every deciding fact (DECIDING_FACTS in the suite generator) appears in the output of the
  tool call named for it, with a query built from the instruction's own wording;
  an absent task's entity appears in neither store (its facts are marked `absent`).

A fact the retriever cannot surface for a reasonable query means the task is fixed or dropped,
never passed. Written to run through the eval scope; it needs the live stack (:8920, :8921).

    uv run python -m tests.wfe.e2e.research_attainability            # live
    uv run python -m tests.wfe.e2e.research_attainability --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

from tests.wfe import eval_mode
from tests.wfe.runner import load_suite
from tests.wfe.suites import build_research_production as gen

SUITE = "tests/wfe/suites/research_production.jsonl"
Caller = Callable[[str, dict, dict], str]
URLS = {"kb_search_all": lambda: eval_mode.RAG_MCP_URL, "recall": lambda: eval_mode.MEMORY_MCP_URL}


def call_tool(tool: str, args: dict, scope: dict) -> str:
    """One tool call under `scope`, as the pipeline makes it."""
    req = urllib.request.Request(
        f"{URLS[tool]()}/tools/{tool}",
        data=json.dumps({"arguments": args, "eval": scope}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:300]}"


def flat(raw: str) -> str:
    return re.sub(r"(?:\\n|\\t|\s)+", " ", raw)


def check_task(task: dict, call: Caller = call_tool) -> list[str]:
    """Failures for one task (empty = attainable)."""
    tid = task["id"]
    h: dict = {}
    t, _, ctx = eval_mode.prepare(
        True,
        {"workspace": "auto-research", "run_id": f"attain|{tid}"},
        {"campaign_id": "research-attainability"},
        task,
        {"system_prompt_pipeline": "", "system_prompt_base": ""},
        h,
    )
    scope, failures = h["pipeline_eval"], []
    try:
        if ctx.get("seed_error"):
            failures.append(f"seeding failed: {ctx['seed_error']}")
        facts = gen.DECIDING_FACTS.get(tid) or []
        if not facts:
            failures.append("no deciding facts recorded")
        for fact in facts:
            out = flat(call(fact.tool, fact.args, scope))
            found = bool(re.search(fact.pattern, out, re.I | re.S))
            if fact.absent and found:
                failures.append(f"decoy reachable: {fact.why} — {fact.tool} shows /{fact.pattern}/")
            elif not fact.absent and not found:
                failures.append(
                    f"fact not exposed: {fact.why} — {fact.tool} lacks /{fact.pattern}/"
                )
    finally:
        eval_mode.cleanup(ctx, None, {"run_id": f"attain|{tid}"})
    return failures


def run(call: Caller = call_tool, only: set[str] | None = None) -> dict[str, list[str]]:
    gen.build()  # fills DECIDING_FACTS
    tasks = [t for t in load_suite(SUITE) if only is None or t["id"] in only]
    return {t["id"]: check_task(t, call) for t in tasks}


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
