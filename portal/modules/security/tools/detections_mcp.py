"""Portal 5 — SPL Detections MCP Tool Server.

Queryable tool surface for the SPL detection library, field mappings,
and detection validation.  Turns passive metadata into active tools.

Port: 8932 (configurable via DETECTIONS_MCP_PORT env var; bumped from 8930 to resolve Incalmo collision)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── MCP Server Setup ─────────────────────────────────────────────────────────
_port = int(os.environ.get("DETECTIONS_MCP_PORT") or os.environ.get("MCP_PORT", "8932"))

mcp = FastMCP(
    "Portal SPL Detection Tools",
    host="0.0.0.0",
    instructions="Queryable SPL detection library: search, validate, explain, "
    "and diff detections against hypotheses. Structured, not RAG.",
    port=_port,
)

# ── Lazy imports for bench_security ──────────────────────────────────────────

_bench_path = str(
    Path(__file__).resolve().parent.parent.parent.parent.parent / "tests" / "benchmarks"
)


def _ensure_bench_path() -> None:
    if _bench_path not in sys.path:
        sys.path.insert(0, _bench_path)


# ── Tool Manifest ────────────────────────────────────────────────────────────

TOOLS_MANIFEST = [
    {
        "name": "spl_search_library",
        "description": "Search the SPL detection library by keyword or technique ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keyword or technique ID)",
                },
                "top_k": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "spl_validate_syntax",
        "description": "Validate SPL syntax locally (no live Splunk call needed).",
        "parameters": {
            "type": "object",
            "properties": {"spl": {"type": "string", "description": "SPL query to validate"}},
            "required": ["spl"],
        },
    },
    {
        "name": "spl_explain_detection",
        "description": "Explain a detection: logic, mappings, expected signal.",
        "parameters": {
            "type": "object",
            "properties": {
                "technique_id": {"type": "string", "description": "ATT&CK technique ID"}
            },
            "required": ["technique_id"],
        },
    },
    {
        "name": "spl_techniques_covered",
        "description": "List all technique IDs with SPL detections.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "spl_diff_hypothesis",
        "description": "Compare an SPL result against an expected signal to find matches, misses, and unexpected findings.",
        "parameters": {
            "type": "object",
            "properties": {
                "technique_id": {"type": "string", "description": "ATT&CK technique ID"},
                "observed_signal": {
                    "type": "string",
                    "description": "What was actually observed in telemetry",
                },
            },
            "required": ["technique_id", "observed_signal"],
        },
    },
]


# ── HTTP Routes ──────────────────────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "detections-mcp", "port": _port})


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


# ── Tool Implementations ─────────────────────────────────────────────────────


@mcp.tool()
def spl_search_library(query: str, top_k: int = 10) -> dict:
    """Search the SPL detection library by keyword or technique ID.

    Args:
        query: search query (keyword like "kerberos" or technique ID like "T1558.003")
        top_k: max results (default 10)

    Returns:
        dict with matching detections.
    """
    _ensure_bench_path()
    from portal.modules.security.core.siem.spl_detections import spl_for, technique_reference

    ref = technique_reference()
    query_upper = query.strip().upper()
    results = []

    for tid, desc in ref.items():
        # Match by technique ID or keyword in description
        if query_upper in tid.upper() or query.lower() in desc.lower():
            spl = spl_for(tid)
            results.append(
                {
                    "technique_id": tid,
                    "description": desc,
                    "spl": spl or "",
                    "has_spl": spl is not None,
                }
            )
            if len(results) >= top_k:
                break

    # Exact technique ID match takes priority
    if query_upper in ref:
        exact_spl = spl_for(query_upper)
        exact = {
            "technique_id": query_upper,
            "description": ref[query_upper],
            "spl": exact_spl or "",
            "has_spl": exact_spl is not None,
        }
        # Move to front if not already there
        if not any(r["technique_id"] == query_upper for r in results[:1]):
            results.insert(0, exact)

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@mcp.tool()
def spl_validate_syntax(spl: str) -> dict:
    """Validate SPL syntax locally (no live Splunk call needed).

    Args:
        spl: SPL query to validate

    Returns:
        dict with ok (bool) and errors (list).
    """
    errors: list[str] = []

    if not spl or not spl.strip():
        return {"ok": False, "errors": ["empty SPL"]}

    stripped = spl.strip()

    if stripped.startswith("#"):
        return {"ok": False, "errors": ["SPL is a placeholder comment, not a real query"]}

    has_index = "index=" in stripped or "index " in stripped
    has_pipe = "|" in stripped
    has_search = stripped.startswith("search ") or has_index or has_pipe

    if not has_search:
        errors.append("SPL lacks a search command or index reference")

    # Check for common syntax issues
    if stripped.count('"') % 2 != 0:
        errors.append("unmatched double quotes")

    if stripped.count("(") != stripped.count(")"):
        errors.append("unmatched parentheses")

    return {"ok": len(errors) == 0, "errors": errors}


@mcp.tool()
def spl_explain_detection(technique_id: str) -> dict:
    """Explain a detection: logic, mappings, expected signal.

    Args:
        technique_id: ATT&CK technique ID

    Returns:
        dict with detection explanation.
    """
    _ensure_bench_path()
    from portal.modules.security.core.siem.spl_detections import spl_for, technique_reference

    ref = technique_reference()
    tid = technique_id.strip().upper()

    if tid not in ref:
        return {"error": f"No detection for {tid}", "technique_id": tid}

    spl = spl_for(tid)
    return {
        "technique_id": tid,
        "description": ref.get(tid, ""),
        "spl": spl or "",
        "has_spl": spl is not None,
        "expected_signal": f"Evidence of {tid} activity in indexed telemetry",
    }


@mcp.tool()
def spl_techniques_covered() -> dict:
    """List all technique IDs with SPL detections.

    Returns:
        dict with list of covered technique IDs.
    """
    _ensure_bench_path()
    from portal.modules.security.core.siem.spl_detections import techniques_covered

    covered = techniques_covered()
    return {
        "count": len(covered),
        "techniques": sorted(covered),
    }


@mcp.tool()
def spl_diff_hypothesis(technique_id: str, observed_signal: str) -> dict:
    """Compare an SPL detection's expected signal against what was observed.

    Finds matches, misses, and unexpected findings.

    Args:
        technique_id: ATT&CK technique ID
        observed_signal: what was actually observed in telemetry

    Returns:
        dict with diff results.
    """
    _ensure_bench_path()
    from portal.modules.security.core.siem.spl_detections import spl_for, technique_reference

    ref = technique_reference()
    tid = technique_id.strip().upper()

    if tid not in ref:
        return {"error": f"No detection for {tid}", "technique_id": tid}

    expected = ref.get(tid, "")
    spl = spl_for(tid) or ""

    # Simple keyword overlap analysis
    expected_words = set(expected.lower().split())
    observed_words = set(observed_signal.lower().split())
    matched = expected_words & observed_words
    missed = expected_words - observed_words
    unexpected = observed_words - expected_words

    return {
        "technique_id": tid,
        "expected_signal": expected,
        "observed_signal": observed_signal,
        "matched_keywords": sorted(matched),
        "missed_keywords": sorted(missed),
        "unexpected_keywords": sorted(unexpected),
        "has_spl": spl is not None,
        "overlap_ratio": round(len(matched) / max(len(expected_words), 1), 2),
    }


# ── Serve ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
