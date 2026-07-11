"""Portal 5 — MITRE ATT&CK MCP Tool Server.

Deterministic tool layer for MITRE ATT&CK, D3FEND, and CWE.
Not RAG — structured, versioned, queryable tools.

Port: 8929 (configurable via MITRE_MCP_PORT env var)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── MCP Server Setup ─────────────────────────────────────────────────────────
_port = int(os.environ.get("MITRE_MCP_PORT") or os.environ.get("MCP_PORT", "8929"))

mcp = FastMCP(
    "Portal MITRE ATT&CK Tools",
    host="0.0.0.0",
    instructions="Deterministic MITRE ATT&CK, D3FEND, and CWE lookup tools. "
    "Structured data, not RAG — query by technique ID, get precise results.",
    port=_port,
)

# ── ATT&CK Data Store ────────────────────────────────────────────────────────
# Loaded from the official ATT&CK STIX bundle (Enterprise + ICS).
# For now, use the local spl_detections.yaml + embedded technique metadata
# as the backing store. Full STIX bundle loading is a follow-up.

_TECHNIQUE_DB: dict[str, dict] = {}
_DATA_SOURCES: dict[str, list[str]] = {}
_MITIGATIONS: dict[str, list[dict]] = {}
_LOADED = False


def _ensure_loaded() -> None:
    """Lazy-load technique database from available sources."""
    global _LOADED, _TECHNIQUE_DB, _DATA_SOURCES, _MITIGATIONS
    if _LOADED:
        return

    # Load from spl_detections.yaml (our local detection library)
    try:
        import sys

        bench_path = str(Path(__file__).resolve().parent.parent.parent / "tests" / "benchmarks")
        if bench_path not in sys.path:
            sys.path.insert(0, bench_path)
        from portal.modules.security.core.siem.spl_detections import spl_for, technique_reference

        ref = technique_reference()
        for tid, desc in ref.items():
            spl = spl_for(tid)
            _TECHNIQUE_DB[tid] = {
                "technique_id": tid,
                "name": desc,
                "description": desc,
                "spl": spl or "",
                "has_detection": spl is not None,
            }
    except Exception as e:
        logger.warning("Failed to load spl_detections: %s", e)

    # Embedded ATT&CK technique metadata (subset for key techniques)
    # Full STIX bundle loading deferred to follow-up
    embedded = {
        "T1190": {
            "name": "Exploit Public-Facing Application",
            "tactic": "initial-access",
            "platforms": ["Linux", "Windows", "Network"],
        },
        "T1059": {
            "name": "Command and Scripting Interpreter",
            "tactic": "execution",
            "platforms": ["Linux", "Windows", "macOS"],
        },
        "T1059.004": {"name": "Unix Shell", "tactic": "execution", "platforms": ["Linux", "macOS"]},
        "T1505.003": {
            "name": "Web Shell",
            "tactic": "persistence",
            "platforms": ["Linux", "Windows"],
        },
        "T1003": {
            "name": "OS Credential Dumping",
            "tactic": "credential-access",
            "platforms": ["Linux", "Windows"],
        },
        "T1003.001": {
            "name": "LSASS Memory",
            "tactic": "credential-access",
            "platforms": ["Windows"],
        },
        "T1003.003": {"name": "NTDS", "tactic": "credential-access", "platforms": ["Windows"]},
        "T1003.006": {"name": "DCSync", "tactic": "credential-access", "platforms": ["Windows"]},
        "T1558.003": {
            "name": "Kerberoasting",
            "tactic": "credential-access",
            "platforms": ["Windows"],
        },
        "T1558.004": {
            "name": "AS-REP Roasting",
            "tactic": "credential-access",
            "platforms": ["Windows"],
        },
        "T1078": {
            "name": "Valid Accounts",
            "tactic": "persistence",
            "platforms": ["Linux", "Windows", "macOS", "SaaS"],
        },
        "T1078.004": {
            "name": "Cloud Accounts",
            "tactic": "persistence",
            "platforms": ["Azure AD", "GCP", "AWS"],
        },
        "T1557": {
            "name": "Adversary-in-the-Middle",
            "tactic": "credential-access",
            "platforms": ["Linux", "Windows"],
        },
        "T1557.001": {
            "name": "LLMNR/NBT-NS Poisoning",
            "tactic": "credential-access",
            "platforms": ["Windows"],
        },
        "T1550.002": {
            "name": "Pass the Hash",
            "tactic": "lateral-movement",
            "platforms": ["Windows"],
        },
        "T1021.002": {
            "name": "SMB/Windows Admin Shares",
            "tactic": "lateral-movement",
            "platforms": ["Windows"],
        },
        "T1210": {
            "name": "Exploitation of Remote Services",
            "tactic": "lateral-movement",
            "platforms": ["Linux", "Windows"],
        },
        "T1053.005": {"name": "Scheduled Task", "tactic": "persistence", "platforms": ["Windows"]},
        "T1548.001": {
            "name": "Setuid and Setgid",
            "tactic": "privilege-escalation",
            "platforms": ["Linux"],
        },
        "T1068": {
            "name": "Exploitation for Privilege Escalation",
            "tactic": "privilege-escalation",
            "platforms": ["Linux", "Windows"],
        },
        "T1047": {
            "name": "Windows Management Instrumentation",
            "tactic": "execution",
            "platforms": ["Windows"],
        },
        "T1552": {
            "name": "Unsecured Credentials",
            "tactic": "credential-access",
            "platforms": ["Linux", "Windows"],
        },
        "T1552.005": {
            "name": "Cloud Instance Metadata API",
            "tactic": "credential-access",
            "platforms": ["IaaS"],
        },
        "T1537": {
            "name": "Transfer Data to Cloud Account",
            "tactic": "exfiltration",
            "platforms": ["IaaS"],
        },
        "T1110": {
            "name": "Brute Force",
            "tactic": "credential-access",
            "platforms": ["Linux", "Windows"],
        },
        "T1110.003": {
            "name": "Password Spraying",
            "tactic": "credential-access",
            "platforms": ["Linux", "Windows"],
        },
        "T1083": {
            "name": "File and Directory Discovery",
            "tactic": "discovery",
            "platforms": ["Linux", "Windows"],
        },
        "T1189": {
            "name": "Drive-by Compromise",
            "tactic": "initial-access",
            "platforms": ["Linux", "Windows"],
        },
        "T1203": {
            "name": "Exploitation for Client Execution",
            "tactic": "execution",
            "platforms": ["Linux", "Windows"],
        },
        "T1592": {
            "name": "Gather Victim Host Information",
            "tactic": "reconnaissance",
            "platforms": ["Linux", "Windows"],
        },
        "T1595": {
            "name": "Active Scanning",
            "tactic": "reconnaissance",
            "platforms": ["Linux", "Windows"],
        },
        "T1610": {"name": "Deploy Container", "tactic": "execution", "platforms": ["Containers"]},
        "T1611": {
            "name": "Escape to Host",
            "tactic": "privilege-escalation",
            "platforms": ["Containers"],
        },
    }

    for tid, meta in embedded.items():
        if tid in _TECHNIQUE_DB:
            _TECHNIQUE_DB[tid].update(meta)
        else:
            _TECHNIQUE_DB[tid] = {"technique_id": tid, "has_detection": False, **meta}

    _LOADED = True


# ── Tool Manifest ────────────────────────────────────────────────────────────

TOOLS_MANIFEST = [
    {
        "name": "mitre_technique_lookup",
        "description": "Look up a MITRE ATT&CK technique by ID. Returns name, tactic, platforms, detection info.",
        "parameters": {
            "type": "object",
            "properties": {
                "technique_id": {
                    "type": "string",
                    "description": "ATT&CK technique ID (e.g. T1190, T1558.003)",
                }
            },
            "required": ["technique_id"],
        },
    },
    {
        "name": "mitre_data_sources_for_technique",
        "description": "List data sources needed to detect a technique.",
        "parameters": {
            "type": "object",
            "properties": {
                "technique_id": {"type": "string", "description": "ATT&CK technique ID"}
            },
            "required": ["technique_id"],
        },
    },
    {
        "name": "mitre_detections_for_technique",
        "description": "List local SPL detections for a technique (joins ATT&CK to our detection library).",
        "parameters": {
            "type": "object",
            "properties": {
                "technique_id": {"type": "string", "description": "ATT&CK technique ID"}
            },
            "required": ["technique_id"],
        },
    },
    {
        "name": "mitre_techniques_list",
        "description": "List all known ATT&CK techniques with their metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "tactic": {
                    "type": "string",
                    "description": "Optional tactic filter (e.g. initial-access, credential-access)",
                }
            },
        },
    },
]


# ── HTTP Routes ──────────────────────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "mitre-mcp", "port": _port})


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


# ── Tool Implementations ─────────────────────────────────────────────────────


@mcp.tool()
def mitre_technique_lookup(technique_id: str) -> dict:
    """Look up a MITRE ATT&CK technique by ID.

    Returns name, tactic, platforms, detection availability, and local SPL
    if a detection exists.

    Args:
        technique_id: ATT&CK technique ID (e.g. T1190, T1558.003)

    Returns:
        dict with technique metadata, or error if not found.
    """
    _ensure_loaded()
    tid = technique_id.strip().upper()
    entry = _TECHNIQUE_DB.get(tid)
    if not entry:
        return {"error": f"Technique {tid} not found", "technique_id": tid}
    return {
        "technique_id": tid,
        "name": entry.get("name", entry.get("description", tid)),
        "tactic": entry.get("tactic", "unknown"),
        "platforms": entry.get("platforms", []),
        "has_detection": entry.get("has_detection", False),
        "spl": entry.get("spl", ""),
        "description": entry.get("description", ""),
    }


@mcp.tool()
def mitre_data_sources_for_technique(technique_id: str) -> dict:
    """List data sources needed to detect a technique.

    Maps technique → required telemetry sources (Event IDs, log types, etc.)

    Args:
        technique_id: ATT&CK technique ID

    Returns:
        dict with data sources list.
    """
    _ensure_loaded()
    tid = technique_id.strip().upper()

    # Map techniques to their data sources
    data_source_map = {
        "T1190": ["web:access", "web:server"],
        "T1059": ["process:creation", "command:execution"],
        "T1059.004": ["process:creation", "linux:auditd"],
        "T1505.003": ["web:access", "file:creation"],
        "T1003": ["process:access", "windows:security"],
        "T1003.001": ["process:access", "windows:security"],
        "T1003.003": ["windows:security", "file:access"],
        "T1003.006": ["windows:security", "network:connection"],
        "T1558.003": ["windows:security", "network:connection"],
        "T1558.004": ["windows:security"],
        "T1078": ["authentication:login"],
        "T1078.004": ["cloud:audit"],
        "T1557": ["network:connection", "windows:security"],
        "T1557.001": ["network:connection"],
        "T1550.002": ["windows:security", "network:connection"],
        "T1021.002": ["windows:security", "network:connection"],
        "T1210": ["network:connection", "process:creation"],
        "T1053.005": ["windows:security", "scheduled_task"],
        "T1548.001": ["process:creation", "linux:auditd"],
        "T1068": ["process:creation"],
        "T1047": ["wmi:operation", "process:creation"],
        "T1552": ["file:access"],
        "T1552.005": ["cloud:api"],
        "T1537": ["cloud:storage"],
        "T1110.003": ["authentication:login"],
        "T1083": ["file:access", "process:creation"],
        "T1189": ["web:access", "process:creation"],
        "T1203": ["process:creation"],
        "T1592": ["network:connection"],
        "T1595": ["network:connection"],
        "T1610": ["container:creation"],
        "T1611": ["container:execution", "process:creation"],
    }

    sources = data_source_map.get(tid, [])
    return {
        "technique_id": tid,
        "data_sources": sources,
        "has_local_detection": _TECHNIQUE_DB.get(tid, {}).get("has_detection", False),
    }


@mcp.tool()
def mitre_detections_for_technique(technique_id: str) -> dict:
    """List local SPL detections for a technique.

    Joins ATT&CK technique ID to our local detection library
    (siem/spl_detections.yaml).

    Args:
        technique_id: ATT&CK technique ID

    Returns:
        dict with detection info (SPL, description, expected signal).
    """
    _ensure_loaded()
    tid = technique_id.strip().upper()
    entry = _TECHNIQUE_DB.get(tid, {})

    if not entry.get("has_detection"):
        return {
            "technique_id": tid,
            "has_detection": False,
            "message": f"No local SPL detection for {tid}",
        }

    return {
        "technique_id": tid,
        "has_detection": True,
        "spl": entry.get("spl", ""),
        "description": entry.get("description", ""),
        "expected_signal": entry.get("expected_signal", ""),
    }


@mcp.tool()
def mitre_techniques_list(tactic: str = "") -> dict:
    """List all known ATT&CK techniques with their metadata.

    Args:
        tactic: Optional tactic filter (e.g. "initial-access", "credential-access")

    Returns:
        dict with list of techniques.
    """
    _ensure_loaded()
    techniques = []
    for tid, entry in sorted(_TECHNIQUE_DB.items()):
        if tactic and entry.get("tactic", "") != tactic:
            continue
        techniques.append(
            {
                "technique_id": tid,
                "name": entry.get("name", entry.get("description", tid)),
                "tactic": entry.get("tactic", "unknown"),
                "has_detection": entry.get("has_detection", False),
            }
        )

    return {
        "count": len(techniques),
        "tactic_filter": tactic or "all",
        "techniques": techniques,
    }


# ── Serve ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
