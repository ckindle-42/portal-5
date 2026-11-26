"""Extract only the current user's own words from a routed message list."""

from __future__ import annotations

import re
from typing import Any

_ATTACHED_NOTE_RE = re.compile(r"\[Attached file — id: .*?, name: .*?, type: .*?(?:, path: .*?)?\]")
_OWUI_TOOL_QUERY_DELIMITER = '"""\nQuery: '


def _owui_tool_selection_prompt(messages: list[dict[str, Any]]) -> bool:
    return any(
        message.get("role") == "system"
        and isinstance(message.get("content"), str)
        and (
            "Your task is to choose and return the correct tool(s)" in message["content"]
            or "Available Tools:" in message["content"]
        )
        for message in messages
        if isinstance(message, dict)
    )


def _owui_tool_query(messages: list[dict[str, Any]], text: str) -> str:
    if not _owui_tool_selection_prompt(messages):
        return text
    if text.startswith("History:\n"):
        marker = text.rfind(_OWUI_TOOL_QUERY_DELIMITER)
        return text[marker + len(_OWUI_TOOL_QUERY_DELIMITER) :] if marker != -1 else text
    if text.startswith("Query: "):
        return text[len("Query: ") :]
    return text


def _last_user_content(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return str(content)
    return ""


def is_owui_task_prompt(messages: list[dict[str, Any]]) -> bool:
    text = _last_user_content(messages).lstrip()
    return text.startswith("### Task:") and "<chat_history>" in text


def own_user_text(messages: list[dict[str, Any]], limit: int | None = None) -> str:
    text = _last_user_content(messages)
    if text.lstrip().startswith("### Task:") and "<chat_history>" in text:
        return ""
    text = _owui_tool_query(messages, text)
    if text.lstrip().startswith("### Task:") and "provided context" in text.casefold():
        close = text.rfind("</context>")
        if close != -1:
            text = text[close + len("</context>") :]
    text = _ATTACHED_NOTE_RE.sub("", text).strip()
    return text if limit is None else text[:limit]
