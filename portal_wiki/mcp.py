"""Portal Wiki MCP tools — agent-native retrieval.

Tools: wiki.search, wiki.get_unit, wiki.explain
All answers RETURN their citations (grounded, not hallucinated).
"""

from __future__ import annotations

import logging
import re as _re
from typing import Any

from portal.platform.wiki.store import load_all, load_unit

logger = logging.getLogger(__name__)


# Kind-based ranking tiers for wiki_search. The flat keyword score treats a
# design unit and a test-section unit identically on equal keyword evidence, so
# "workspace routing" surfaced `unit-acceptance-s03_routing` (a UAT section)
# ahead of `unit-router-routing` (the routing design). A unit's kind is a signal
# about how load-bearing it is for the answer: design/architecture units explain
# *why* and *how* a subsystem works; test-section and derived units record *that*
# a check exists. Tiers apply as a tie-break on top of the keyword score.
_KIND_TIERS = {
    "why": 1.0,  # design rationale — highest-value for a reader
    "mixed": 0.5,  # architecture + interface
    "what": 0.0,  # factual description
}
_KIND_DEFAULT = 0.0

# Tag boosts: a verified/authored unit has been walked against code this program
# (TASK_WIKI_ZERO_DEBT_V1), so its prose is grounded; test-section units are
# distinguished by their `-s0*_` id suffix and get no boost.
_TAG_BOOST = ("verified-v1", "authored-v1")

# Acceptance/UAT section units (`unit-acceptance-s03_routing`) and other
# test-harness units record that a check exists, not how the subsystem works.
# They share the `mixed` kind with the design unit they shadow, so a stable
# sort would keep them on top of an equal tie. Demote them explicitly.
_SECTION_UNIT_RE = _re.compile(r"-s\d{2}_|^unit-(?:acceptance|uat)-|test-|^unit-tests-")


def _section_penalty(unit_id: str) -> float:
    return -2.0 if _SECTION_UNIT_RE.search(unit_id) else 0.0


def _kind_weight(kind: str) -> float:
    return _KIND_TIERS.get(kind, _KIND_DEFAULT)


def _tag_weight(tags: list[str]) -> float:
    return 0.5 if any(t in tags for t in _TAG_BOOST) else 0.0


def wiki_search(query: str, top_k: int = 10) -> dict[str, Any]:
    """Search the canonical knowledge layer by keyword.

    Ranking is the keyword score (title 2x, tag 1.5x, body 1x) plus a kind
    tier and a verification boost, so a design unit outranks a test-section
    unit on equal keyword evidence. Test-section units (`-s0*` acceptance
    sections) are the classic false-positive top hit; the kind tier demotes
    them behind the subsystem unit that explains the behaviour.

    Args:
        query: search query (keyword or phrase)
        top_k: max results (default 10)

    Returns:
        dict with matching units and their citations.
    """
    units = load_all()
    query_words = query.lower().split()
    results = []

    for unit in units:
        score = 0.0
        title_lower = unit.title.lower()
        body_lower = unit.body.lower()

        for word in query_words:
            if word in title_lower:
                score += 2.0
            if word in body_lower:
                score += 1.0
            if any(word in tag.lower() for tag in unit.tags):
                score += 1.5

        if score > 0:
            results.append(
                {
                    "unit_id": unit.id,
                    "title": unit.title,
                    "kind": unit.kind,
                    "score": round(score, 3),
                    "rank": round(
                        score
                        + _kind_weight(unit.kind)
                        + _tag_weight(unit.tags)
                        + _section_penalty(unit.id),
                        3,
                    ),
                    "sources": [s.to_dict() for s in unit.sources],
                    "preview": unit.body[:200] + "..." if len(unit.body) > 200 else unit.body,
                }
            )

    results.sort(key=lambda r: (r["rank"], r["score"]), reverse=True)
    return {
        "query": query,
        "count": min(len(results), top_k),
        "results": results[:top_k],
    }


def wiki_get_unit(unit_id: str) -> dict[str, Any]:
    """Get a specific knowledge unit by ID.

    Args:
        unit_id: the unit ID (e.g. "unit-T1190-signature")

    Returns:
        dict with full unit content and citations.
    """
    unit = load_unit(unit_id)
    if not unit:
        return {"error": f"Unit '{unit_id}' not found"}

    return {
        "unit_id": unit.id,
        "title": unit.title,
        "kind": unit.kind,
        "body": unit.body,
        "sources": [s.to_dict() for s in unit.sources],
        "confidence": unit.confidence,
        "tags": unit.tags,
    }


def wiki_explain(query: str) -> dict[str, Any]:
    """Explain something by searching the canonical layer and returning
    a cited answer.

    Args:
        query: what to explain (e.g. "T1003.006 windows telemetry signature")

    Returns:
        dict with answer text and source citations.
    """
    search_result = wiki_search(query, top_k=3)
    if not search_result["results"]:
        return {
            "query": query,
            "answer": f"No knowledge found for: {query}",
            "sources": [],
        }

    top = search_result["results"]
    answer_parts = []
    all_sources = []
    for r in top:
        answer_parts.append(f"**{r['title']}** ({r['kind']}): {r['preview']}")
        all_sources.extend(r["sources"])

    return {
        "query": query,
        "answer": "\n\n".join(answer_parts),
        "sources": all_sources,
        "units_referenced": [r["unit_id"] for r in top],
    }
