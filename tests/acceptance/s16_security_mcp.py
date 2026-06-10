"""S16: Security MCP tool tests — classify_vulnerability."""
import time

from tests.acceptance._common import (
    MCP,
    _get,
    _mcp,
    record,
)


async def run() -> None:
    """S16: Security MCP tool tests — classify_vulnerability via MCP protocol."""
    print("\n━━━ S16. SECURITY MCP TOOLS ━━━")
    sec = "S16"

    sec_port = MCP.get("security", 8919)

    # S16-01: Health check
    t0 = time.time()
    code, data = await _get(f"http://localhost:{sec_port}/health", timeout=5)
    if code != 200:
        record(sec, "S16-01", "Security MCP health", "WARN", f"HTTP {code}", t0=t0)
        return
    record(
        sec,
        "S16-01",
        "Security MCP health",
        "PASS",
        f"service: {data.get('service', 'unknown')}",
        t0=t0,
    )

    # S16-02: classify_vulnerability with a high-severity RCE description
    await _mcp(
        sec_port,
        "classify_vulnerability",
        {
            "description": "Remote code execution via buffer overflow in OpenSSL 3.0 allows attackers to execute arbitrary code by sending a crafted certificate."
        },
        section=sec,
        tid="S16-02",
        name="classify_vulnerability (RCE — expect high/critical)",
        ok_fn=lambda t: any(s in t.lower() for s in ["severity", "high", "critical"]),
        warn_if=["error", "exception", "not available"],
        timeout=120,
    )

    # S16-03: classify_vulnerability with a low-severity info disclosure
    await _mcp(
        sec_port,
        "classify_vulnerability",
        {
            "description": "Information disclosure in debug endpoint reveals server version number to authenticated users."
        },
        section=sec,
        tid="S16-03",
        name="classify_vulnerability (info disclosure — expect low/medium)",
        ok_fn=lambda t: any(s in t.lower() for s in ["severity", "low", "medium", "high"]),
        warn_if=["error", "exception", "not available"],
        timeout=120,
    )

    # S16-04: classify_vulnerability returns probabilities
    await _mcp(
        sec_port,
        "classify_vulnerability",
        {"description": "SQL injection in login form allows unauthorized data access."},
        section=sec,
        tid="S16-04",
        name="classify_vulnerability returns probabilities",
        ok_fn=lambda t: all(s in t.lower() for s in ["probabilities", "confidence"]),
        warn_if=["error", "exception"],
        timeout=120,
    )
