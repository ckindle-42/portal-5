"""READING_TRUTH_V1 P6R - a quote that is almost verbatim is a corrupted quote, not a paraphrase.

B0 found 8 of 42 answers with character-level corruption inside quoted spans,
one of them reversing the meaning ("does not directly access" became "does car
directly access"). The integrity diagnostic classed them with paraphrases,
which hides a property of the serving build behind a property of the reading.
This module names them: a quoted span that is NOT verbatim in its source, yet
matches a window of the source within a small character edit distance, is
NEAR-VERBATIM - garbled or minimally altered, not reworded.

Pure functions. The fold is passed in (callers pass the store's own verbatim
fold), so this module never decides what counts as equal text; the edit budget
is a parameter so the P6R calibration, not this file, sets it.
"""

from __future__ import annotations

import difflib
import string
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass


def _default_fold(text: str) -> str:
    return " ".join(text.split()).lower()


@dataclass(frozen=True)
class NearVerbatim:
    """A quoted span that is one small edit budget away from its source."""

    distance: int
    span: str
    window: str

    @property
    def ratio(self) -> float:
        return round(self.distance / max(1, len(self.span)), 4)


def levenshtein(a: str, b: str, limit: int) -> int:
    """Character edit distance, bounded: returns ``limit + 1`` once it is exceeded."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1] if previous[-1] <= limit else limit + 1


def default_budget(span: str) -> int:
    """At least 3 edits (one short word garbled), else 8% of the span's characters."""
    return max(3, round(0.08 * len(span)))


#: a window's edges are arbitrary cut points, so punctuation there is not part of the quote
_EDGE = string.punctuation + "\u201c\u201d\u2018\u2019"


def _windows(words: list[str], size: int) -> list[str]:
    if size < 1 or size > len(words):
        return []
    return [" ".join(words[i : i + size]).strip(_EDGE) for i in range(len(words) - size + 1)]


def near_verbatim(
    span: str,
    source: str,
    *,
    fold: Callable[[str], str] = _default_fold,
    budget: Callable[[str], int] = default_budget,
    min_words: int = 3,
    prefilter: float = 0.75,
) -> NearVerbatim | None:
    """The best near-verbatim match of ``span`` in ``source``, or None.

    None when the span is verbatim (that is a good quote), shorter than
    ``min_words`` (too short to tell corruption from coincidence), or further
    than the edit budget from every source window (a paraphrase or a
    fabrication - other classes)."""
    folded_span, folded_source = fold(span).strip(_EDGE), fold(source)
    if not folded_span or folded_span in folded_source:
        return None
    n = len(folded_span.split())
    if n < min_words:
        return None
    limit = budget(folded_span)
    # Each edit destroys at most three trigrams of the quote. Even the whole
    # source must contain the remainder; rejecting below this bound is lossless.
    # This matters when the integrity diagnostic searches the entire store.
    span_grams = Counter(folded_span[i : i + 3] for i in range(len(folded_span) - 2))
    source_grams = Counter(folded_source[i : i + 3] for i in range(len(folded_source) - 2))
    common = sum((span_grams & source_grams).values())
    if common < len(folded_span) - 2 - 3 * limit:
        return None
    words = folded_source.split()
    best: NearVerbatim | None = None
    for size in (n - 1, n, n + 1):
        for window in _windows(words, size):
            # An edit changes at most one common character. This lossless bound
            # avoids dynamic-programming work on windows that cannot pass.
            required = max(prefilter, 1 - 2 * limit / (len(folded_span) + len(window)))
            if difflib.SequenceMatcher(None, folded_span, window).quick_ratio() < required:
                continue
            distance = levenshtein(folded_span, window, limit)
            if distance <= limit and (best is None or distance < best.distance):
                best = NearVerbatim(distance=distance, span=folded_span, window=window)
    return best


def edit_kind(
    span: str,
    window: str,
    vocabulary: set[str] | frozenset[str],
    *,
    fold: Callable[[str], str] = _default_fold,
) -> str:
    """Name a near-verbatim edit: ``garbled`` or ``altered``.

    A_AMENDMENT_1 split. ``garbled``: a differing token of the span is not a word
    in the store's vocabulary, or the edit lies inside a word (the differing
    tokens still share most of their characters). ``altered``: every difference
    is a whole-word substitution by another real word. Both are diagnostics -
    neither grounds a quote."""
    spans = [w.strip(_EDGE) for w in fold(span).split()]
    wins = [w.strip(_EDGE) for w in fold(window).split()]
    matcher = difflib.SequenceMatcher(None, spans, wins, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        for word in spans[i1:i2]:
            if word and word not in vocabulary:
                return "garbled"
        if op == "replace" and i2 - i1 == j2 - j1:
            for a, b in zip(spans[i1:i2], wins[j1:j2], strict=True):
                longer = max(len(a), len(b))
                if longer > 3 and levenshtein(a, b, longer) <= longer // 3:
                    return "garbled"
    return "altered"


__all__ = ["NearVerbatim", "default_budget", "edit_kind", "levenshtein", "near_verbatim"]
