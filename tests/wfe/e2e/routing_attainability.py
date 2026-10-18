"""Is each routing task clear-cut, and is the router's own few-shot file kept out?

The routing family offers no tools. For scored tasks, attainability proves that the
REAL Layer 2 keyword scorer (router/routing.py:_detect_workspace, the production
fallback) resolves each prompt to its gold workspace offline. The classifier-only
creative and research tasks have no matching Layer-2 keyword tables, so only their
live rows can measure Layer-1 classification. The harmful-intent gate stays cold on
every prompt (a trip would reroute the row to auto-daily); no prompt names any
workspace id or shares a five-word sequence with routing_examples.json — the
router's own few-shot prompt, which would leak the task; and each prompt plus the
default output budget fits the 8k window. Nothing here touches the network.

    uv run python -m tests.wfe.e2e.routing_attainability            # offline
    uv run python -m tests.wfe.e2e.routing_attainability --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from tests.wfe.runner import load_suite
from tests.wfe.suites import build_routing_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = "tests/wfe/suites/routing_production.jsonl"
WORKSPACE = "auto"


def check_task(task: dict, portal: dict, example_shingles: set[str]) -> list[str]:
    from portal.platform.inference.router import routing as rt

    ins = task["instruction"]
    want = task["checkers"][0]["workspace"]
    failures = []
    if not task.get("classifier_only"):
        got = rt._detect_workspace([{"role": "user", "content": ins}])
        if got != want:
            failures.append(f"Layer 2 resolves the prompt to {got!r}, not the gold {want!r}")
    if rt.detect_harmful_intent([{"role": "user", "content": ins}]):
        failures.append("the prompt trips the harmful-intent gate (would reroute to auto-daily)")
    if gen._shingles(ins) & example_shingles:
        failures.append("the prompt shares a five-word sequence with routing_examples.json (leak)")
    for ws in gen.PROMPTS:
        if re.search(rf"\b{re.escape(ws)}\b", ins):
            failures.append(f"the prompt names the workspace id {ws!r}")
    w = portal[WORKSPACE]
    prompt = (len(w.get("owui_system_prompt") or "") + len(ins)) / 4
    if prompt + 2048 > int(w.get("context_limit") or 0):
        failures.append(f"prompt ~{int(prompt)} tokens + output budget 2048 exceeds the window")
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
    portal = yaml.safe_load(open(f"{REPO}/config/portal.yaml"))["workspaces"]
    example_shingles = gen._example_shingles()
    tasks = [t for t in load_suite(SUITE) if only is None or t["id"] in only]
    return {t["id"]: check_task(t, portal, example_shingles) for t in tasks}


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
