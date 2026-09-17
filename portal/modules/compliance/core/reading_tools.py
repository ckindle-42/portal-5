"""The small, core-only tool surface available to an agentic reading.

The declarations and dispatcher live together so an advertised schema cannot
drift from the callable implementation.  Tool results carry the exact section
ids returned to the model; the reader uses those ids for its closure receipt.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from portal.modules.compliance.core import addressing, graph_queries, reading_assembly

MAX_CHARS = 6000


def _result(payload: dict[str, Any], section_ids: list[str] | None = None) -> dict[str, Any]:
    return {"payload": payload, "section_ids": list(dict.fromkeys(section_ids or []))}


def _bounded(value: Any, max_chars: int) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + f"\n[truncated: {len(value) - max_chars} characters omitted]"
    if isinstance(value, list):
        return [_bounded(item, max_chars) for item in value]
    if isinstance(value, dict):
        return {key: _bounded(item, max_chars) for key, item in value.items()}
    return value


def _resolve(repo: Any, ref: str) -> dict[str, dict[str, Any]]:
    from portal.modules.compliance.core.section_index import resolve_sections

    resolved = resolve_sections(repo, [ref])
    return resolved or addressing.resolve_by_address(repo, ref)


def compliance_search(
    repo: Any,
    query: str,
    jurisdiction: str = "",
    requirement: str = "",
    top_k: int = 10,
) -> dict[str, Any]:
    from portal.modules.compliance.core import section_index
    from portal.modules.compliance.tools.compliance_retrieval import search as retrieve

    addressed = addressing.addressed_hits(repo, query, MAX_CHARS)
    corpora = (
        [section_index.CORPUS_FOR_JURISDICTION[jurisdiction]]
        if jurisdiction in section_index.CORPUS_FOR_JURISDICTION
        else list(dict.fromkeys(section_index.CORPUS_FOR_JURISDICTION.values()))
    )
    hits: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for kb_id in corpora:
        try:
            body = asyncio.run(retrieve(kb_id, query, max(top_k, 3)))
        except Exception as exc:  # noqa: BLE001 - report corpus availability to the agent
            unavailable.append({"kb_id": kb_id, "detail": str(exc)})
            continue
        hits.extend(body.get("results", []))
    resolved = section_index.resolve_sections(repo, [str(hit.get("chunk_id", "")) for hit in hits])
    addressed_ids = {str(hit["section_id"]) for hit in addressed}
    results: list[dict[str, Any]] = list(addressed)
    for hit in sorted(hits, key=lambda row: -float(row.get("fused_score", 0) or 0)):
        section_id = section_index.parent_section_id(str(hit.get("chunk_id", "")))
        entry = resolved.get(section_id)
        if entry is None or section_id in addressed_ids:
            continue
        if requirement:
            wanted = {str(row["section_id"]) for row in repo.sections_for_requirement(requirement)}
            if section_id not in wanted:
                continue
        text, note = addressing.clip(entry.get("text", ""), MAX_CHARS)
        results.append(
            {
                **addressing.provenance(entry),
                "match": "retrieval",
                "score": hit.get("fused_score"),
                "text": text,
                **note,
            }
        )
        if len(results) >= top_k:
            break
    return _result(
        {
            "query": query,
            "requirement": requirement,
            "results": results[:top_k],
            "num_results": len(results[:top_k]),
            "corpora_unavailable": unavailable,
        },
        [str(row["section_id"]) for row in results[:top_k]],
    )


def compliance_read(repo: Any, ref: str, neighbors: bool = False) -> dict[str, Any]:
    resolved = _resolve(repo, ref)
    units: list[dict[str, Any]] = []
    for section_id, entry in sorted(resolved.items(), key=lambda item: item[1].get("ordinal", 0)):
        text, note = addressing.clip(entry.get("text", ""), MAX_CHARS)
        units.append(
            {**addressing.provenance(entry), "section_id": section_id, "text": text, **note}
        )
    payload: dict[str, Any] = {"ref": ref, "resolved": bool(units), "units": units}
    if neighbors and units:
        payload["neighbors"] = addressing.neighbors(repo, next(iter(resolved.values())), MAX_CHARS)
    return _result(payload, [str(unit["section_id"]) for unit in units])


def compliance_requirement(repo: Any, ref: str) -> dict[str, Any]:
    payload = reading_assembly.assemble(
        repo, ref, budget_tokens=12_000, include=["requirement", "measures", "technical_basis"]
    )
    ids = [
        str(section["section_id"])
        for component in payload.get("components", [])
        for section in component.get("sections", [])
    ]
    return _result(payload, ids)


def compliance_links(repo: Any, ref: str, direction: str = "both") -> dict[str, Any]:
    payload = graph_queries.links(repo, ref, direction)
    ids = [
        str(edge.get("dst_ref"))
        for edge in payload.get("edges", [])
        if str(edge.get("dst_ref", "")).startswith(("csection-", "isection-"))
    ]
    return _result(payload, ids)


def compliance_timeline(repo: Any, ref: str) -> dict[str, Any]:
    return _result(graph_queries.timeline(repo, ref), [])


def compliance_notes(repo: Any, subject_ref: str = "") -> dict[str, Any]:
    from portal.modules.compliance.core.notes import notes_for

    notes = notes_for(repo, subject_ref)
    return _result(
        {"subject_ref": subject_ref, "notes": notes}, [str(n["section_id"]) for n in notes]
    )


_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "compliance_search",
        "description": "Find citable regulatory or operator material.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "requirement": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "compliance_read",
        "description": "Read verbatim text at an address, with optional neighbours.",
        "parameters": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "neighbors": {"type": "boolean"}},
            "required": ["ref"],
        },
    },
    {
        "name": "compliance_requirement",
        "description": "Read the requirement, Measures, and Technical Basis packet.",
        "parameters": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "compliance_links",
        "description": "Follow requirement and operator links; proposals stay labelled.",
        "parameters": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "direction": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "compliance_timeline",
        "description": "Inspect revision and effective/known-at timelines.",
        "parameters": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "compliance_notes",
        "description": "Read operator notes for a subject.",
        "parameters": {"type": "object", "properties": {"subject_ref": {"type": "string"}}},
    },
]

TOOL_SCHEMAS = [
    {"type": "function", "function": {**declaration, "parameters": declaration["parameters"]}}
    for declaration in _DECLARATIONS
]
_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "compliance_search": compliance_search,
    "compliance_read": compliance_read,
    "compliance_requirement": compliance_requirement,
    "compliance_links": compliance_links,
    "compliance_timeline": compliance_timeline,
    "compliance_notes": compliance_notes,
}


def dispatch(
    repo: Any, name: str, arguments: dict[str, Any] | None = None, *, max_chars: int = MAX_CHARS
) -> dict[str, Any]:
    """Dispatch one model call without allowing a bad call to kill the loop."""
    fn = _FUNCTIONS.get(name)
    if fn is None:
        return {"payload": {"error": f"unknown tool: {name}"}, "section_ids": [], "error": True}
    args = dict(arguments or {})
    try:
        signature = inspect.signature(fn)
        missing = [
            parameter.name
            for parameter in list(signature.parameters.values())[1:]
            if parameter.default is inspect.Parameter.empty and parameter.name not in args
        ]
        if missing:
            return {
                "payload": {"error": f"missing required argument(s): {', '.join(missing)}"},
                "section_ids": [],
                "error": True,
            }
        result = fn(repo, **args)
        result["payload"] = _bounded(result.get("payload", {}), max_chars)
        result["truncation"] = {"max_chars": max_chars, "stated": True}
        return result
    except Exception as exc:  # noqa: BLE001 - a malformed model call is recoverable
        return {
            "payload": {"error": f"tool {name} failed: {exc}"},
            "section_ids": [],
            "error": True,
        }


__all__ = ["TOOL_SCHEMAS", "dispatch"]
