"""S24: Specialist MLX models (Foundation-Sec + ToolACE-2.5)."""
import asyncio
import time
from tests.acceptance._common import (
    MCP,
    MLX_URL,
    record,
    _assert_routing,
    _chat_with_model,
    _get,
    _mlx_health,
)

async def run() -> None:
    """S24: Specialist MLX models — Foundation-Sec (auto-blueteam) and ToolACE-2.5 (tools-specialist).

    Both are locally-converted 8B MLX models promoted to production in May 2026.
    Foundation-Sec: defender-side cybersecurity (CVE/CWE, MITRE ATT&CK, SOC triage).
    ToolACE-2.5: structured function/API call composition (BFCL-topping).
    """
    print("\n━━━ S24. SPECIALIST MLX MODELS ━━━")
    sec = "S24"

    # S24-01: MLX proxy must be reachable — skip all if not
    t0 = time.time()
    state, _ = await _mlx_health()
    if state == "unreachable":
        record(sec, "S24-01", "MLX proxy for specialist models", "INFO", "MLX proxy not running", t0=t0)
        return
    record(sec, "S24-01", "MLX proxy for specialist models", "PASS", f"state: {state}", t0=t0)

    # S24-02: Foundation-Sec registered in MLX model list
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    foundation_sec_present = False
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        foundation_sec_present = any("Foundation-Sec" in m for m in model_ids)
    record(
        sec,
        "S24-02",
        "Foundation-Sec-8B registered in MLX",
        "PASS" if foundation_sec_present else "INFO",
        f"Foundation-Sec in MLX models: {foundation_sec_present}",
        t0=t0,
    )

    # S24-03: Foundation-Sec smoke test via auto-blueteam workspace
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto-blueteam",
        "A SOC alert fires: 10 failed SSH logins from 185.220.101.5 followed by a success. "
        "What is the most likely attack, and what are your first two containment steps?",
        max_tokens=350,
        timeout=300,
    )
    signals = ["brute", "credential", "ssh", "block", "isolat", "contain", "firewall", "quarantin"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S24-03", "auto-blueteam", model)
    if found and code == 200:
        status = "PASS" if route_status in ("match", "no_expectation", "no_actual") else "WARN"
    else:
        status = "WARN"
    record(
        sec, "S24-03", "Foundation-Sec via auto-blueteam",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )

    # S24-04: Foundation-Sec CVE → CWE mapping (defender-side domain knowledge)
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-blueteam",
        "CVE-2021-44228 (Log4Shell): what is the root CWE and which MITRE ATT&CK technique does it enable?",
        max_tokens=300,
        timeout=300,
    )
    signals = ["CWE-917", "CWE-502", "log4j", "JNDI", "T1190", "T1203", "remote code", "deseri"]
    found = [s for s in signals if s.lower() in response.lower()]
    record(
        sec, "S24-04", "Foundation-Sec CVE/CWE/ATT&CK knowledge",
        "PASS" if len(found) >= 2 and code == 200 else "WARN",
        f"signals ({len(found)}): {found[:4]}",
        t0=t0,
    )

    # S24-05: ToolACE-2.5 registered in MLX model list
    t0 = time.time()
    code, models_data = await _get(f"{MLX_URL}/v1/models")
    toolace_present = False
    if code == 200 and isinstance(models_data, dict):
        model_ids = [m.get("id", "") for m in models_data.get("data", [])]
        toolace_present = any("ToolACE" in m for m in model_ids)
    record(
        sec,
        "S24-05",
        "ToolACE-2.5-8B registered in MLX",
        "PASS" if toolace_present else "INFO",
        f"ToolACE in MLX models: {toolace_present}",
        t0=t0,
    )

    # Tools definitions matching the tools-specialist workspace MCP functions
    _TOOLACE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": "Execute Python code in a sandboxed environment and return stdout/stderr.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python source code to execute"},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": "Store a key-value pair in persistent memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "recall",
                "description": "Retrieve a value from persistent memory by key.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                    },
                    "required": ["key"],
                },
            },
        },
    ]

    # S24-06: ToolACE-2.5 smoke test — send real tools array, expect tool_call response
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "tools-specialist",
        "Use the execute_python tool to compute the sum of numbers 1 through 10.",
        tools=_TOOLACE_TOOLS,
        max_tokens=300,
        timeout=300,
    )
    # Accept: OpenAI tool_calls JSON (from _chat_with_model serialization), ToolACE func() syntax,
    # or natural-language description of the call — all confirm the model understood the tools schema.
    signals_toolcall = ["execute_python", "tool_calls", "function_call", "func(", "\"name\""]
    signals_fallback = ["code", "sum", "range", "python", "call", "function", "tool"]
    found_tc = [s for s in signals_toolcall if s.lower() in response.lower()]
    found_fb = [s for s in signals_fallback if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S24-06", "tools-specialist", model)
    if code == 200 and found_tc:
        # Model emitted a structured tool call — strong confirmation
        status = "PASS" if route_status in ("match", "no_expectation", "no_actual") else "WARN"
        detail = f"tool-call signals: {found_tc[:3]} | {route_detail}"
    elif code == 200 and found_fb:
        # Model responded in natural language but acknowledged the tool — acceptable
        status = "WARN"
        detail = f"no tool-call format; fallback signals: {found_fb[:3]} | {route_detail}"
    else:
        status = "WARN"
        detail = f"HTTP {code} | no signals | {route_detail}"
    record(sec, "S24-06", "ToolACE-2.5 via tools-specialist (structured tools)", status, detail, t0=t0)

    # S24-07: ToolACE-2.5 multi-step tool chain — expect sequential calls using tools schema
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "tools-specialist",
        "I need to execute Python code that computes a list of even numbers from 1–20, "
        "then store the result in memory under the key 'even_numbers'. "
        "Make the necessary tool calls in order.",
        tools=_TOOLACE_TOOLS,
        max_tokens=400,
        timeout=300,
    )
    # Expect the model to reference both execute_python and remember in its response
    signals_steps = ["execute_python", "remember", "even", "result", "store", "memory",
                     "tool_calls", "function_call", "func("]
    found = [s for s in signals_steps if s.lower() in response.lower()]
    record(
        sec, "S24-07", "ToolACE-2.5 multi-step tool chain (execute + remember)",
        "PASS" if len(found) >= 2 and code == 200 else "WARN",
        f"signals ({len(found)}): {found[:5]}",
        t0=t0,
    )
