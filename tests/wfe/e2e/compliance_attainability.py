"""Is each planted determination's gold reachable through the tools the model is offered?

The controls gate proves grading works; it cannot prove the gold can be reached. A determination
is attainable only when every fact its gold depends on (DECIDING_FACTS in the suite generator, by
control class) appears in the output of an offered compliance tool, called the way a model would,
on the evaluation instance, with the answer key absent. A fact that exists only in the PLANT header
or in data no tool exposes makes the task unattainable and this check fails: fix the store or the
projection so the fact is exposed key-free, or reword the task in the generator and record why.

It also proves the engine's own coverage path works for each task's requirement: the address is
accepted fully qualified and the standard's normative text is in the payload.

    uv run python -m tests.wfe.e2e.compliance_attainability            # live :8948
    uv run python -m tests.wfe.e2e.compliance_attainability --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable
from typing import Any

from tests.wfe.suites import build_compliance_production as gen

EVAL_URL = os.environ.get("WFE_COMPLIANCE_EVAL_URL", "http://localhost:8948")
Caller = Callable[[str, dict], str]


def call_eval(tool: str, args: dict) -> str:
    """One tool call on the evaluation instance, as the pipeline makes it."""
    req = urllib.request.Request(
        f"{EVAL_URL}/tools/{tool}",
        data=json.dumps({"arguments": args}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return resp.read().decode()


def flat(raw: str) -> str:
    """Tool output with JSON newlines and runs of whitespace collapsed to one space."""
    return re.sub(r"(?:\\n|\\t|\s)+", " ", raw)


def _targets() -> dict[str, str]:
    """doc id -> the requirement its determination names, from the corpus (not the key's gold)."""
    return {t["doc"]: t["req"] for t in gen.determination_targets()}


def check_task(doc: str, req: str, call: Caller) -> list[str]:
    """Failures for one determination (empty = attainable)."""
    failures: list[str] = []
    outputs: list[str] = []
    cache: dict[str, str] = {}

    def run(tool: str, args: dict) -> str:
        key = tool + json.dumps(args, sort_keys=True)
        if key not in cache:
            try:
                cache[key] = flat(call(tool, args))
            except Exception as e:  # noqa: BLE001
                cache[key] = f"CALL FAILED: {e}"
            outputs.append(cache[key])
        return cache[key]

    for fact in gen.DECIDING_FACTS.get(doc, []):
        out = run(fact.tool, fact.args)
        if not re.search(fact.pattern, out, re.I | re.S):
            failures.append(
                f"fact not exposed: {fact.why} — {fact.tool}({fact.args}) lacks /{fact.pattern}/"
            )
    if not gen.DECIDING_FACTS.get(doc):
        failures.append("no deciding facts recorded for this determination")

    cov = run("compliance_coverage", {"standard": req.split(" ")[0], "requirement": req})
    if re.search(r"is not a regulatory address|\"error\"", cov):
        failures.append(f"coverage rejects the fully qualified address {req!r}")
    if not re.search(r'"sections_in_standard": ?[1-9]', cov):
        failures.append(f"coverage finds no sections of the standard for {req!r}")
    normative = re.search(r"\"text\": ?\"== [^\"]{20,}", cov)
    if not normative:
        failures.append(f"the dual-document payload carries no normative text for {req!r}")

    for leak in gen.LEAKS:
        if any(re.search(leak, o) for o in outputs):
            failures.append(f"answer key reachable: /{leak}/ appears in a tool output")
    return failures


def check_all(call: Caller = call_eval) -> dict[str, list[str]]:
    return {doc: check_task(doc, req, call) for doc, req in _targets().items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    result: dict[str, Any] = check_all()
    bad = {d: f for d, f in result.items() if f}
    if a.json:
        print(json.dumps(result, indent=1))
    else:
        for doc, failures in result.items():
            print(f"{'FAIL' if failures else 'ok  '}  {doc}")
            for f in failures:
                print(f"        {f}")
        print(f"attainable: {len(result) - len(bad)}/{len(result)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
