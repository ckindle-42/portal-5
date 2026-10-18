"""Is each tools-specialist task attainable through the lane's three tools?

The controls gate proves grading works; it cannot prove the gold can be reached. A
task is attainable only when, on the live MCPs under an evaluation scope (the way the
pipeline calls them), the deciding facts are exposed in order — a chain task's
remember must precede its recall in the same scope, so the facts are called in the
order DECIDING_FACTS records:

  execute_python  the reference code runs and prints the gold on stdout
                  ({success, stdout, ...} — code_sandbox_mcp.py:533-556);
  remember        the write is accepted ({id, stored: true, ...} — graph_memory.py:420);
  recall          the read-back carries the stored fact in its text
                  ({query, memories:[{text, ...}]} — graph_memory.py:423-468).

Memory isolation per row rides the eval scope (the sandbox's isolation is the
container); that the scope really keeps rows apart is unverified offline and
backlogged. check_task itself stays hermetic — the scope plumbing lives in run() —
so the offline unit test drives it with a stub caller and never touches the network.

    uv run python -m tests.wfe.e2e.tools_specialist_attainability            # live
    uv run python -m tests.wfe.e2e.tools_specialist_attainability --json
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
from tests.wfe.suites import build_tools_specialist_production as gen

SUITE = "tests/wfe/suites/tools_specialist_production.jsonl"
SANDBOX_MCP_URL = eval_mode.mcp_url("WFE_SANDBOX_MCP_URL", "SANDBOX_MCP_PORT", 8914)
Caller = Callable[[str, dict], str]
URLS = {
    "execute_python": lambda: SANDBOX_MCP_URL,
    "remember": lambda: eval_mode.MEMORY_MCP_URL,
    "recall": lambda: eval_mode.MEMORY_MCP_URL,
}


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


def check_task(task: dict, call: Caller) -> list[str]:
    """Failures for one task (empty = attainable). `call(tool, args)` keeps one eval
    scope across the calls; facts run in DECIDING_FACTS order."""
    gen.build()  # fills DECIDING_FACTS
    tid = task["id"]
    facts = gen.DECIDING_FACTS.get(tid) or []
    if not facts:
        return ["no deciding facts recorded"]
    failures = []
    for fact in facts:
        out = flat(call(fact.tool, fact.args))
        if not re.search(fact.pattern, out, re.I | re.S):
            failures.append(f"fact not exposed: {fact.why} — {fact.tool} lacks /{fact.pattern}/")
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
    gen.build()  # fills DECIDING_FACTS
    tasks = [t for t in load_suite(SUITE) if only is None or t["id"] in only]
    out = {}
    for t in tasks:
        h: dict = {}
        _, _, ctx = eval_mode.prepare(
            True,
            {"workspace": "tools-specialist", "run_id": f"attain|{t['id']}"},
            {"campaign_id": "tools-specialist-attainability"},
            t,
            {"system_prompt_pipeline": "", "system_prompt_base": ""},
            h,
        )
        scope, failures = h["pipeline_eval"], []
        try:
            if ctx.get("seed_error"):
                failures.append(f"seeding failed: {ctx['seed_error']}")
            failures.extend(
                check_task(t, lambda tool, args, scope=scope: call_tool(tool, args, scope))
            )
        finally:
            eval_mode.cleanup(ctx, None, {"run_id": f"attain|{t['id']}"})
        out[t["id"]] = failures
    return out


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
