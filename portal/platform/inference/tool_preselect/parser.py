"""Parse the preselector model's raw text output into an ordered,
deduplicated list of valid tool-index numbers (§4.4).

Must tolerate:
  - "1.", "2." (trailing period)
  - "(1)", "1)" (parens)
  - "1. run_bash" (number + tool name — extract only the number)
  - numbers separated by comma, newline, or both
  - preamble/postamble prose ("Here are the 5 most relevant tools: 1. ...")
  - numbers outside the valid 1..N range (discarded)
  - duplicate numbers (discarded, first occurrence order preserved)
"""

from __future__ import annotations

import re

# Matches an integer optionally wrapped in ( ) and/or followed by . or )
_NUMBER_RE = re.compile(r"\(?\b(\d+)\)?[.)]?")

# A line "looks like a list item" if, after stripping, it starts with a
# number (optionally wrapped in parens) — this is what distinguishes a
# ranked-list line ("1. web_search") from preamble/postamble prose that
# happens to mention a number ("Here are the 3 most relevant tools:").
_LIST_ITEM_LINE_RE = re.compile(r"^\(?\d+")


def _extract_numbers(text: str) -> list[int]:
    result = []
    for match in _NUMBER_RE.finditer(text):
        try:
            result.append(int(match.group(1)))
        except ValueError:
            continue
    return result


def parse_ranked_indices(raw_output: str, valid_max: int) -> list[int]:
    """Extract an ordered, deduplicated list of 1-indexed tool numbers.

    Only lines that look like list items (start with a number) are
    scanned — this excludes preamble/postamble prose that happens to
    mention a number (e.g. "Here are the 3 most relevant tools:").
    Falls back to scanning the whole text if no line looks like a list
    item (handles a single comma-separated line: "1, 2, 3").

    Args:
        raw_output: the preselector model's raw text response.
        valid_max: highest valid index (= number of tools offered).

    Returns:
        Ordered list of valid, deduplicated 1-indexed numbers. Empty
        list if nothing parseable was found.
    """
    list_lines = [
        line for line in raw_output.splitlines() if _LIST_ITEM_LINE_RE.match(line.strip())
    ]
    candidates = (
        [n for line in list_lines for n in _extract_numbers(line)]
        if list_lines
        else _extract_numbers(raw_output)
    )

    seen: set[int] = set()
    result: list[int] = []
    for n in candidates:
        if n < 1 or n > valid_max:
            continue
        if n in seen:
            continue
        seen.add(n)
        result.append(n)
    return result


def indices_to_tool_names(indices: list[int], tool_names_ordered: list[str]) -> list[str]:
    """Map 1-indexed positions back to tool names (indices already validated)."""
    return [tool_names_ordered[i - 1] for i in indices if 1 <= i <= len(tool_names_ordered)]
