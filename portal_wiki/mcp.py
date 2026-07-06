"""Portal Wiki MCP tools — agent-native retrieval.

Tools: wiki.search, wiki.get_unit, wiki.explain
All answers RETURN their citations (grounded, not hallucinated).
"""

from __future__ import annotations

import logging
from typing import Any

from .core.store import load_all, load_unit

logger = logging.getLogger(__name__)


def wiki_search(query: str, top_k: int = 10) -> dict[str, Any]:
    """Search the canonical knowledge layer by keyword.

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
                    "score": score,
                    "sources": [s.to_dict() for s in unit.sources],
                    "preview": unit.body[:200] + "..." if len(unit.body) > 200 else unit.body,
                }
            )

    results.sort(key=lambda r: r["score"], reverse=True)
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
