"""Known-answer controls for WFE tasks (cause C2). Specified in
docs/WFE_ROOT_CAUSES_20261013.md, "Known-answer controls"."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path

from portal.platform.inference.router.thinking import NO_ANSWER_MESSAGE
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome

#: The date expiry is judged against; tests replace it.
TODAY = dt.date.today

#: Checkers that grade only the answer text, so a control answer tests them fully.
ANSWER_GRADED = {"answer_contains", "cited_answer", "compliance_reading_contract"}


@dataclass
class ControlFailure:
    suite: str
    task_id: str
    control: str
    expected: str
    got: str
    notes: str

    def __str__(self) -> str:
        return (
            f"{self.suite}:{self.task_id} control {self.control!r} expected "
            f"{self.expected}, got {self.got} ({self.notes[:160]})"
        )


def _checker_types(task: dict) -> set[str]:
    specs = task.get("checkers")
    if specs is None:
        specs = [task.get("checker") or {"type": "answer_contains"}]
    return {s.get("type", "answer_contains") for s in specs}


def _seed_text(task: dict) -> str:
    seed = task.get("seed") or {}
    if isinstance(seed, dict):
        return "\n".join(str(v) for v in seed.values())
    return str(seed)


def _outcome(task: dict, answer: str) -> tuple[Outcome, str]:
    r = apply_checkers(task, CheckContext(final_text=answer, task=task))
    return r.outcome, r.notes


def check_task(task: dict, suite: str = "", today: dt.date | None = None) -> list[ControlFailure]:
    """Every control failure for one task; empty when the checker is sound."""
    tid = task.get("id", "?")
    out: list[ControlFailure] = []
    expires = task.get("expires")
    if expires and dt.date.fromisoformat(str(expires)) < (today or TODAY()):
        out.append(
            ControlFailure(
                suite,
                tid,
                "expires",
                f"on or after {expires}",
                "expired",
                "time-sensitive key past its expiry: re-verify the key, move the date",
            )
        )
    if not _checker_types(task) <= ANSWER_GRADED:
        return out
    auto = {
        "empty": "",
        "placeholder": NO_ANSWER_MESSAGE,
        "echo": f"{task.get('instruction', '')}\n{_seed_text(task)}",
    }
    declared = task.get("controls") or {}
    for name, answer in [
        *auto.items(),
        *((f"fail[{i}]", a) for i, a in enumerate(declared.get("fail") or [])),
    ]:
        got, notes = _outcome(task, answer)
        if got == Outcome.PASS:
            out.append(ControlFailure(suite, tid, name, "not PASS", got.value, notes))
    for i, answer in enumerate(declared.get("pass") or []):
        got, notes = _outcome(task, answer)
        if got != Outcome.PASS:
            out.append(ControlFailure(suite, tid, f"pass[{i}]", "PASS", got.value, notes))
    if any(s.get("exact") for s in task.get("checkers") or []) and not declared.get("pass"):
        out.append(
            ControlFailure(
                suite,
                tid,
                "pass",
                "a declared gold answer",
                "none",
                "a task with an exact key must declare a gold answer that passes",
            )
        )
    return out


def check_suite(path: Path | str, today: dt.date | None = None) -> list[ControlFailure]:
    from tests.wfe.runner import load_suite

    p = Path(path)
    return [f for t in load_suite(p) for f in check_task(t, p.stem, today)]


def gate(suite_paths: list[Path | str], task_ids: set[str] | None = None) -> list[ControlFailure]:
    """Control failures limited to the tasks a plan will actually run."""
    fails = [f for sp in sorted({str(p) for p in suite_paths}) for f in check_suite(sp)]
    return [f for f in fails if task_ids is None or f.task_id in task_ids]


def suite_digest(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def receipt(suite_paths: list[Path | str], task_ids: set[str] | None = None) -> dict:
    """Run the gate; record suite digests, task count, date and failures."""
    paths = sorted({str(p) for p in suite_paths})
    fails = gate(paths, task_ids)
    return {
        "checked_utc": dt.datetime.now(dt.UTC).isoformat(),
        "today": TODAY().isoformat(),
        "suites": {p: suite_digest(p) for p in paths},
        "tasks": len(task_ids) if task_ids is not None else None,
        "failures": [str(f) for f in fails],
    }
