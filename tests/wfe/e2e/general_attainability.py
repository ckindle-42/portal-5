"""Is each general task attainable through the tools the general workspaces offer?

The controls gate proves grading works; it cannot prove the gold can be reached. A task is
attainable only when, on the live MCPs under an evaluation scope (the way the pipeline calls
them), after the task's own kb_seed / memory_seed are written:

  python     the reference code, run through execute_python on the sandbox, prints the gold;
  memory     recall, asked with the instruction's own wording, returns the seeded note;
  kb         kb_search returns the seeded document;
  document   the documents slice's own check (read facts exposed; the reference create call
             is accepted and satisfies the task's checkers);
  notool     nothing to reach (answer-graded only).

An unreachable fact means the task is fixed or dropped, never passed. Written to run through
the eval scope; it needs the live stack (:8913, :8914, :8920, :8921).

    uv run python -m tests.wfe.e2e.general_attainability            # live
    uv run python -m tests.wfe.e2e.general_attainability --json
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
from tests.wfe.e2e import documents_attainability as doc_att
from tests.wfe.runner import load_suite
from tests.wfe.suites import build_documents_production as docs
from tests.wfe.suites import build_general_production as gen

SUITE = "tests/wfe/suites/general_production.jsonl"
SANDBOX_MCP_URL = eval_mode.mcp_url("WFE_SANDBOX_MCP_URL", "SANDBOX_MCP_PORT", 8914)
Caller = Callable[[str, dict, dict], str]


def _url(tool: str) -> str:
    base = {
        "execute_python": SANDBOX_MCP_URL,
        "recall": eval_mode.MEMORY_MCP_URL,
        "kb_search": eval_mode.RAG_MCP_URL,
    }[tool]
    return f"{base}/tools/{tool}"


def call_tool(tool: str, args: dict, scope: dict) -> str:
    """One tool call under `scope`, as the pipeline makes it."""
    req = urllib.request.Request(
        _url(tool),
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
    if task["kind"] == "document":
        source = gen.DOC_SOURCE[int(tid.rsplit("-", 1)[1])]
        original = next(t for t in docs.build() if t["id"] == source)
        return doc_att.check_task(original)
    if task["kind"] == "notool":
        return []
    h: dict = {}
    _, _, ctx = eval_mode.prepare(
        True,
        {"workspace": "auto-daily::fast", "run_id": f"attain|{tid}"},
        {"campaign_id": "general-attainability"},
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
            if not re.search(fact.pattern, out, re.I | re.S):
                failures.append(
                    f"fact not exposed: {fact.why} — {fact.tool} lacks /{fact.pattern}/"
                )
    finally:
        eval_mode.cleanup(ctx, None, {"run_id": f"attain|{tid}"})
    return failures


def run(call: Caller = call_tool, only: set[str] | None = None) -> dict[str, list[str]]:
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
