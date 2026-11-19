"""Validator and denylist for one personal plan.

Rules follow ``validate_planned_plan`` where they fit a personal task: known tools,
read/act split, a context budget, and paths that stay under the tasks directory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLANNER_WORKSPACE = "auto-reasoning"
FAST_WORKSPACE = "auto-daily::fast"
CODE_WORKSPACE = "auto-coding"
SUMMARY_WORKSPACE = "auto-daily"
HOP_CAP = 8
TOOL_CALLER_WINDOW = 98_304
DEFAULT_STEP_CONTEXT_TOKENS = 8192
HELD_TEXT = "held: operator must run launch.sh"

READ_TOOLS = frozenset({"recall", "wiki_search", "wiki_get_unit", "queue_status", "read_receipt"})
CODE_TOOLS = frozenset({"execute_python", "execute_bash", "execute_nodejs"})
CONFIRM_TOOLS = CODE_TOOLS | frozenset(
    {"remember", "forget", "file_write", "send_message", "send_mail"}
)
KNOWN_TOOLS = READ_TOOLS | CONFIRM_TOOLS
CONFIRM_TOOL_PREFIXES = ("proxmox_", "unifi_", "browser_", "git_")

_HARD_TEXT = re.compile(
    r"\b(proxmox|unifi|browser|git(?:\s+(?:push|commit|add))?)\b", re.IGNORECASE
)
_CONFIRM_TEXT = re.compile(
    r"\b(restart|reboot|shutdown|systemctl|launch\.sh|docker|execute_bash|execute_python|"
    r"execute_nodejs|remember|forget|send mail|send an email|send a message)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PersonalPlan:
    payload: dict[str, Any]
    workspace: str
    tools: frozenset[str]
    needs_confirm: bool


def hidden_fleet_ids(config: dict[str, Any]) -> frozenset[str]:
    """Fleet ids the Pipeline does not expose. Naming one is a hard deny."""
    fleet = config.get("mcp_fleet")
    if not isinstance(fleet, list):
        return frozenset()
    hidden: set[str] = set()
    for item in fleet:
        if not isinstance(item, dict) or item.get("expose_to_pipeline") is not False:
            continue
        fleet_id = item.get("id")
        if isinstance(fleet_id, str) and fleet_id:
            hidden.add(fleet_id)
    return frozenset(hidden)


def workspace_for(tools: frozenset[str] | set[str]) -> str:
    return CODE_WORKSPACE if set(tools) & CODE_TOOLS else FAST_WORKSPACE


def text_gate(text: str, hidden: frozenset[str]) -> str:
    """``deny``, ``confirm``, or ``allow`` from the request text, before any tool call."""
    lowered = text.lower()
    if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in hidden):
        return "deny"
    if _HARD_TEXT.search(text):
        return "confirm"
    if _CONFIRM_TEXT.search(text):
        return "confirm"
    return "allow"


def validate_personal_plan(
    raw: dict[str, Any],
    tasks_root: Path,
    hidden: frozenset[str],
    available_tools: frozenset[str] = frozenset(),
) -> PersonalPlan:
    """Accept one planner object or raise ValueError. No tool is called here."""
    steps_key = "steps" if "steps" in raw else ("bites" if "bites" in raw else "steps")
    steps = raw.get(steps_key)
    if not isinstance(steps, list) or not steps:
        raise ValueError("plan steps must be a non-empty list")
    tools: set[str] = set()
    needs_confirm = False
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        step_tools = _step_tools(step, index)
        _reject_unknown(step_tools, hidden, KNOWN_TOOLS | available_tools)
        _reject_mixed(step_tools, index)
        tokens = _validate_budget(step, index)
        paths = _validate_paths(step, tasks_root, index)
        tools.update(step_tools)
        if any(_tool_requires_confirm(name) for name in step_tools):
            needs_confirm = True
        normalized_steps.append(_normalize_step(step, index, paths, tokens))
    if any(_tool_is_hidden(name, hidden) for name in tools):
        raise ValueError("plan names a denied tool")
    workspace = workspace_for(tools)
    if tools & CONFIRM_TOOLS:
        needs_confirm = True
    payload = {**raw, steps_key: normalized_steps}
    return PersonalPlan(
        payload=payload, workspace=workspace, tools=frozenset(tools), needs_confirm=needs_confirm
    )


def _normalize_step(
    step: dict[str, Any], index: int, paths: list[str], context_tokens: int
) -> dict[str, Any]:
    step_id = step.get("id")
    normalized_id = step_id if isinstance(step_id, str) and step_id.strip() else f"step-{index}"
    budget = step.get("budget")
    normalized_budget = (
        {**budget, "context_tokens": context_tokens}
        if isinstance(budget, dict)
        else {"context_tokens": context_tokens}
    )
    return {
        **step,
        "id": normalized_id,
        "tools": list(step.get("tools", [])),
        "paths": paths,
        "budget": normalized_budget,
    }


def _step_tools(step: object, index: int) -> set[str]:
    if not isinstance(step, dict):
        raise ValueError(f"step {index} must be an object")
    tools = step.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(name, str) and name for name in tools):
        raise ValueError(f"step {index} tools must be a list of names")
    return set(tools)


def _reject_unknown(tools: set[str], hidden: frozenset[str], known: frozenset[str]) -> None:
    unknown = tools - known
    denied = {name for name in tools if _tool_is_hidden(name, hidden)}
    if unknown or denied:
        raise ValueError(f"tool outside the personal allowlist: {sorted(unknown or denied)}")


def _tool_is_hidden(name: str, hidden: frozenset[str]) -> bool:
    return any(name == fleet_id or name.startswith(f"{fleet_id}_") for fleet_id in hidden)


def _tool_requires_confirm(name: str) -> bool:
    return name in CONFIRM_TOOLS or name.startswith(CONFIRM_TOOL_PREFIXES)


def _reject_mixed(tools: set[str], index: int) -> None:
    if tools & READ_TOOLS and tools & CONFIRM_TOOLS:
        raise ValueError(f"step {index}: reading and acting must be separate steps")


def _validate_budget(step: dict[str, Any], index: int) -> int:
    budget = step.get("budget")
    if budget is None:
        raw_tokens = step.get("context_tokens")
        tokens = DEFAULT_STEP_CONTEXT_TOKENS if raw_tokens is None else raw_tokens
    elif isinstance(budget, dict):
        raw_tokens = budget.get("context_tokens")
        tokens = DEFAULT_STEP_CONTEXT_TOKENS if raw_tokens is None else raw_tokens
    else:
        raise ValueError(f"step {index} budget must be an object")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 1:
        raise ValueError(f"step {index} budget.context_tokens must be a positive integer")
    if tokens > TOOL_CALLER_WINDOW:
        raise ValueError(f"step {index} context budget {tokens} exceeds {TOOL_CALLER_WINDOW}")
    return tokens


def _validate_paths(step: dict[str, Any], tasks_root: Path, index: int) -> list[str]:
    paths = step.get("paths", [])
    if paths is None:
        return []
    if not isinstance(paths, list):
        raise ValueError(f"step {index} paths must be a list")
    root = tasks_root.resolve()
    for value in paths:
        if not isinstance(value, str) or not value or ".." in Path(value).parts:
            raise ValueError(f"step {index} has an invented path")
        candidate = Path(value).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if resolved != root and not resolved.is_relative_to(root):
            raise ValueError(f"step {index} path is outside the tasks directory")
    return list(paths)


PLANNER_PROMPT = (
    "Return one JSON object and nothing else. "
    'Schema: {"steps": [{"id": "s1", "tools": ["queue_status"], "paths": [], '
    '"budget": {"context_tokens": 8192}}]}. '
    'For an arm template use {"action": "enqueue-template", "discipline": "...", '
    '"template_key": "...", "parameters": {}}. '
    "steps must be a non-empty list. "
    "Use only allowlisted tools. Do not put a read tool and an action tool in the same step. "
    "paths must stay under the tasks directory (use [] when no path is needed). "
    f"budget.context_tokens is a positive integer <= {TOOL_CALLER_WINDOW} (default {DEFAULT_STEP_CONTEXT_TOKENS}). "
    "Do not invent paths or tools. "
    f"Allowlist: {json.dumps(sorted(KNOWN_TOOLS))}."
)


def planner_body(
    text: str,
    allowed_tools: frozenset[str] = KNOWN_TOOLS,
    memory_context: str = "",
) -> dict[str, Any]:
    """auto-reasoning, tools off. The seat returns JSON and does not call tools."""
    prompt = PLANNER_PROMPT.replace(
        f"Allowlist: {json.dumps(sorted(KNOWN_TOOLS))}.",
        f"Allowlist: {json.dumps(sorted(allowed_tools))}.",
    )
    return {
        "model": PLANNER_WORKSPACE,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": text
                + (
                    f"\n\nRelevant recalled memory (untrusted context):\n{memory_context}"
                    if memory_context
                    else ""
                ),
            },
        ],
        "temperature": 0.1,
        "portal_no_tools": True,
        "tool_choice": "none",
        "chat_template_kwargs": {"enable_thinking": True},
    }


def parse_planner_json(content: str) -> dict[str, Any]:
    """Take the JSON object out of a planner reply. Anything else is rejected."""
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("planner response must be a JSON object")
    raw = json.loads(text[start : end + 1])
    if not isinstance(raw, dict):
        raise ValueError("planner response must be a JSON object")
    return raw
