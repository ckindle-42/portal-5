from __future__ import annotations

import json
import re

HARNESS_NOTE_MARKER = "WFE HARNESS TOOLS:"

TAXONOMY_SETS: dict[str, tuple[str, ...]] = {
    "coverage": ("Full", "Partial", "None", "Ambiguous"),
    "determination": ("SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "ABSTAIN"),
}


def production_tool_names(portal: dict) -> set[str]:
    names: set[str] = set()
    for ws in (portal.get("workspaces") or {}).values():
        names.update(t for t in ws.get("tools") or [] if "_" in t)
    return names


def prompt_tool_mismatches(
    system_prompt: str, harness_tools: set[str], known_tools: set[str]
) -> list[str]:
    if HARNESS_NOTE_MARKER in system_prompt:
        return []
    return sorted(
        t for t in known_tools - harness_tools if re.search(rf"\b{re.escape(t)}\b", system_prompt)
    )


def harness_note(system_prompt: str, harness_tools: list[str], known_tools: set[str]) -> str:
    if not prompt_tool_mismatches(system_prompt, set(harness_tools), known_tools):
        return ""
    return (
        f"\n\n{HARNESS_NOTE_MARKER} the only tools available here are "
        f"{', '.join(harness_tools)}. Any other tool named in these instructions does not "
        "exist in this environment: work from the material you are given using these "
        "tools. If the user's request specifies an output format, follow it instead of "
        "any output format these instructions describe."
    )


def taxonomy_conflicts(system_prompt: str, user_text: str) -> list[str]:
    if HARNESS_NOTE_MARKER in system_prompt:
        return []
    sys_hits = {
        k
        for k, labels in TAXONOMY_SETS.items()
        if any(re.search(rf"\b{lbl}\b", system_prompt) for lbl in labels)
    }
    usr_hits = {
        k
        for k, labels in TAXONOMY_SETS.items()
        if any(re.search(rf"\b{lbl}\b", user_text) for lbl in labels)
    }
    if sys_hits and usr_hits and sys_hits != usr_hits:
        return sorted(sys_hits ^ usr_hits)
    return []


def suite_warnings(
    system_prompt: str, user_text: str, harness_tools: set[str], known_tools: set[str]
) -> list[str]:
    out = [
        f"prompt names tool not in harness surface: {t}"
        for t in prompt_tool_mismatches(system_prompt, harness_tools, known_tools)
    ]
    conflicts = taxonomy_conflicts(system_prompt, user_text)
    if conflicts:
        out.append(
            f"output taxonomy conflict between system prompt and user turn: {', '.join(conflicts)}"
        )
    return out


def task_tool_mismatches(task: dict, harness_tools: set[str], known_tools: set[str]) -> list[str]:
    if task.get("requires_tools"):
        return []
    text = str(task.get("instruction", ""))
    return sorted(t for t in known_tools - harness_tools if re.search(rf"\b{re.escape(t)}\b", text))


def audit_workspace(
    system_prompt: str, suite_jsonl: str, harness_tools: set[str], known_tools: set[str]
) -> list[str]:
    warnings: list[str] = []
    for line in suite_jsonl.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        instruction = str(row.get("instruction", ""))
        found = suite_warnings(system_prompt, instruction, harness_tools, known_tools)
        found += [
            f"task {row.get('id')} demands tool not in harness surface: {t}"
            for t in task_tool_mismatches(row, harness_tools, known_tools)
        ]
        for w in found:
            if w not in warnings:
                warnings.append(w)
    return warnings
