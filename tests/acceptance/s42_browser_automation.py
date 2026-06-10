"""S42: M5 browser automation — MCP service health and tool count."""
import os
import time

from tests.acceptance._common import (
    _get_acc_client,
    record,
)


async def run() -> None:
    """S42: M5 browser automation — MCP service health and tool count."""
    print("\n━━━ S42. M5 BROWSER AUTOMATION ━━━")
    sec = "S42"

    browser_mcp_url = os.environ.get("BROWSER_MCP_URL", "http://localhost:8923")

    # S42-01: Browser MCP health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{browser_mcp_url}/health", timeout=10)
        if r.status_code == 200:
            data = r.json()
            record(
                sec,
                "S42-01",
                "Browser MCP health",
                "PASS",
                f"status={data.get('status')}, profiles={len(data.get('profiles', []))}",
                t0=t0,
            )
        else:
            record(sec, "S42-01", "Browser MCP health", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(
            sec,
            "S42-01",
            "Browser MCP health",
            "WARN",
            f"not running (expected if browser MCP not started): {str(e)[:60]}",
            t0=t0,
        )

    # S42-02: Browser MCP tools manifest
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{browser_mcp_url}/tools", timeout=10)
        if r.status_code == 200:
            tools = r.json()
            tool_names = [t["name"] for t in tools]
            expected = [
                "browser_navigate",
                "browser_snapshot",
                "browser_click",
                "browser_fill",
                "browser_screenshot",
                "browser_close",
            ]
            missing = [n for n in expected if n not in tool_names]
            if not missing:
                record(
                    sec,
                    "S42-02",
                    "Browser MCP tools",
                    "PASS",
                    f"{len(tools)} tools: {', '.join(tool_names[:4])}...",
                    t0=t0,
                )
            else:
                record(
                    sec, "S42-02", "Browser MCP tools", "WARN", f"missing tools: {missing}", t0=t0
                )
        else:
            record(sec, "S42-02", "Browser MCP tools", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(
            sec,
            "S42-02",
            "Browser MCP tools",
            "WARN",
            f"not running (expected if browser MCP not started): {str(e)[:60]}",
            t0=t0,
        )


# ══════════════════════════════════════════════════════════════════════════════
# S60: M2 Tool-Calling Orchestration
# ══════════════════════════════════════════════════════════════════════════════
