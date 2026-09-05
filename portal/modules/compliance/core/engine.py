"""Temporal filtering + intent routing (T3 Phase 2).

**Filtering, not scoring.** ``effective_on`` is applied as a predicate before
ranking — a retired requirement never reaches a "what must we do today" query.

**Four routed paths, one classification call** — not an agent swarm. Eight-plus
sequential model calls fit neither an 8192-token input budget nor a stack where
a single search costs ~52 s. The classifier is a keyword scorer by default (no
model dependency on the deterministic path); a caller may pass its own
``classify`` for the LLM route.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable

from portal.modules.compliance.core.cip_register import Register, RegisterNode

# ── temporal filter ──────────────────────────────────────────────────────────

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_iso_date(value: str, *, field: str = "date") -> str:
    """Validate an ISO-8601 calendar date (``YYYY-MM-DD``).

    TASK_COMPLIANCE_REASONING_V2 P1.4: "Reject invalid ISO dates and ambiguous
    revision prefixes." A malformed or absent date must fail loudly — it must
    never silently resolve to "today", an empty selection, or a default that
    looks like a real answer.
    """
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value or ""):
        raise ValueError(f"invalid ISO date for {field}: {value!r} (expected YYYY-MM-DD)")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date for {field}: {value!r}") from exc
    return value


_PROSPECTIVE_STATES = ("BOARD_ADOPTED", "FERC_APPROVED", "FUTURE_EFFECTIVE")


def _is_enforceable_at(n: RegisterNode, effective_on: str) -> bool:
    """Interval-based selection (F01): a node is enforceable at
    ``effective_on`` iff its known validity interval
    ``[valid_from, valid_to)`` covers that date — independent of its CURRENT
    lifecycle *label*. A node labelled ``RETIRED`` today was still
    enforceable during its own historical interval; a historical query must
    still find it. A node with no known ``valid_from`` is never treated as
    currently effective — unknown effectivity is unknown, not a default
    inclusion (F02)."""
    if not n.valid_from:
        return False
    if n.valid_from > effective_on:
        return False
    return not (n.valid_to and n.valid_to <= effective_on)


def effective_parts(reg: Register, effective_on: str) -> list[RegisterNode]:
    """Register nodes enforceable on ``effective_on`` (ISO ``YYYY-MM-DD``),
    selected by validity INTERVAL rather than by the current lifecycle label
    (F01) — a retired node is still returned for a historical date inside its
    own ``[valid_from, valid_to)``. Raises ``ValueError`` for a malformed
    date rather than silently matching zero nodes."""
    parse_iso_date(effective_on, field="effective_on")
    return [n for n in reg.nodes if _is_enforceable_at(n, effective_on)]


def unknown_effectivity_parts(reg: Register) -> list[RegisterNode]:
    """Nodes whose effective date is unknown/unset (F02) — an unrecognized
    version defaults here, not to ``EFFECTIVE``. Never returned by
    ``effective_parts``/``future_effective_parts``; must stay visible so a
    "current" answer can be qualified rather than silently complete."""
    return [n for n in reg.nodes if not n.valid_from]


def future_effective_parts(reg: Register, as_of: str) -> list[RegisterNode]:
    """Nodes adopted/approved but not yet enforceable as of ``as_of`` — the
    "what's coming" set. Date-derived (F01): a ``BOARD_ADOPTED`` /
    ``FERC_APPROVED`` / ``FUTURE_EFFECTIVE`` node whose ``valid_from`` has
    already passed has moved into ``effective_parts`` and drops out of this
    set — the lifecycle label alone no longer decides membership, only the
    date does."""
    parse_iso_date(as_of, field="as_of")
    out = []
    for n in reg.nodes:
        if n.lifecycle_state in _PROSPECTIVE_STATES:
            if n.valid_from and n.valid_from <= as_of:
                continue  # already enforceable now — belongs to effective_parts
            out.append(n)
        elif n.lifecycle_state == "EFFECTIVE" and n.valid_from and n.valid_from > as_of:
            out.append(n)
    return out


# ── intent routing ──────────────────────────────────────────────────────────
INTENTS = ("today", "change", "gaps", "freeform")

_INTENT_CUES = {
    "today": [
        r"\btoday\b",
        r"currently (enforceable|required|in effect)",
        r"what must we do",
        r"right now",
        r"as of (today|now)",
        r"in effect",
    ],
    "change": [
        r"what('?s| is) (coming|changing|new)",
        r"future[- ]effective",
        r"upcoming",
        r"changed between",
        r"new version",
        r"what changed",
        r"revision",
        r"supersed",
    ],
    "gaps": [
        r"\bgap analysis\b",
        r"where are (our|the) gaps",
        r"coverage (matrix|analysis)",
        r"are we (covered|compliant)",
        r"which requirements? (do|don't) we",
        r"audit prep",
    ],
}


def classify_intent(query: str) -> str:
    """One classification. Keyword scorer — ties and no-match fall to freeform."""
    q = query.lower()
    scores = {k: sum(bool(re.search(p, q)) for p in pats) for k, pats in _INTENT_CUES.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "freeform"


def route(
    query: str,
    reg: Register,
    effective_on: str,
    *,
    classify: Callable[[str], str] | None = None,
) -> dict:
    """Dispatch to one path. Returns the routing decision + the filtered node set
    the downstream path operates on (retrieval / mapping / coverage happen in
    their own modules)."""
    intent = (classify or classify_intent)(query)
    if intent == "today":
        nodes = effective_parts(reg, effective_on)
    elif intent == "change":
        nodes = future_effective_parts(reg, effective_on)
    elif intent == "gaps":
        nodes = effective_parts(reg, effective_on)  # applicability-gated in coverage.py
    else:
        nodes = []  # freeform: retrieval over policy/procedure, no register enumeration
    return {
        "intent": intent,
        "effective_on": effective_on,
        "n_nodes_in_path": len(nodes),
        "node_ids": [n.id for n in nodes],
        "path": {
            "today": "filter EFFECTIVE at date -> retrieve -> mapping store -> answer",
            "change": "register diff -> traverse IMPLEMENTED_BY -> impacted policy",
            "gaps": "enumerate applicable parts -> align -> coverage matrix",
            "freeform": "retrieve over policy/procedure, standard answer",
        }[intent],
    }
