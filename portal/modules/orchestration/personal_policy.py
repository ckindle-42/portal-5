"""Validator and denylist for one personal plan.

Rules follow ``validate_planned_plan`` where they fit a personal task: known tools,
read/act split, a context budget, and paths that stay under the tasks directory.
"""

from __future__ import annotations

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
HELD_TEXT = "held: operator must run launch.sh"

READ_TOOLS = frozenset({"recall", "wiki_search", "wiki_get_unit", "queue_status", "read_receipt"})
CODE_TOOLS = frozenset({"execute_python", "execute_bash", "execute_nodejs"})
CONFIRM_TOOLS = CODE_TOOLS | frozenset(
    {"remember", "forget", "file_write", "send_message", "send_mail"}
)
KNOWN_TOOLS = READ_TOOLS | CONFIRM_TOOLS
# Denied even after confirm. Brief default, independent of expose_to_pipeline.
HARD_DENY_NAMES = frozenset({"proxmox", "unifi", "browser", "git"})

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


def text_gate(text: str, hidden: frozenset[str]) -> str:
    """``deny``, ``confirm``, or ``allow`` from the request text, before any tool call."""
    lowered = text.lower()
    if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in hidden | HARD_DENY_NAMES):
        return "deny"
    if _HARD_TEXT.search(text):
        return "deny"
    if _CONFIRM_TEXT.search(text):
        return "confirm"
    return "allow"


def validate_personal_plan(
    raw: dict[str, Any], tasks_root: Path, hidden: frozenset[str]
) -> PersonalPlan:
    """Accept one planner object or raise ValueError. No tool is called here."""
    steps = raw.get("steps", raw.get("bites"))
    if not isinstance(steps, list) or not steps:
        raise ValueError("plan steps must be a non-empty list")
    tools: set[str] = set()
    needs_confirm = False
    for index, step in enumerate(steps):
        step_tools = _step_tools(step, index)
        _reject_unknown(step_tools, hidden)
        _reject_mixed(step_tools, index)
        _require_budget(step, index)
        _reject_paths(step, tasks_root, index)
        tools.update(step_tools)
        if step_tools & CONFIRM_TOOLS or step_tools & HARD_DENY_NAMES:
            needs_confirm = True
    if tools & HARD_DENY_NAMES or tools & hidden:
        raise ValueError("plan names a denied tool")
    workspace = CODE_WORKSPACE if tools & CODE_TOOLS else FAST_WORKSPACE
    if tools & CONFIRM_TOOLS:
        needs_confirm = True
    return PersonalPlan(
        payload=raw, workspace=workspace, tools=frozenset(tools), needs_confirm=needs_confirm
    )


def _step_tools(step: object, index: int) -> set[str]:
    if not isinstance(step, dict):
        raise ValueError(f"step {index} must be an object")
    tools = step.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(name, str) and name for name in tools):
        raise ValueError(f"step {index} tools must be a list of names")
    return set(tools)


def _reject_unknown(tools: set[str], hidden: frozenset[str]) -> None:
    unknown = tools - KNOWN_TOOLS
    denied = tools & (HARD_DENY_NAMES | hidden)
    if unknown or denied:
        raise ValueError(f"tool outside the personal allowlist: {sorted(unknown or denied)}")


def _reject_mixed(tools: set[str], index: int) -> None:
    if tools & READ_TOOLS and tools & CONFIRM_TOOLS:
        raise ValueError(f"step {index}: reading and acting must be separate steps")


def _require_budget(step: dict[str, Any], index: int) -> None:
    budget = step.get("budget")
    if not isinstance(budget, dict):
        raise ValueError(f"step {index} budget is required")
    tokens = budget.get("context_tokens")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 1:
        raise ValueError(f"step {index} budget.context_tokens is required")
    if tokens > TOOL_CALLER_WINDOW:
        raise ValueError(f"step {index} context budget {tokens} exceeds {TOOL_CALLER_WINDOW}")


def _reject_paths(step: dict[str, Any], tasks_root: Path, index: int) -> None:
    paths = step.get("paths", [])
    if paths is None:
        return
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
