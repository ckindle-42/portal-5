"""Is each CAD task attainable through the tools auto-coding::cad offers?

The controls gate proves grading works; it cannot prove the gold can be reached. A
task is attainable only when, on the live CAD MCP (:8926) with one engine session per
task (the session is the request id — b123d_bridge.session_handle, :181):

  cad_build      the reference build123d script (the generator's DECIDING_FACTS carry
                 it) validates — `ok: true`;
  cad_measure    the measured volume shows the spec geometry's whole-number part with
                 a decimal fraction — the same digit the answer is graded on.

Unlike the research check this stays out of eval_mode.prepare: the CAD MCP keeps no
user-store scope (isolation is the per-request engine session), so there is nothing to
seed and nothing to clean up — the request id IS the row boundary. Written for the
live gate only (O2: the CAD engine is live-only); it is NOT run from the offline lane
and makes no call unless invoked:

    uv run python -m tests.wfe.e2e.cad_attainability            # live
    uv run python -m tests.wfe.e2e.cad_attainability --json
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
from tests.wfe.suites import build_cad_production as gen

SUITE = "tests/wfe/suites/cad_production.jsonl"
CAD_MCP_URL = eval_mode.mcp_url("WFE_CAD_MCP_URL", "CAD_RENDER_HOST_PORT", 8926)
Caller = Callable[[str, dict], str]


def call_tool(tool: str, args: dict, request_id: str) -> str:
    """One CAD tool call the way the pipeline makes it: the session is the request id."""
    req = urllib.request.Request(
        f"{CAD_MCP_URL}/tools/{tool}",
        data=json.dumps({"arguments": args, "request_id": request_id}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:300]}"


def flat(raw: str) -> str:
    return re.sub(r"(?:\\n|\\t|\s)+", " ", raw)


def check_task(task: dict, call: Caller) -> list[str]:
    """Failures for one task (empty = attainable). `call(tool, args)` must keep one
    engine session across the calls — the live caller bakes the request id in; the
    offline unit passes a stub that replays the declared control trace."""
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
        rid = f"wfe-cad-attain|{t['id']}"
        out[t["id"]] = check_task(t, lambda tool, args, rid=rid: call_tool(tool, args, rid))
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
