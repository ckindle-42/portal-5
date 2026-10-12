"""Prompt/tool-surface consistency for WFE workloads (pure functions, no I/O).

Why this exists: the auto-compliance suite serves the production persona prompt
(config/personas/cippolicywriter.yaml). That prompt tells the model to call
compliance tools (nerc_cip_requirement, compliance_ask, nerc_cip_currency, ...)
and to use an output taxonomy, while the WFE harness offers only its own tools
and the user turn asks for a different label set. Found in the Saluki Rule-5
re-verify (2026-10-12): the model hunted map/register files with repo_search
because the prompt sent it there with the only tools it had. Every seat measured
on that suite was affected, so the check flags it until the suite is fixed.
"""

from __future__ import annotations

import json
import re

#: Tool-name families a production persona may reference but the WFE harness
#: does not offer. Extend when a new family appears in a persona prompt.
TOOL_FAMILY_RE = re.compile(
    r"\b(nerc_cip_\w+|compliance_\w+|lookup_control|map_frameworks|search_controls)\b"
)

#: Competing output label sets. Two sets named in one run is a contradiction.
TAXONOMY_SETS: dict[str, tuple[str, ...]] = {
    "coverage": ("Full", "Partial", "None", "Ambiguous"),
    "determination": ("SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "ABSTAIN"),
}


def prompt_tool_mismatches(system_prompt: str, harness_tools: set[str]) -> list[str]:
    """Tool names the prompt references that the harness does not offer."""
    named = sorted(set(TOOL_FAMILY_RE.findall(system_prompt)))
    return [name for name in named if name not in harness_tools]


def taxonomy_conflicts(system_prompt: str, user_text: str) -> list[str]:
    """Label sets used by both the system prompt and the user turn, which disagree."""
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


def suite_warnings(system_prompt: str, user_text: str, harness_tools: set[str]) -> list[str]:
    """Human-readable warnings for one workload's system prompt and user turn."""
    out = [
        f"prompt names tool not in harness surface: {t}"
        for t in prompt_tool_mismatches(system_prompt, harness_tools)
    ]
    conflicts = taxonomy_conflicts(system_prompt, user_text)
    if conflicts:
        out.append(
            f"output taxonomy conflict between system prompt and user turn: {', '.join(conflicts)}"
        )
    return out


def audit_workspace(system_prompt: str, suite_jsonl: str, harness_tools: set[str]) -> list[str]:
    """Warnings for the SERVED system prompt against the user turns of one suite file.

    `system_prompt` is what the runner sends: the persona prompt plus the workspace's
    system_prompt_append (runner.py `sp += ws.get("system_prompt_append")`). Pure: the
    caller reads the files. Each suite row's `instruction` is the user turn.
    """
    warnings: list[str] = []
    for line in suite_jsonl.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for w in suite_warnings(system_prompt, str(row.get("instruction", "")), harness_tools):
            if w not in warnings:
                warnings.append(w)
    return warnings
