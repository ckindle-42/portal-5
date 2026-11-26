"""Extract only the current user's own words from a routed message list."""

from __future__ import annotations

import re
from typing import Any

_ATTACHED_NOTE_RE = re.compile(r"\[Attached file — id: .*?, name: .*?, type: .*?(?:, path: .*?)?\]")


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
    if text.lstrip().startswith("### Task:") and "provided context" in text.casefold():
        close = text.rfind("</context>")
        if close != -1:
            text = text[close + len("</context>") :]
    text = _ATTACHED_NOTE_RE.sub("", text).strip()
    return text if limit is None else text[:limit]
