"""Is each security-analysis task answerable from the instruction alone?

auto-security's analytical workload is measured without tools on this suite, so a
task is attainable only when:

  self-contained  every deciding fact (the CVE identifier or the snippet's first
                  defining line) appears in the instruction;
  gold-private    the gold (CWE id or severity band) is never stated in the
                  instruction or the embedded snippet;
  recomputable    the generator, re-run, computes the same gold the committed
                  suite carries;
  fits the window the prompt plus the hard output cap stays inside the seat's
                  context_limit.

Nothing here touches the network.

    uv run python -m tests.wfe.e2e.security_analysis_attainability            # offline
    uv run python -m tests.wfe.e2e.security_analysis_attainability --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import yaml

from tests.wfe.runner import load_suite
from tests.wfe.suites import build_security_analysis_production as gen

REPO = __import__("pathlib").Path(__file__).resolve().parents[3]
SUITE = "tests/wfe/suites/security_analysis_production.jsonl"
WORKSPACE = "auto-security"


def _gold(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def _window_failures(task: dict, portal: dict) -> list[str]:
    w = portal[WORKSPACE]
    limit = int(w.get("context_limit") or 0)
    cap = int(w.get("predict_limit") or 2048)
    prompt = (len(w.get("owui_system_prompt") or "") + len(task["instruction"])) / 4
    if prompt + cap > limit:
        return [f"prompt ~{int(prompt)} tokens + output cap {cap} exceeds {limit}"]
    return []


def check_task(task: dict, portal: dict, built: dict[str, str]) -> list[str]:
    """Failures for one task (empty = attainable)."""
    tid, ins = task["id"], task["instruction"]
    failures = []
    facts = gen.DECIDING_FACTS.get(tid) or []
    if not facts:
        failures.append("no deciding facts recorded")
    for fact in facts:
        if not re.search(fact.pattern, ins, re.I | re.S):
            failures.append(f"given not stated: {fact.why} — instruction lacks /{fact.pattern}/")
    if _gold(task) in ins:
        failures.append("gold not private: the gold appears in the instruction")
    if tid in built and built[tid] != _gold(task):
        failures.append(f"gold drift: suite {_gold(task)} != generator {built[tid]}")
    failures.extend(_window_failures(task, portal))
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
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
