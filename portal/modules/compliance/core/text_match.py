"""One quote measure, with no optional dependency and no invented threshold.

``adjudicate_refusals.py`` intended ``rapidfuzz.token_set_ratio`` and silently
fell back to ``difflib.SequenceMatcher.ratio`` under the same ``0.85`` floor
when rapidfuzz was absent. ``SequenceMatcher`` compares whole strings, so a
correct short quote inside a long section body scores near zero — measured
0.042-0.713, median 0.248 across the corpus this module classifies. A floor
tuned for one scale silently governed a different one, and
``checker_strictness`` was structurally unreachable as a result: it returned
0 where a hand read of CIP-004-7 alone found 8.

``quote_containment`` implements token-set containment directly — the
fraction of the quoted sentence's own distinct tokens present anywhere in the
section — which is scale-invariant with respect to the body's length the way
whole-string similarity is not. It applies no threshold; a caller decides what
a given ratio means for its own purpose.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["quote_containment"]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def quote_containment(quote: str, body: str) -> dict[str, Any]:
    """``{verbatim, ratio, backend}`` for one quote against one body.

    ``verbatim`` is a literal substring test (whitespace-insensitive is NOT
    applied — verbatim stays the standard). ``ratio`` is the fraction of the
    quote's distinct tokens found anywhere in the body: 1.0 means every word
    of the quote appears in the body, regardless of the body's own length, so
    a one-sentence quote in a ten-page section is not penalised for the
    section's size the way whole-string similarity is.
    """
    quote_stripped = quote.strip()
    body_stripped = body.strip() if body else ""
    verbatim = bool(quote_stripped) and quote_stripped in body_stripped

    quote_tokens = _tokens(quote_stripped)
    if not quote_tokens:
        ratio = 0.0
    else:
        body_tokens = _tokens(body_stripped)
        ratio = len(quote_tokens & body_tokens) / len(quote_tokens)

    return {
        "verbatim": verbatim,
        "ratio": round(ratio, 4),
        "backend": "token_set_containment",
    }
