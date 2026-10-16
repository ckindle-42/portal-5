"""Is each documents task attainable through the tools auto-documents offers?

The controls gate proves grading works; it cannot prove the gold can be reached. A task is
attainable only when, on the live documents MCP under an evaluation scope (the way the
pipeline calls it):

  read / round trip   every deciding fact (DECIDING_FACTS in the suite generator) appears in the
                      output of the read_* tool called on the task's seeded fixture;
  create / round trip the reference call (REFERENCE_CALLS) is accepted, produces a file under
                      the row's out/ with a valid creation receipt, and the task's own checkers
                      (office_contains on the parsed file, tool_grounded on the call's output)
                      grade it PASS.

A task asking for something a tool cannot express fails here: fix or drop the task, never pass it.

    uv run python -m tests.wfe.e2e.documents_attainability            # live :8913
    uv run python -m tests.wfe.e2e.documents_attainability --json
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
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.runner import load_suite
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_documents_production as gen

SUITE = "tests/wfe/suites/documents_production.jsonl"
Caller = Callable[[str, dict, dict], str]


def call_documents(tool: str, args: dict, scope: dict) -> str:
    """One tool call on the documents MCP under `scope`, as the pipeline makes it."""
    req = urllib.request.Request(
        f"{eval_mode.DOCUMENTS_MCP_URL}/tools/{tool}",
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


def check_task(task: dict, call: Caller = call_documents) -> list[str]:
    """Failures for one task (empty = attainable)."""
    tid = task["id"]
    wsc = {"system_prompt_pipeline": "", "system_prompt_base": ""}
    h: dict = {}
    t, _, ctx = eval_mode.prepare(
        True,
        {"workspace": "auto-documents", "run_id": f"attain|{tid}"},
        {"campaign_id": "documents-attainability"},
        task,
        wsc,
        h,
    )
    scope, failures = h["pipeline_eval"], []
    try:
        if ctx.get("seed_error"):
            failures.append(f"fixture seeding failed: {ctx['seed_error']}")
        for fact in gen.DECIDING_FACTS.get(tid, []):
            out = flat(call(fact.tool, fact.args, scope))
            if not re.search(fact.pattern, out, re.I | re.S):
                failures.append(
                    f"fact not exposed: {fact.why} — {fact.tool} lacks /{fact.pattern}/"
                )
        if tid.startswith("doc-read") and not gen.DECIDING_FACTS.get(tid):
            failures.append("no deciding facts recorded")
        if tid in gen.REFERENCE_CALLS:
            tool, args = gen.REFERENCE_CALLS[tid]
            out = call(tool, args, scope)
            calls = [{"name": tool, "args": args, "output": out, "error": None}]
            # a round trip's read half: the real read call on the seeded fixture
            for r in (
                x for x in t["checkers"] if x["type"] == "tool_grounded" and tool not in x["tools"]
            ):
                rargs = {"file_path": next(iter(task["seed_b64"]))}
                calls.insert(
                    0,
                    {
                        "name": r["tools"][0],
                        "args": rargs,
                        "output": call(r["tools"][0], rargs, scope),
                        "error": None,
                    },
                )
            res = apply_checkers(t, CheckContext(task=t, tool_calls=calls))
            if res.outcome != Outcome.PASS:
                failures.append(
                    f"reference call {tool} does not satisfy the task: {res.notes[:200]}"
                )
    finally:
        eval_mode.cleanup(ctx, None, {"run_id": f"attain|{tid}"})
    return failures


def run(call: Caller = call_documents, only: set[str] | None = None) -> dict[str, list[str]]:
    gen.build()  # fills DECIDING_FACTS and REFERENCE_CALLS
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
