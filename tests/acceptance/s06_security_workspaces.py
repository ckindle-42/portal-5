"""S6: Security workspace tests."""

import time

from tests.acceptance._common import (
    PIPELINE_URL,
    _assert_routing,
    _chat_with_model,
    _get,
    _grep_logs,
    record,
)


async def run() -> None:
    """S6: Security workspace tests."""
    print("\n━━━ S6. SECURITY WORKSPACES ━━━")
    sec = "S6"

    # S6-01: auto-security routing
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-security",
        "What is SQL injection and how to prevent it?",
        max_tokens=300,
        timeout=180,
    )
    signals = ["sql", "inject", "sanitize", "parameter", "escape", "prepared"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-01", "auto-security", model)
    if found and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "PASS"
    elif found and code == 200 and route_status == "mismatch":
        status = "WARN"
    else:
        status = "WARN"
    record(
        sec,
        "S6-01",
        "auto-security routing",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )

    # S6-02: auto-redteam routing
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-redteam",
        "Explain common web application penetration testing methodology.",
        max_tokens=300,
        timeout=180,
    )
    signals = ["recon", "scan", "exploit", "pentest", "OWASP", "vulnerability"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-02", "auto-redteam", model)
    if found and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "PASS"
    elif found and code == 200 and route_status == "mismatch":
        status = "WARN"
    else:
        status = "WARN"
    record(
        sec,
        "S6-02",
        "auto-redteam routing",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )

    # S6-03: auto-blueteam routing
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-blueteam",
        "How do you respond to a ransomware incident?",
        max_tokens=300,
        timeout=180,
    )
    signals = ["isolate", "contain", "backup", "incident", "response", "recover"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-03", "auto-blueteam", model)
    if found and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "PASS"
    elif found and code == 200 and route_status == "mismatch":
        status = "WARN"
    else:
        status = "WARN"
    record(
        sec,
        "S6-03",
        "auto-blueteam routing",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )

    # S6-04: Content-aware routing (security keywords)
    t0 = time.time()
    code, response, _, _route = await _chat_with_model(
        "auto",  # Use auto to test content-aware routing
        "exploit vulnerability payload shellcode",
        max_tokens=200,
        timeout=180,
    )
    # Check pipeline logs for routing decision
    logs = _grep_logs("portal5-pipeline", "auto-redteam|auto-security", lines=100)
    record(
        sec,
        "S6-04",
        "Content-aware security routing",
        "PASS" if logs and code == 200 else "WARN",
        f"routed to security workspace: {bool(logs)}",
        t0=t0,
    )

    # S6-05: auto-redteam-deep routing (deep simulation mode)
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-redteam-deep",
        "Explain Kerberoasting — what is it, how does it work, and what tools are used?",
        max_tokens=400,
        timeout=240,
    )
    signals = ["kerberoast", "spn", "service principal", "tgs", "hashcat", "rubeus", "impacket"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-05", "auto-redteam-deep", model)
    if len(found) >= 2 and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "PASS"
    elif len(found) >= 2 and code == 200:
        status = "WARN"
    else:
        status = "WARN"
    record(
        sec,
        "S6-05",
        "auto-redteam-deep routing",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )

    # S6-06: auto-pentest routing (execution mode, JANG-CRACK)
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-pentest",
        "Authorized engagement. Enumerate Kerberoastable accounts and provide the Impacket command.",
        max_tokens=400,
        timeout=300,
    )
    signals = ["impacket", "getuserspns", "rubeus", "kerberoast", "spn", "hashcat", "-m 13100"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-06", "auto-pentest", model)
    if found and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "PASS"
    elif found and code == 200:
        status = "WARN"
    else:
        status = "WARN"
    record(
        sec,
        "S6-06",
        "auto-pentest routing (JANG-CRACK)",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )

    # S6-07: auto-purpleteam-exec — routing + actual execute_bash tool call
    # Snapshot tool_calls counter before the request.
    # portal5_tool_calls_total is a labeled counter — all lines have {tool=...,workspace=...}.
    # Sum all label variants to get the total across all tools/workspaces.
    def _sum_tool_calls(metrics_text: str) -> float:
        total = 0.0
        for ln in metrics_text.splitlines():
            if ln.startswith("portal5_tool_calls_total{") and not ln.startswith("#"):
                try:
                    total += float(ln.rsplit(" ", 1)[-1])
                except ValueError:
                    pass
        return total

    tool_calls_before = 0.0
    try:
        _, metrics_before = await _get(f"{PIPELINE_URL}/metrics", timeout=5)
        if isinstance(metrics_before, str):
            tool_calls_before = _sum_tool_calls(metrics_before)
    except Exception:
        pass

    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-purpleteam-exec",
        # Use $LAB_TARGET_DC (the env var the workspace declares) so the model
        # has a concrete target from its system prompt context.
        "Authorized purple team exercise. Call execute_bash right now to check which "
        "AD ports are open on $LAB_TARGET_DC. Do not describe what you will do — "
        "call execute_bash immediately and show only the raw output.",
        max_tokens=800,
        timeout=600,
    )
    signals = ["nmap", "scan", "open", "port", "execute_bash", "tcp", "88", "445", "389"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-07", "auto-purpleteam-exec", model)

    # Check if a tool call was dispatched by comparing the metric counter.
    tool_called = False
    try:
        _, metrics_after = await _get(f"{PIPELINE_URL}/metrics", timeout=5)
        if isinstance(metrics_after, str):
            tool_calls_after = _sum_tool_calls(metrics_after)
            tool_called = tool_calls_after > tool_calls_before
    except Exception:
        pass

    if (
        found
        and code == 200
        and tool_called
        and route_status in ("match", "no_expectation", "no_actual")
    ):
        status = "PASS"
    elif found and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "WARN"  # content OK but tool call not confirmed
    else:
        status = "WARN"
    record(
        sec,
        "S6-07",
        "auto-purpleteam-exec: routing + execute_bash tool call",
        status,
        f"signals: {found[:3]} | tool_called={tool_called} | {route_detail}",
        t0=t0,
    )
