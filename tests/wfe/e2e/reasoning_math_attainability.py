"""Is each reasoning/math task answerable from what the instruction states?

The reasoning/math workspaces offer zero tools (WFE P3 triage §2), so — unlike the
research, general and documents checks — there is no MCP store to reach and this
script makes no network call. A task is attainable only when:

  self-contained  every deciding fact (DECIDING_FACTS in the suite generator: the
                  problem's givens and the logic-grid clues) appears in the
                  instruction — a missing given means the gold is not determined;
  gold-private    the gold is never stated in the instruction (a computed value must
                  not appear at all; a logic-grid runner's name may appear in the
                  roster, but never bound to the asked position);
  recomputable    the generator, re-run, computes the same gold the committed suite
                  carries;
  fits the window the prompt (workspace system prompt + instruction) plus the hard
                  output cap (predict_limit, tests/wfe/runner.py:1278) stays inside
                  context_limit, so a long reasoning chain cannot overflow the seat.

What this cannot prove offline is the seats' real prompt-token count (P-4): the
served system prompt and chat template are the live executor's measure, backlogged
in coding_task/WFE_LIVE_BACKLOG.md.

    uv run python -m tests.wfe.e2e.reasoning_math_attainability            # offline
    uv run python -m tests.wfe.e2e.reasoning_math_attainability --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from portal.platform.inference.config import effective_workspace
from tests.wfe.runner import load_suite
from tests.wfe.suites import build_reasoning_math_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = "tests/wfe/suites/reasoning_math_production.jsonl"
WORKSPACES = ("auto-reasoning", "auto-reasoning::math")


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def _window_failures(task: dict, portal: dict) -> list[str]:
    out = []
    for ws in WORKSPACES:
        w = effective_workspace(portal, ws)
        prompt_tokens = (len(w.get("owui_system_prompt") or "") + len(task["instruction"])) / 4
        cap = int(w.get("predict_limit") or 0)
        limit = int(w.get("context_limit") or 0)
        if not cap or not limit:
            out.append(f"{ws}: predict_limit/context_limit missing in portal.yaml")
        elif prompt_tokens + cap > limit:
            out.append(
                f"{ws}: prompt ~{int(prompt_tokens)} tokens + output cap {cap} "
                f"exceeds context_limit {limit}"
            )
    return out


def check_task(task: dict, portal: dict, built: dict[str, str]) -> list[str]:
    """Failures for one task (empty = attainable)."""
    tid, ins = task["id"], task["instruction"]
    failures = []
    facts = gen.DECIDING_FACTS.get(tid) or []
    if not facts:
        failures.append("no deciding facts recorded")
    for fact in facts:
        if not re.search(fact.pattern, ins):
            failures.append(f"given not stated: {fact.why} — instruction lacks /{fact.pattern}/")
    if leak := gen._leaks(task):
        failures.append(f"gold not private: {leak}")
    if tid in built and built[tid] != _gold(task):
        failures.append(f"gold drift: suite {_gold(task)} != generator {built[tid]}")
    failures.extend(_window_failures(task, portal))
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
    gen.build()  # fills DECIDING_FACTS
    portal = yaml.safe_load(open(f"{REPO}/config/portal.yaml"))["workspaces"]
    built = {t["id"]: json.loads(t["controls"]["pass"][0]["answer"])["answer"] for t in gen.build()}
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
