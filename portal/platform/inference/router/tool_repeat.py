"""Per-turn guard against a model re-issuing a tool call it already made.

Some models (Qwen3.8 on the compliance seat, measured 2026-10-16) answer a full tool result
by asking for the same call again, hop after hop, until the 20-hop limit ends the turn with no
answer. A repeat gains nothing: the result is already in the conversation. The guard returns the
earlier result with a short note instead of running the tool again, and on a third identical
request tells the loop to take a final turn with the tools withheld.

One guard lives for one turn. Nothing is kept across turns.
"""

from __future__ import annotations

import json
from typing import Any

REPEAT_NOTE = (
    "You already called this with the same arguments; the result is above. "
    "Use it to answer, or call a different tool."
)
#: The request count at which the turn stops offering tools (1 = executed, 2 = first repeat).
FORCE_SYNTHESIS_AT = 3


def _canonical_args(call: dict[str, Any]) -> str:
    raw: Any = (call.get("function") or {}).get("arguments")
    if isinstance(raw, str):
        text = raw.strip()
        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            return text
    return json.dumps(raw if raw is not None else {}, sort_keys=True, separators=(",", ":"))


def call_key(call: dict[str, Any]) -> tuple[str, str]:
    """(tool name, canonical arguments): key order and whitespace never make a call new."""
    return (str((call.get("function") or {}).get("name", "")).strip(), _canonical_args(call))


class ToolRepeatGuard:
    """Remembers the calls a turn has executed and their results."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], str] = {}
        self._requests: dict[tuple[str, str], int] = {}
        self.force_synthesis = False
        self.suppressed = 0

    def seen(self, call: dict[str, Any]) -> bool:
        """True when this exact call already ran this turn; counts the request."""
        key = call_key(call)
        self._requests[key] = self._requests.get(key, 0) + 1
        if key not in self._results:
            return False
        self.suppressed += 1
        if self._requests[key] >= FORCE_SYNTHESIS_AT:
            self.force_synthesis = True
        return True

    def remember(self, call: dict[str, Any], result: dict[str, Any]) -> None:
        self._results[call_key(call)] = str(result.get("content") or "")

    def repeat_result(self, call: dict[str, Any]) -> dict[str, Any]:
        """The tool message for a suppressed repeat: the earlier result plus the note."""
        name = (call.get("function") or {}).get("name", "")
        earlier = self._results[call_key(call)]
        return {
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "name": name,
            "content": f"{earlier}\n\n[{REPEAT_NOTE}]",
        }
