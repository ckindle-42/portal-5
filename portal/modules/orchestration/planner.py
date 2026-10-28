"""Deep-seat task planning and deterministic plan validation."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from string import Template
from typing import Any

from .contracts import TaskPlan, parse_plan
from .worker import Engine, _response_parts

PLANNER_RULES = """Write a JSON task plan as one object with task_id, goal, and bites.
Every bite must have accept (a list of deterministic acceptance checks) or review='deep' with a specific review_reason.
Keep every bite within the supplied comfortable Fast context token budget; include budget.context_tokens.
Split reading from acting: a bite must not combine read_tools and action_tools, and untrusted reads never act.
Every file_write bite must declare its exact writable data-plane paths in write_paths.
Prefer small bites and give each a narrow goal and only its required tools.
End with stage='assembly' followed by stage='final_review'; final_review depends on assembly.
Each bite must include a checkable output, dependencies, budget, model, risk, and procedure.
The framework writes each bite's declared output from its finish call; file_write is only for additional write_paths.
Do not invent tools, paths, or discipline names. Return JSON only."""
MAX_PLAN_BITES = 64
MAX_BITE_TURNS = 16
MAX_BITE_MINUTES = 60
MAX_BITE_OUTPUT_TOKENS = 16_384
MAX_WRITE_PATHS = 128


def validate_planned_plan(
    raw: dict[str, Any],
    arm_config: dict[str, Any],
    discipline_key: str,
    source_dir: Path | None = None,
) -> TaskPlan:
    """Validate planner output against the selected discipline and arm policy."""
    planner = _mapping(arm_config.get("planner"), "planner")
    disciplines = _mapping(arm_config.get("disciplines"), "disciplines")
    discipline = _mapping(disciplines.get(discipline_key), f"discipline {discipline_key}")
    plan = validate_execution_plan(raw, arm_config, source_dir)
    max_context = min(
        _positive_int(planner, "comfortable_context_tokens"),
        _positive_int(discipline, "fast_context_budget_tokens"),
    )
    for bite in plan.bites:
        if bite.discipline != discipline_key:
            raise ValueError(f"bite {bite.bite_id}: discipline must be {discipline_key}")
        if bite.budget.context_tokens is None:
            raise ValueError(f"bite {bite.bite_id}: budget.context_tokens is required")
        if bite.budget.context_tokens > max_context:
            raise ValueError(
                f"bite {bite.bite_id}: context budget {bite.budget.context_tokens} exceeds "
                f"Fast context budget {max_context}"
            )
    if len(plan.bites) < 2 or [plan.bites[-2].stage, plan.bites[-1].stage] != [
        "assembly",
        "final_review",
    ]:
        raise ValueError("plan must end with assembly and final_review bites")
    if plan.bites[-2].bite_id not in plan.bites[-1].depends_on:
        raise ValueError("final_review must depend on the assembly bite")
    return plan


def validate_execution_plan(
    raw: dict[str, Any], arm_config: dict[str, Any], source_dir: Path | None = None
) -> TaskPlan:
    """Validate every executable entry point against immutable discipline policy."""
    disciplines = _mapping(arm_config.get("disciplines"), "disciplines")
    plan = parse_plan(raw)
    if len(plan.bites) > MAX_PLAN_BITES:
        raise ValueError(f"plan exceeds the {MAX_PLAN_BITES}-bite limit")
    by_id = {bite.bite_id: bite for bite in plan.bites}
    for bite in plan.bites:
        discipline = _mapping(disciplines.get(bite.discipline), f"discipline {bite.discipline}")
        allowed_tools = _string_set(discipline, "tool_allowlist")
        read_tools = _string_set(discipline, "read_tools")
        action_tools = _string_set(discipline, "action_tools")
        if not set(bite.tools) <= allowed_tools:
            raise ValueError(f"bite {bite.bite_id}: tool outside discipline allowlist")
        has_read = bite.reads_untrusted or bool(set(bite.tools) & read_tools)
        has_action = bool(set(bite.tools) & action_tools)
        if has_read and has_action:
            raise ValueError(f"bite {bite.bite_id}: reading and acting must be separate bites")
        if "file_write" in bite.tools and not bite.write_paths:
            raise ValueError(f"bite {bite.bite_id}: file_write requires write_paths")
        if len(bite.write_paths) > MAX_WRITE_PATHS:
            raise ValueError(f"bite {bite.bite_id}: too many write_paths")
        if bite.budget.turns > MAX_BITE_TURNS:
            raise ValueError(f"bite {bite.bite_id}: turns exceed policy limit")
        if bite.budget.minutes > MAX_BITE_MINUTES:
            raise ValueError(f"bite {bite.bite_id}: minutes exceed policy limit")
        if bite.budget.output_tokens > MAX_BITE_OUTPUT_TOKENS:
            raise ValueError(f"bite {bite.bite_id}: output tokens exceed policy limit")
        _validate_write_paths(bite)
        if source_dir is not None:
            _validate_inputs(bite, by_id, source_dir)
    return replace(plan, policy_validated=True)


def instantiate_plan_template(
    arm_config: dict[str, Any],
    *,
    template_key: str,
    discipline_key: str,
    task_id: str,
    parameters: dict[str, str],
    source_dir: Path,
) -> TaskPlan:
    """Render one configured plan template and validate it as planner output."""
    disciplines = _mapping(arm_config.get("disciplines"), "disciplines")
    discipline = _mapping(disciplines.get(discipline_key), f"discipline {discipline_key}")
    templates = _mapping(discipline.get("plan_templates"), f"{discipline_key}.plan_templates")
    template = _mapping(templates.get(template_key), f"plan template {template_key}")
    declared = template.get("parameters")
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        raise ValueError(f"plan template {template_key} parameters must be a list of strings")
    if len(set(declared)) != len(declared):
        raise ValueError(f"plan template {template_key} has duplicate parameters")
    missing = set(declared) - parameters.keys()
    unexpected = parameters.keys() - set(declared)
    if missing or unexpected:
        raise ValueError(
            f"plan template parameters mismatch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    raw_plan = _render_template_value(template.get("plan"), parameters)
    if not isinstance(raw_plan, dict) or "task_id" in raw_plan:
        raise ValueError(f"plan template {template_key} must define a plan without task_id")
    raw_plan["task_id"] = task_id
    return validate_planned_plan(raw_plan, arm_config, discipline_key, source_dir)


def _render_template_value(value: Any, parameters: dict[str, str]) -> Any:
    if isinstance(value, str):
        try:
            return Template(value).substitute(parameters)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"invalid plan template placeholder: {exc}") from exc
    if isinstance(value, list):
        return [_render_template_value(item, parameters) for item in value]
    if isinstance(value, dict):
        return {key: _render_template_value(item, parameters) for key, item in value.items()}
    return value


def planner_prompt(arm_config: dict[str, Any], discipline_key: str) -> str:
    """Build the immutable planner prompt from configured budgets and tools."""
    policy = _mapping(arm_config.get("planner"), "planner")
    discipline = _mapping(
        _mapping(arm_config.get("disciplines"), "disciplines").get(discipline_key), discipline_key
    )
    return (
        f"{PLANNER_RULES}\n"
        f"Comfortable Fast context budget: {min(_positive_int(policy, 'comfortable_context_tokens'), _positive_int(discipline, 'fast_context_budget_tokens'))} tokens.\n"
        f"Allowed tools: {json.dumps(discipline.get('tool_allowlist', []))}.\n"
        f"Read tools: {json.dumps(discipline.get('read_tools', []))}.\n"
        f"Action tools: {json.dumps(discipline.get('action_tools', []))}.\n"
        f"Discipline: {discipline_key}.\n"
        f"Procedures: {json.dumps(discipline.get('procedures', []))}."
    )


def plan_goal(
    engine: Engine,
    *,
    goal: str,
    task_id: str,
    discipline: str,
    arm_config: dict[str, Any],
    source_dir: Path | None = None,
) -> dict[str, Any]:
    """Ask the Deep seat for one plan and return only validated JSON."""
    body = {
        "model": engine.model_tag,
        "messages": [
            {"role": "system", "content": planner_prompt(arm_config, discipline)},
            {
                "role": "user",
                "content": json.dumps(
                    {"task_id": task_id, "goal": goal, "discipline": discipline},
                    sort_keys=True,
                ),
            },
        ],
        "max_tokens": 8192,
        "temperature": 0.1,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": True},
    }
    engine.load_plan(300)
    response = engine.chat(body, 300, lambda _event: None)
    content, _ = _response_parts(response)
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("planner response must be a JSON object")
    if raw.get("task_id") != task_id:
        raise ValueError("planner response task_id differs from the request")
    if raw.get("goal") != goal:
        raise ValueError("planner response goal differs from the request")
    validate_planned_plan(raw, arm_config, discipline, source_dir)
    return raw


def _validate_inputs(bite: Any, by_id: dict[str, Any], source_dir: Path) -> None:
    source_root = source_dir.expanduser().resolve()
    for reference in bite.inputs:
        if reference in by_id:
            if reference not in bite.depends_on:
                raise ValueError(f"bite {bite.bite_id}: input bite {reference} is not a dependency")
        else:
            relative = Path(reference)
            target = (source_root / relative).resolve()
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not target.is_relative_to(source_root)
            ):
                raise ValueError(f"bite {bite.bite_id}: input path escapes source directory")
            if not target.is_file():
                raise ValueError(f"bite {bite.bite_id}: input path does not exist: {reference}")


def _validate_write_paths(bite: Any) -> None:
    for value in bite.write_paths:
        if value in bite.inputs:
            continue
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or path == Path("."):
            raise ValueError(f"bite {bite.bite_id}: write path must stay inside task data")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} configuration must be a mapping")
    return value


def _positive_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _string_set(raw: dict[str, Any], key: str) -> set[str]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return set(value)
