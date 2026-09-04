"""Shared text signals for span classification.

Split out of ``planted.py`` (TASK_COMPLIANCE_ENGINE_LANDING_V1 P2) so the real
retrieval proposer (``propose.py``) and the planted-corpus proposer share one
"does this span substantively restate the obligation" check instead of two
copies drifting apart.
"""

from __future__ import annotations

import re

STOP_WORDS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "for",
    "and",
    "or",
    "in",
    "on",
    "at",
    "by",
    "with",
    "is",
    "are",
    "be",
    "shall",
    "must",
    "each",
    "entity",
    "that",
    "this",
    "as",
    "from",
    "within",
    "its",
    "it",
    "applicable",
    "responsible",
    "processes",
    "process",
    "include",
    "documented",
}


def keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9-]{4,}", text.lower()) if w not in STOP_WORDS}


ASPIRATIONAL_RE = re.compile(
    r"\b(strive to|strives to|endeavor to|endeavors to|as appropriate|where feasible|"
    r"where practical|best effort|encouraged to|periodic(?:ally)?|from time to time)\b",
    re.I,
)


def is_aspirational(body: str) -> bool:
    """Aspirational language with no numeric commitment — names an intent, not
    an auditable obligation. `"we strive to review periodically"` vs a 15-day
    rule."""
    return bool(ASPIRATIONAL_RE.search(body)) and not re.search(
        r"\b\d+\s+(calendar |business )?(day|days|month|months|hour|hours|year|years)\b", body, re.I
    )
