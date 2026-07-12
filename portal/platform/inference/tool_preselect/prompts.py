"""Prompt template for the tool preselector (§1.7).

Deliberately simple: the preselector ranks, it does not reason and
does not use MiniCPM5's native XML tool-call format — it's a plain
text ranker.
"""

from __future__ import annotations

_USER_TURN_MAX_CHARS = 500

PROMPT_TEMPLATE = """User request: {user_turn}

Available tools:
{tool_list}

Return the numbers of the {k_plus_slack} most relevant tools for this request, one per line, in order of relevance. Only return numbers."""


def build_prompt(
    user_turn_content: str,
    tool_names_ordered: list[str],
    tool_descriptions: dict[str, str],
    k: int,
    slack: int = 3,
) -> str:
    """Build the preselector prompt.

    Args:
        user_turn_content: raw user turn text (stripped to first 500 chars)
        tool_names_ordered: tool names in the order they should be numbered
        tool_descriptions: name -> short description
        k: target number of tools the caller wants
        slack: extra candidates requested beyond K (§1.7 — K_plus_slack = K + 3)

    Returns:
        The complete prompt string.
    """
    stripped = user_turn_content[:_USER_TURN_MAX_CHARS]
    lines = [
        f"{i}. {name}: {tool_descriptions.get(name, '')}"
        for i, name in enumerate(tool_names_ordered, start=1)
    ]
    return PROMPT_TEMPLATE.format(
        user_turn=stripped,
        tool_list="\n".join(lines),
        k_plus_slack=k + slack,
    )
