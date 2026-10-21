"""Contracts for the offline orchestration arm."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ModelSeat = Literal["fast", "deep"]
_TASK_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


@dataclass(frozen=True)
class Budget:
    turns: int
    minutes: float
    output_tokens: int


@dataclass(frozen=True)
class Bite:
    bite_id: str
    goal: str
    discipline: str
    inputs: tuple[str, ...]
    depends_on: tuple[str, ...]
    tools: tuple[str, ...]
    output_path: str
    output_schema: dict[str, Any] | None
    file_type: str | None
    accept: tuple[dict[str, Any], ...]
    risk: str
    budget: Budget
    model: ModelSeat
    procedure: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "bite_id": self.bite_id,
            "goal": self.goal,
            "discipline": self.discipline,
            "inputs": list(self.inputs),
            "depends_on": list(self.depends_on),
            "tools": list(self.tools),
            "output": {
                "path": self.output_path,
                **({"schema": self.output_schema} if self.output_schema is not None else {}),
                **({"file_type": self.file_type} if self.file_type is not None else {}),
            },
            "accept": list(self.accept),
            "risk": self.risk,
            "budget": {
                "turns": self.budget.turns,
                "minutes": self.budget.minutes,
                "output_tokens": self.budget.output_tokens,
            },
            "model": self.model,
            "procedure": self.procedure,
        }


@dataclass(frozen=True)
class TaskPlan:
    task_id: str
    goal: str
    bites: tuple[Bite, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "bites": [b.as_dict() for b in self.bites],
        }


def parse_plan(raw: dict[str, Any]) -> TaskPlan:
    """Load and validate the hand-written Phase 1 plan contract."""
    if not isinstance(raw, dict):
        raise ValueError("plan must be an object")
    task_id = _required_string(raw, "task_id")
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError("task_id must use letters, numbers, dot, underscore, or hyphen")
    goal = _required_string(raw, "goal")
    raw_bites = raw.get("bites")
    if not isinstance(raw_bites, list) or not raw_bites:
        raise ValueError("plan.bites must be a non-empty list")
    bites = tuple(_parse_bite(item) for item in raw_bites)
    _validate_bites(bites)
    return TaskPlan(task_id=task_id, goal=goal, bites=bites)


def _parse_bite(raw: Any) -> Bite:
    if not isinstance(raw, dict):
        raise ValueError("each bite must be an object")
    output = raw.get("output")
    if not isinstance(output, dict):
        raise ValueError("bite.output must be an object")
    output_path = _required_string(output, "path")
    path = Path(output_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"bite output path must stay inside the task directory: {output_path}")
    schema = output.get("schema")
    file_type = output.get("file_type")
    if (schema is None) == (file_type is None):
        raise ValueError("bite.output must declare exactly one of schema or file_type")
    if schema is not None:
        if not isinstance(schema, dict):
            raise ValueError("bite.output.schema must be an object")
        Draft202012Validator.check_schema(schema)
    if file_type is not None and file_type not in {"json", "text"}:
        raise ValueError("bite.output.file_type must be json or text")
    raw_budget = raw.get("budget")
    if not isinstance(raw_budget, dict):
        raise ValueError("bite.budget must be an object")
    budget = Budget(
        turns=_positive_int(raw_budget, "turns"),
        minutes=_positive_number(raw_budget, "minutes"),
        output_tokens=_positive_int(raw_budget, "output_tokens"),
    )
    accept = raw.get("accept")
    if not isinstance(accept, list) or not accept or not all(isinstance(x, dict) for x in accept):
        raise ValueError("bite.accept must contain at least one deterministic check")
    model = raw.get("model", "fast")
    if model not in {"fast", "deep"}:
        raise ValueError("bite model must be fast or deep")
    bite = Bite(
        bite_id=_required_string(raw, "bite_id"),
        goal=_required_string(raw, "goal"),
        discipline=_required_string(raw, "discipline"),
        inputs=_string_tuple(raw, "inputs"),
        depends_on=_string_tuple(raw, "depends_on"),
        tools=_string_tuple(raw, "tools"),
        output_path=output_path,
        output_schema=schema,
        file_type=file_type,
        accept=tuple(accept),
        risk=str(raw.get("risk", "low")),
        budget=budget,
        model=cast(ModelSeat, model),
        procedure=str(raw.get("procedure", "")),
    )
    if bite.risk not in {"low", "high"}:
        raise ValueError(f"bite {bite.bite_id}: risk must be low or high")
    _validate_bite_tools(bite)
    return bite


def _validate_bite_tools(bite: Bite) -> None:
    if len(set(bite.tools)) != len(bite.tools):
        raise ValueError(f"bite {bite.bite_id}: tools must be unique")
    if "finish" in bite.tools:
        raise ValueError("finish is reserved for the orchestration worker")


def _validate_bites(bites: tuple[Bite, ...]) -> None:
    by_id = {bite.bite_id: bite for bite in bites}
    if len(by_id) != len(bites):
        raise ValueError("bite_id values must be unique")
    paths = [bite.output_path for bite in bites]
    if len(set(paths)) != len(paths):
        raise ValueError("bite output paths must be unique")
    for bite in bites:
        if any(dep not in by_id for dep in bite.depends_on):
            raise ValueError(f"bite {bite.bite_id}: depends_on contains an unknown bite")
        if bite.bite_id in bite.depends_on:
            raise ValueError(f"bite {bite.bite_id}: cannot depend on itself")
    _assert_acyclic(by_id)


def _assert_acyclic(by_id: dict[str, Bite]) -> None:
    active: set[str] = set()
    done: set[str] = set()

    def visit(bite_id: str) -> None:
        if bite_id in active:
            raise ValueError("bite dependency graph contains a cycle")
        if bite_id in done:
            return
        active.add(bite_id)
        for dependency in by_id[bite_id].depends_on:
            visit(dependency)
        active.remove(bite_id)
        done.add(bite_id)

    for bite_id in by_id:
        visit(bite_id)


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _string_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return tuple(value)


def _positive_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"budget.{key} must be a positive integer")
    return value


def _positive_number(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"budget.{key} must be a positive number")
    return float(value)


def plan_json(plan: TaskPlan) -> str:
    """Serialize a normalized hand-written plan for the ledger."""
    return json.dumps(plan.as_dict(), sort_keys=True)
