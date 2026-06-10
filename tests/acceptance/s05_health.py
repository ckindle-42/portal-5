"""S5: Code sandbox tests."""
import time

from tests.acceptance._common import (
    MCP,
    _get,
    _mcp,
    record,
)


async def run() -> None:
    """S5: Code sandbox tests."""
    print("\n━━━ S5. CODE SANDBOX ━━━")
    sec = "S5"

    # S5-01: Sandbox health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['sandbox']}/health")
    record(
        sec, "S5-01", "Sandbox MCP health", "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0
    )

    # S5-02: Execute Python code (tool: execute_python)
    await _mcp(
        MCP["sandbox"],
        "execute_python",
        {
            "code": "print(sum(range(1, 11)))",
        },
        section=sec,
        tid="S5-02",
        name="Execute Python (sum 1-10)",
        ok_fn=lambda t: "55" in t,
        timeout=60,
    )

    # S5-03: Execute with list comprehension
    await _mcp(
        MCP["sandbox"],
        "execute_python",
        {
            "code": "result = [x**2 for x in range(5)]\nprint(result)",
        },
        section=sec,
        tid="S5-03",
        name="Execute Python (list comprehension)",
        ok_fn=lambda t: "[0, 1, 4, 9, 16]" in t or "0, 1, 4, 9, 16" in t,
        timeout=60,
    )
