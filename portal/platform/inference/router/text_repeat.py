"""In-stream guard against a degenerate repetition loop: output that repeats
WITHOUT PROGRESS. The definition is shared with the QAT grader
(``tests/qat/uat_behavioral.check_output_hygiene``), which calls this module
instead of keeping its own copy. A line recurring with new content between
occurrences (a citation after each claim) is progress; a recent span with no
novel line and a duplicate — consecutive repeats or a short cycle — is not.
"""

from __future__ import annotations

import re
from collections import deque

#: A stripped line shorter than this is ordinary structure (bullets, fences), not a loop.
MIN_LINE_CHARS = 12
#: The limit-th identical line, or a short cycle filling the no-novel span, is degenerate.
REPEAT_LIMIT = 5
_FENCE_RE = re.compile(r"(?:`{3,}|~{3,})[\w+#.-]*")


def _is_structural_line(value: str) -> bool:
    """True for comment rulers, horizontal rules, table borders, and code fences."""
    if not any(ch.isalnum() for ch in value):
        return True
    return bool(_FENCE_RE.fullmatch(value))


class LineRepetitionGuard:
    """Judges completed stripped lines; trips when the tail stops making progress.

    Trips when the last ``limit - 1`` qualifying lines (stripped, >= min chars,
    non-structural) contain no first-occurrence line and at least one duplicate:
    the ``limit``-th identical line, or a short cycle dominating the tail. A
    line returning after new content never contributes to a trip.
    """

    def __init__(self, limit: int = REPEAT_LIMIT, min_chars: int = MIN_LINE_CHARS) -> None:
        self._seen: set[str] = set()
        self._counts: dict[str, int] = {}
        self._span: deque[tuple[str, bool]] = deque(maxlen=max(limit - 1, 1))  # (line, novel)
        self._pending = ""
        self._min_chars = min_chars
        self.tripped_line: str | None = None
        self.tripped_count = 0

    def feed(self, text: str) -> bool:
        """Feed a visible-content fragment; True once the tail shows no progress."""
        if self.tripped_line is not None:
            return True
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            if self._feed_line(line):
                return True
        return False

    def finish(self) -> bool:
        """Judge a final line left unterminated by end of output (whole-answer judging)."""
        if self.tripped_line is not None or not self._pending:
            return self.tripped_line is not None
        line, self._pending = self._pending, ""
        return self._feed_line(line)

    def _feed_line(self, line: str) -> bool:
        value = line.strip()  # strip() also drops a trailing \r from CRLF
        if len(value) < self._min_chars or _is_structural_line(value):
            return False
        novel = value not in self._seen
        self._seen.add(value)
        self._counts[value] = self._counts.get(value, 0) + 1
        self._span.append((value, novel))
        values = [span_value for span_value, _ in self._span]
        if (
            len(values) == self._span.maxlen
            and not novel
            and not any(span_novel for _, span_novel in self._span)
            and len(set(values)) < len(values)
        ):
            self.tripped_line = value
            self.tripped_count = self._counts[value]
            return True
        return False

    def stop_message(self) -> str:
        """The client-visible reason, framed by the caller's stop notice."""
        return (
            "the output stopped making progress — the same lines kept repeating with nothing "
            f"new between ({self.tripped_count} occurrences of one line), so generation was "
            "stopped instead of running to the token limit"
        )
