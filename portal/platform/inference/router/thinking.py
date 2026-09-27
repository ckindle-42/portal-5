"""Shared answer/reasoning separation for streaming and non-streaming paths."""

from __future__ import annotations

import re
from typing import Any

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_INNER_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_OPEN = "<think>"
_CLOSE = "</think>"
_MAX_LITERAL_TAG_EXAMPLE = 8192
NO_ANSWER_MESSAGE = "⚠️ The model did not produce an answer. Please retry."


class ThinkTagFilter:
    """Incrementally remove protocol ``<think>`` blocks from answer content.

    Only complete protocol markers outside Markdown code spans/fences are
    interpreted. A complete block immediately quoted with matching single or
    double quotes is preserved as literal markup. Code fences and inline code
    pass through byte-for-byte. The parser retains only a tag prefix, a bounded
    quoted example, and Markdown delimiter state; an unterminated think block
    is discarded at the terminal boundary.
    """

    def __init__(self) -> None:
        self._open_pending = ""
        self._in_think = False
        self._close_pending = ""
        self._literal_quote: str | None = None
        self._literal_parts: list[str] = []
        self._literal_size = 0
        self._literal_allowed = False
        self._closed_literal: tuple[str, str] | None = None
        self._marker_char = ""
        self._marker_count = 0
        self._inline_ticks = 0
        self._fence_char = ""
        self._fence_len = 0
        self._line_prefix_whitespace = True
        self._last_emitted = ""
        self.removed = False

    def feed(self, text: str, *, final: bool = False) -> str:
        """Return the visible portion of *text*, retaining delimiter state."""
        output: list[str] = []
        for char in text:
            if self._closed_literal is not None:
                quote, literal = self._closed_literal
                self._closed_literal = None
                if char == quote:
                    self._emit(literal, output)
                    self._emit(char, output)
                    continue
                self.removed = True
                self._outside_char(char, output)
                continue
            if self._in_think:
                self._think_char(char)
            else:
                self._outside_char(char, output)

        if final:
            if self._in_think:
                # An unterminated protocol block cannot be treated as answer
                # text. In particular, never flush its buffered inner text.
                self.removed = True
                self._reset_think()
            if self._closed_literal is not None:
                self._closed_literal = None
                self.removed = True
            if self._marker_count:
                self._finish_marker(output)
            if self._open_pending:
                self._emit(self._open_pending, output)
                self._open_pending = ""
        return "".join(output)

    def _emit(self, value: str, output: list[str]) -> None:
        if not value:
            return
        output.append(value)
        self._last_emitted = value[-1]
        for char in value:
            if char == "\n":
                self._line_prefix_whitespace = True
            elif char not in " \t\r":
                self._line_prefix_whitespace = False

    def _outside_char(self, char: str, output: list[str]) -> None:
        if self._marker_count:
            if char == self._marker_char:
                self._marker_count += 1
                return
            self._finish_marker(output)

        in_code = bool(self._fence_char) or bool(self._inline_ticks)
        if char == "`" or (
            char == "~" and (self._fence_char == "~" or self._line_prefix_whitespace)
        ):
            self._marker_char = char
            self._marker_count = 1
            return
        if in_code:
            self._emit(char, output)
            return

        if self._open_pending:
            self._open_pending += char
            candidate = self._open_pending.lower()
            if candidate == _OPEN:
                self._open_pending = ""
                self._begin_think()
            elif not _OPEN.startswith(candidate):
                pending = self._open_pending
                self._open_pending = ""
                self._emit(pending[0], output)
                for rest in pending[1:]:
                    self._outside_char(rest, output)
            return
        if char == "<":
            self._open_pending = char
            return
        self._emit(char, output)

    def _finish_marker(self, output: list[str]) -> None:
        marker = self._marker_char
        count = self._marker_count
        at_line_prefix = self._line_prefix_whitespace
        self._marker_char = ""
        self._marker_count = 0
        self._emit(marker * count, output)

        if self._fence_char:
            if marker == self._fence_char and at_line_prefix and count >= self._fence_len:
                self._fence_char = ""
                self._fence_len = 0
            return
        if self._inline_ticks:
            if marker == "`" and count == self._inline_ticks:
                self._inline_ticks = 0
            return
        if at_line_prefix and count >= 3 and marker in ("`", "~"):
            self._fence_char = marker
            self._fence_len = count
        elif marker == "`":
            self._inline_ticks = count

    def _begin_think(self) -> None:
        self._in_think = True
        self._close_pending = ""
        self._literal_quote = self._last_emitted if self._last_emitted in ("'", '"') else None
        self._literal_allowed = self._literal_quote is not None
        self._literal_parts = []
        self._literal_size = len(_OPEN)

    def _think_char(self, char: str) -> None:
        self._close_pending += char
        close_lower = _CLOSE.lower()
        while self._close_pending and not close_lower.startswith(self._close_pending.lower()):
            flushed = self._close_pending[0]
            self._close_pending = self._close_pending[1:]
            if self._literal_allowed:
                self._literal_parts.append(flushed)
                self._literal_size += len(flushed)
                if self._literal_size > _MAX_LITERAL_TAG_EXAMPLE:
                    self._literal_allowed = False
                    self._literal_parts.clear()
        if self._close_pending.lower() != close_lower:
            return

        self._in_think = False
        if self._literal_allowed and self._literal_quote:
            literal = _OPEN + "".join(self._literal_parts) + _CLOSE
            self._closed_literal = (self._literal_quote, literal)
        else:
            self.removed = True
        self._reset_think()

    def _reset_think(self) -> None:
        self._in_think = False
        self._close_pending = ""
        self._literal_quote = None
        self._literal_parts = []
        self._literal_size = 0
        self._literal_allowed = False


def strip_think(text: str) -> str:
    """Remove protocol think wrappers while preserving every other character."""
    return ThinkTagFilter().feed(text, final=True)


def extract_think_inner(text: str) -> str:
    """Return the text inside the first ``<think>…</think>`` block, or ``""``."""
    m = _THINK_INNER_RE.search(text)
    return m.group(1).strip() if m else ""


def normalize_think_message(
    msg: dict[str, Any], *, workspace_id: str = "", backend_id: str = ""
) -> bool:
    """Remove inline protocol thoughts and report whether the turn has no answer.

    Separate ``reasoning``, ``reasoning_content`` and ``thinking`` fields are
    intentionally left separate. The return value is true when an inline
    protocol block or a separate reasoning field exists but no visible answer
    remains. Callers classify that turn as an incomplete response; they must
    never use reasoning as substitute verdict text.
    """
    del workspace_id, backend_id  # identifiers belong in trace metadata, not logs
    content = msg.get("content") or ""
    content_filter = ThinkTagFilter()
    if isinstance(content, str):
        visible = content_filter.feed(content, final=True)
        msg["content"] = visible
    else:
        visible = ""
    has_reasoning = any(msg.get(name) for name in ("reasoning", "reasoning_content", "thinking"))
    return not visible.strip() and bool(has_reasoning or content_filter.removed)
