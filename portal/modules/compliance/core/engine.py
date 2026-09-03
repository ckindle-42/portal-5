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

import re
from collections.abc import Callable

from portal.modules.compliance.core.cip_register import Register, RegisterNode

# ── temporal filter ──────────────────────────────────────────────────────────


def effective_parts(reg: Register, effective_on: str) -> list[RegisterNode]:
    """Register nodes enforceable on ``effective_on`` (ISO ``YYYY-MM-DD``).

    A node is enforceable when: its lifecycle is not retired/pre-adoption, its
    ``valid_from`` (if set) is on or before the date, and its ``valid_to`` (if
    set) is strictly after it. ``BOARD_ADOPTED`` / ``FERC_APPROVED`` /
    ``FUTURE_EFFECTIVE`` are excluded here (they belong to "what's coming")."""
    out = []
    for n in reg.nodes:
        if n.lifecycle_state != "EFFECTIVE":
            continue
        if n.valid_from and n.valid_from > effective_on:
            continue
        if n.valid_to and n.valid_to <= effective_on:
            continue
        out.append(n)
    return out


def future_effective_parts(reg: Register, as_of: str) -> list[RegisterNode]:
    """Nodes adopted/approved but not yet enforceable as of ``as_of`` — the
    "what's coming" set. Visible BEFORE the enforcement date, not after."""
    out = []
    for n in reg.nodes:
        if (
            n.lifecycle_state in ("BOARD_ADOPTED", "FERC_APPROVED", "FUTURE_EFFECTIVE")
            or n.lifecycle_state == "EFFECTIVE"
            and n.valid_from
            and n.valid_from > as_of
        ):
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
