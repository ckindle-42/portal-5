"""review.grounding -- every claim cites evidence a deterministic checker can locate.

The compliance core's rule ("a FULL requires a quoted span from both sides that a deterministic
checker can locate in the cited document"), applied to security claims. A model may say
anything; only claims that survive this gate reach an analyst:

* the claim has text and cites at least one evidence id;
* every cited id is an event the reviewer actually showed (or fetched through a pivot);
* an optional ``quote`` appears verbatim -- whitespace- and case-insensitively -- in the
  concatenated text of the cited events.

Dropped claims are counted and reasoned, never silently discarded: the ungrounded-claim rate
is a metric. Pure compute.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import Claim

_WS = re.compile(r"\s+")

#: A quote shorter than this proves nothing (any short token occurs somewhere).
MIN_QUOTE_CHARS = 4


def normalize(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


@dataclass(frozen=True)
class GroundingReport:
    kept: tuple[Claim, ...]
    dropped: tuple[tuple[Claim, str], ...]
    cited: int
    resolved: int

    @property
    def citation_resolution(self) -> float:
        """Resolved citations over all citations made (1.0 when nothing was cited)."""
        return 1.0 if self.cited == 0 else self.resolved / self.cited


def parse_claims(raw: Any) -> tuple[list[Claim], int]:
    """Claims from a model's JSON list, and how many entries were malformed."""
    if not isinstance(raw, list):
        return [], 0 if raw is None else 1
    claims: list[Claim] = []
    malformed = 0
    for item in raw:
        if not isinstance(item, Mapping):
            malformed += 1
            continue
        ids = item.get("evidence_ids")
        if isinstance(ids, str):
            ids = [ids]
        if not isinstance(ids, list):
            ids = []
        quote = item.get("quote")
        claims.append(
            Claim(
                text=str(item.get("text") or "").strip(),
                evidence_ids=tuple(str(i) for i in ids),
                quote=str(quote) if isinstance(quote, str) and quote.strip() else None,
            )
        )
    return claims, malformed


def verify_claims(claims: Sequence[Claim], events: Mapping[str, str]) -> GroundingReport:
    kept: list[Claim] = []
    dropped: list[tuple[Claim, str]] = []
    cited = resolved = 0
    for claim in claims:
        cited += len(claim.evidence_ids)
        known = [i for i in claim.evidence_ids if i in events]
        resolved += len(known)
        if not claim.text:
            dropped.append((claim, "empty_text"))
        elif not claim.evidence_ids:
            dropped.append((claim, "no_evidence"))
        elif len(known) != len(claim.evidence_ids):
            missing = next(i for i in claim.evidence_ids if i not in events)
            dropped.append((claim, f"unknown_evidence:{missing}"))
        elif claim.quote is not None:
            quote = normalize(claim.quote)
            haystack = normalize(" ".join(events[i] for i in claim.evidence_ids))
            if len(quote) < MIN_QUOTE_CHARS:
                dropped.append((claim, "quote_too_short"))
            elif quote not in haystack:
                dropped.append((claim, "quote_not_found"))
            else:
                kept.append(claim)
        else:
            kept.append(claim)
    return GroundingReport(tuple(kept), tuple(dropped), cited, resolved)
