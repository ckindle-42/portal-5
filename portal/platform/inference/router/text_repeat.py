"""In-stream guard against a degenerate line-repetition loop.

The platform's definition of a degenerate answer already exists in the QAT
grader (``tests/qat/uat_behavioral.check_output_hygiene``): the same stripped
line of at least 12 characters occurring 5 times. The grader judges after the
fact, so a looping turn still burns its whole output budget first (seen live
2026-11-26 on auto-coding::bigfix: 8192 tokens in ~2 minutes, finish=length,
QAT row FAIL). This guard applies the same definition while the stream runs
and ends the turn on the offending repetition, so the client gets a clear
notice instead of two minutes of loop.
"""

from __future__ import annotations

import re

#: A stripped line shorter than this is ordinary structure (bullets, fences), not a loop.
MIN_LINE_CHARS = 12
#: Occurrences of one identical line that make the answer degenerate (QAT grader's count).
REPEAT_LIMIT = 5
_FENCE_RE = re.compile(r"(?:`{3,}|~{3,})[\w+#.-]*")


def _is_structural_line(value: str) -> bool:
    """True for comment rulers, horizontal rules, table borders, and code fences."""
    if not any(ch.isalnum() for ch in value):
        return True
    return bool(_FENCE_RE.fullmatch(value))


class LineRepetitionGuard:
    """Counts completed stripped lines in one turn's visible content stream."""

    def __init__(self, limit: int = REPEAT_LIMIT, min_chars: int = MIN_LINE_CHARS) -> None:
        self._counts: dict[str, int] = {}
        self._pending = ""
        self._limit = limit
        self._min_chars = min_chars
        self.tripped_line: str | None = None
        self.tripped_count = 0

    def feed(self, text: str) -> bool:
        """Feed a visible-content fragment; True once the repeat limit trips."""
        if self.tripped_line is not None:
            return True
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            value = line.strip()  # strip() also drops a trailing \r from CRLF
            if len(value) < self._min_chars or _is_structural_line(value):
                continue
            count = self._counts.get(value, 0) + 1
            self._counts[value] = count
            if count >= self._limit:
                self.tripped_line = value
                self.tripped_count = count
                return True
        return False

    def stop_message(self) -> str:
        """The client-visible reason, framed by the caller's stop notice."""
        return (
            f"the same line repeated {self.tripped_count} times, so generation was stopped "
            "instead of running to the token limit"
        )
