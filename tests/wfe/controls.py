"""Known-answer controls for WFE tasks (cause C2). Specified in
docs/WFE_ROOT_CAUSES_20261013.md, "Known-answer controls"."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from portal.platform.inference.router.thinking import NO_ANSWER_MESSAGE
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome

#: The date expiry is judged against; tests replace it.
TODAY = dt.date.today

#: Checkers a control tests fully: they grade the answer text and, for tool_grounded, the
#: tool trace a declared control supplies ({"answer": ..., "tool_calls": [...]}).
ANSWER_GRADED = {
    "answer_contains",
    "answer_after_reasoning",
    "routed_workspace",
    "cited_answer",
    "compliance_reading_contract",
    "tool_grounded",
    "office_contains",
}

#: Every key a suite task may carry, and the keys each checker type reads (N-24): a
#: missing or misspelled key used to default to a check that any answer passes.
TASK_KEYS = {
    "id",
    "kind",
    "lane",
    "agentic",
    "instruction",
    "images",
    "fixtures",
    "doc_spec",
    "completion_signal",
    "checkers",
    "seed",
    "seed_b64",
    "repo_read",
    "controls",
    "requires_tools",
    "arguable",
    "dimensions",
    "eval_set",
    "kb_seed",
    "memory_seed",
    "no_tools",
    "screen",
    "classifier_only",
    "halt_kind",
    "refusal_is_failure",
    "expires",
    # Short per-row provenance for an expectation that changed deliberately.
    "note",
    # A short multi-turn task: `turns` replaces `instruction` + `checkers`; `rubric` is
    # the judge's copy; workspace/category/source are the suite author's provenance.
    "turns",
    "rubric",
    "workspace",
    "category",
    "source",
}
#: The keys one scripted user turn may carry (runner.scripted_turns).
TURN_KEYS = {"user", "checks", "expect_tools"}
CHECKER_KEYS = {
    "answer_contains": ({"patterns"}, {"forbid", "exact", "forbid_in_tool_output"}),
    "must_not_contain": ({"patterns"}, set()),
    "answer_after_reasoning": ({"patterns"}, set()),
    "routed_workspace": ({"workspace"}, set()),
    "tool_grounded": ({"evidence"}, {"tools"}),
    "office_contains": ({"kind", "expect"}, {"exact", "path", "headings", "sheets", "titles"}),
}


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
    return {s.get("type", "") for s in task.get("checkers") or []}


def _spec_failures(specs, where: str = "") -> list[str]:
    """A checker list the harness cannot grade: empty, an unknown type, unknown keys."""
    from tests.wfe.checkers import CHECKERS

    if not isinstance(specs, list) or not specs:
        return [f"{where}no checkers: a task without one passes any answer"]
    bad = []
    for s in specs:
        kind = s.get("type")
        if kind not in CHECKERS:
            bad.append(f"{where}unknown checker type {kind!r}")
        elif kind in CHECKER_KEYS:
            need, may = CHECKER_KEYS[kind]
            if missing := sorted(k for k in need if not s.get(k)):
                bad.append(f"{where}{kind}: missing or empty {missing}")
            if extra := sorted(set(s) - need - may - {"type"}):
                bad.append(f"{where}{kind}: unknown keys {extra}")
    return bad


def _turn_failures(task: dict) -> list[str]:
    """A multi-turn task: every scripted turn well formed, and something actually graded."""
    turns = task.get("turns")
    if not isinstance(turns, list) or not turns:
        return ["turns must be a non-empty list of user turns"]
    bad = []
    if "checkers" in task:
        bad.append("a multi-turn task grades per turn: move checkers into turns[].checks")
    if "controls" in task:
        bad.append("controls are defined for single-turn tasks only")
    graded = False
    for i, turn in enumerate(turns):
        if not isinstance(turn, dict):
            bad.append(f"turns[{i}] must be an object")
            continue
        if unknown := sorted(set(turn) - TURN_KEYS):
            bad.append(f"turns[{i}]: unknown keys {unknown}")
        if not str(turn.get("user") or "").strip():
            bad.append(f"turns[{i}]: missing user text")
        if turn.get("checks"):
            bad += _spec_failures(turn["checks"], f"turns[{i}].checks: ")
            positive = {s.get("type") for s in turn["checks"]} - {"must_not_contain"}
            if not positive and not turn.get("expect_tools"):
                bad.append(
                    f"turns[{i}]: must_not_contain alone passes an empty answer; add a "
                    "positive check or expect_tools"
                )
            graded = graded or bool(positive)
        if not isinstance(turn.get("expect_tools") or [], list):
            bad.append(f"turns[{i}]: expect_tools must be a list")
        graded = graded or bool(turn.get("expect_tools"))
    if not graded:
        bad.append(
            "no turn carries a positive check or an expected tool: nothing about the "
            "conversation is graded"
        )
    return bad


def schema_failures(task: dict, suite: str = "") -> list[ControlFailure]:
    """A task the harness cannot grade as written: no checkers, an unknown checker
    type, a checker spec with a missing or unknown key, or an unknown task key (N-24)."""
    tid, bad = task.get("id", "?"), []
    if unknown := sorted(set(task) - TASK_KEYS):
        bad.append(f"unknown task keys {unknown}")
    if task.get("turns") is not None:
        bad += _turn_failures(task)
    else:
        bad += _spec_failures(task.get("checkers"))
    return [ControlFailure(suite, tid, "schema", "a gradeable task", "invalid", b) for b in bad]


def _seed_text(task: dict) -> str:
    seed = task.get("seed") or {}
    if isinstance(seed, dict):
        return "\n".join(str(v) for v in seed.values())
    return str(seed)


def _outcome(task: dict, answer: str | dict) -> tuple[Outcome, str]:
    """A control is an answer, or {"answer", "tool_calls", "files_b64", "served"}: a trace
    for a trace-grounded task, the files a produced-file task's checker should find, and
    the pipeline's served record a routed_workspace task's checker should read."""
    text = answer.get("answer", "") if isinstance(answer, dict) else answer
    calls = answer.get("tool_calls") if isinstance(answer, dict) else None
    files = answer.get("files_b64") if isinstance(answer, dict) else None
    served = answer.get("served") if isinstance(answer, dict) else None
    with tempfile.TemporaryDirectory() as td:
        for rel, b64 in (files or {}).items():
            (Path(td) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(td) / rel).write_bytes(base64.b64decode(b64))
        r = apply_checkers(
            task,
            CheckContext(
                final_text=text,
                task=task,
                tool_calls=calls,
                sandbox_root=Path(td) if td else None,
                served=served,
            ),
        )
    return r.outcome, r.notes


def _auto_control_failures(task: dict, suite: str, prefix: str = "") -> list[ControlFailure]:
    """The answers every answer-graded task must reject: an empty reply, the pipeline's
    placeholder, and an echo of what the model was given. A must_not_contain-only task
    is not answer-graded — an empty answer satisfies it by construction."""
    positive = _checker_types(task) - {"must_not_contain"}
    if not positive or not positive <= ANSWER_GRADED:
        return []
    tid = task.get("id", "?")
    auto = {
        "empty": "",
        "placeholder": NO_ANSWER_MESSAGE,
        "echo": f"{task.get('instruction', '')}\n{_seed_text(task)}",
    }
    out = []
    for name, answer in auto.items():
        got, notes = _outcome(task, answer)
        if got == Outcome.PASS:
            out.append(ControlFailure(suite, tid, prefix + name, "not PASS", got.value, notes))
    return out


def check_task(task: dict, suite: str = "", today: dt.date | None = None) -> list[ControlFailure]:
    """Every control failure for one task; empty when the checker is sound."""
    tid = task.get("id", "?")
    out: list[ControlFailure] = schema_failures(task, suite)
    if out:
        return out
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
    if task.get("turns"):
        # A multi-turn task's controls are its turns: each graded turn must reject the
        # auto answers on its own. Declared controls are refused by _turn_failures.
        for i, turn in enumerate(task["turns"]):
            if turn.get("checks"):
                sub = {
                    **task,
                    "checkers": turn["checks"],
                    "instruction": turn.get("user", ""),
                    "controls": {},
                }
                out += _auto_control_failures(sub, suite, f"turn{i}/")
        return out
    out += _auto_control_failures(task, suite)
    declared = task.get("controls") or {}
    for i, answer in enumerate(declared.get("fail") or []):
        got, notes = _outcome(task, answer)
        if got == Outcome.PASS:
            out.append(ControlFailure(suite, tid, f"fail[{i}]", "not PASS", got.value, notes))
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
