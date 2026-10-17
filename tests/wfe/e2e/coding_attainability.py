"""Is each coding task attainable?

Every hidden test passes against the reference solution kept in the generator, so the task is
solvable, and the seeded repo alone does not pass (the task is not already solved). This is
local: it runs the task's own checkers on a scratch directory, as the harness does after an
arm ends. The live half (the sandbox tools as the model sees them, hidden_pytest run in the
row's dir after the arm) is the live executor's first live row per kind.

    uv run python -m tests.wfe.e2e.coding_attainability
    uv run python -m tests.wfe.e2e.coding_attainability --json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_coding_production as gen


def _grade(task: dict, files: dict[str, str]) -> tuple[Outcome, str]:
    with tempfile.TemporaryDirectory() as td:
        for rel, text in files.items():
            (Path(td) / rel).write_text(text)
        r = apply_checkers(
            task, CheckContext(task=task, final_text="", tool_calls=[], sandbox_root=Path(td))
        )
    return r.outcome, r.notes


def check_task(task: dict) -> list[str]:
    """Failures for one file-graded task (empty = attainable)."""
    seed = dict(task.get("seed") or {})
    failures = []
    outcome, notes = _grade(task, {**seed, **gen.REFERENCES[task["id"]]})
    if outcome != Outcome.PASS:
        failures.append(f"the reference does not pass the hidden tests: {notes[:200]}")
    if _grade(task, seed)[0] == Outcome.PASS:
        failures.append("the seeded repo already passes: nothing for the model to do")
    return failures


def run(only: set[str] | None = None) -> dict[str, list[str]]:
    tasks = [t for t in gen.build() if t["kind"] != "read" and (only is None or t["id"] in only)]
    return {t["id"]: check_task(t) for t in tasks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    res = run(set(a.only) if a.only else None)
    bad = {k: v for k, v in res.items() if v}
    if a.json:
        print(json.dumps({"tasks": len(res), "unattainable": bad}, indent=1))
    else:
        for tid, f in res.items():
            print(f"{'FAIL' if f else 'ok  '} {tid}")
            for x in f:
                print(f"       {x}")
        print(f"\n{len(res) - len(bad)}/{len(res)} attainable (read tasks: see the slice tests)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
