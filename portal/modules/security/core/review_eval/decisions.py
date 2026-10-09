"""review_eval.decisions -- every experiment is a question, answered by a rule written first.

Root cause this exists for (lesson 18): "delegated sessions keep optimizing a target unless
stopped" -- a threshold-validation session went on to edit a deprecated grader's constant
because it had a metric and no question. A task that hands an agent a metric and no stop is
asking it to overfit. With no operator gates in this program, the stop must be mechanical:

* a decision record is written and COMMITTED before the arm that answers it is run
  (pre-registration, verified by git ancestry, not by trust);
* it names the question, the stage it targets, the arms (the first is the control), the
  metric, the adopt-if rule, and the anti-goals;
* it targets the BINDING stage (``attribution``) or says in writing why not;
* once resolved it records status, the stamped report, and the result -- and is not edited again.

Records are markdown with a YAML front matter. This module parses and validates them.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import yaml

from .attribution import STAGES

STATUSES = ("PREREGISTERED", "ADOPTED", "REJECTED", "INCONCLUSIVE")
REQUIRED = ("id", "question", "stage", "arms", "metric", "adopt_if", "anti_goals", "status")
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


class DecisionInvalid(ValueError):  # noqa: N818 -- the name is the contract
    """A decision record that cannot be parsed."""


@dataclass(frozen=True)
class Decision:
    id: str
    question: str
    stage: str
    arms: tuple[str, ...]
    metric: str
    adopt_if: str
    anti_goals: tuple[str, ...]
    status: str
    report: str = ""
    result: str = ""
    why_not_binding: str = ""


def parse(text: str) -> Decision:
    match = _FRONT.match(text)
    if match is None:
        raise DecisionInvalid("a decision record starts with a YAML front matter block")
    raw: Any = yaml.safe_load(match.group(1))
    if not isinstance(raw, Mapping):
        raise DecisionInvalid("front matter must be a mapping")
    missing = [k for k in REQUIRED if raw.get(k) in (None, "", [])]
    if missing:
        raise DecisionInvalid(f"missing fields: {missing}")
    return Decision(
        id=str(raw["id"]),
        question=str(raw["question"]).strip(),
        stage=str(raw["stage"]),
        arms=tuple(str(a) for a in raw["arms"]),
        metric=str(raw["metric"]).strip(),
        adopt_if=str(raw["adopt_if"]).strip(),
        anti_goals=tuple(str(a) for a in raw["anti_goals"]),
        status=str(raw["status"]),
        report=str(raw.get("report") or ""),
        result=str(raw.get("result") or "").strip(),
        why_not_binding=str(raw.get("why_not_binding") or "").strip(),
    )


def problems(
    decision: Decision,
    *,
    path: str,
    binding_stage: str | None,
    commit_time: Callable[[str], float | None],
) -> list[str]:
    """Why this record cannot be trusted. Empty means it can."""
    out: list[str] = []
    if decision.stage not in STAGES:
        out.append(f"stage {decision.stage!r} is not one of {STAGES}")
    if len(decision.arms) < 2:
        out.append("an experiment needs a control and at least one candidate arm")
    if decision.status not in STATUSES:
        out.append(f"status {decision.status!r} is not one of {STATUSES}")
    if (
        binding_stage
        and decision.stage != binding_stage
        and not decision.why_not_binding
        and decision.status != "REJECTED"
    ):
        out.append(
            f"targets {decision.stage!r} but the binding stage is {binding_stage!r}; "
            "say why in why_not_binding or retarget"
        )
    if decision.status == "PREREGISTERED":
        if decision.report or decision.result:
            out.append("a PREREGISTERED record has no report or result yet")
        return out
    if not decision.report or not decision.result:
        out.append("a resolved record names its stamped report and states the result")
        return out
    decided_at, reported_at = commit_time(path), commit_time(decision.report)
    if decided_at is None or reported_at is None:
        out.append("both the record and its report must be committed")
    elif not decided_at < reported_at:
        out.append("the record was not committed before the report that answers it")
    return out
