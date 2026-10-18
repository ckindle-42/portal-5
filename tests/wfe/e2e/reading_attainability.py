"""Is each reading-narrow task attainable through the reading tool subset?

The suite reuses compliance_production's gold, so this check reuses its machinery: a
determination is attainable when every deciding fact (DECIDING_FACTS in
build_compliance_production, by control class) appears in an offered tool's output on
the evaluation instance with the PLANT key absent, and the engine's coverage path
accepts the task's fully qualified address (tests/wfe/e2e/compliance_attainability.py
owns all of that — this module delegates to it). A lookup is attainable when
nerc_cip_requirement returns the part's verbatim text carrying exactly the interval
the gold states, and no answer key (expected_coverage, control_class, PLANT) is
reachable. The only thing narrow here is the allowlist, which the live row exercises
as a whole.

check_task stays hermetic — the offline unit drives it with a stub caller; nothing
runs unless invoked:

    uv run python -m tests.wfe.e2e.reading_attainability            # live :8948
    uv run python -m tests.wfe.e2e.reading_attainability --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable

from tests.wfe.e2e import compliance_attainability as comp_att
from tests.wfe.runner import load_suite
from tests.wfe.suites import build_reading_production as gen

SUITE = "tests/wfe/suites/reading_production.jsonl"
EVAL_URL = comp_att.EVAL_URL
Caller = Callable[[str, dict], str]


def call_eval(tool: str, args: dict) -> str:
    return comp_att.call_eval(tool, args)


def check_task(task: dict, call: Caller) -> list[str]:
    """Failures for one task (empty = attainable). Determinations delegate to the
    compliance attainability check (same facts, same instance)."""
    gen.build()  # repopulates comp.DECIDING_FACTS order-independently
    if task["kind"] == "determination":
        doc = re.search(r'"document"\s*:\s*"([^"]+)"', task["controls"]["pass"][0]["answer"]).group(
            1
        )
        req = json.loads(task["controls"]["pass"][0]["answer"])["requirement"]
        return comp_att.check_task(doc, req, call)
    gold = json.loads(task["controls"]["pass"][0]["answer"])
    rid, interval = gold["requirement"], gold["interval"]
    out = call("nerc_cip_requirement", {"req_id": rid})
    failures = []
    if not re.search(re.escape(rid), out, re.I | re.S):
        failures.append(f"fact not exposed: the register holds {rid}")
    num, _, unit = interval.partition(" ")
    if not re.search(rf"\b{num}\s+{re.escape(unit)}\b", out, re.I | re.S):
        failures.append(f"fact not exposed: {rid}'s verbatim text lacks /{num} {unit}/")
    for leak in ("expected_coverage", "control_class", r"<!--\s*PLANT"):
        if re.search(leak, out, re.I | re.S):
            failures.append(f"answer key reachable: /{leak}/ appears in a tool output")
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
    tasks = [t for t in load_suite(SUITE) if only is None or t["id"] in only]
    return {t["id"]: check_task(t, call_eval) for t in tasks}


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
