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


def parse_ranked_indices(raw_output: str, valid_max: int) -> list[int]:
    """Extract an ordered, deduplicated list of 1-indexed tool numbers.

    Args:
        raw_output: the preselector model's raw text response.
        valid_max: highest valid index (= number of tools offered).

    Returns:
        Ordered list of valid, deduplicated 1-indexed numbers. Empty
        list if nothing parseable was found.
    """
    seen: set[int] = set()
    result: list[int] = []
    for match in _NUMBER_RE.finditer(raw_output):
        try:
            n = int(match.group(1))
        except ValueError:
            continue
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
