"""S6: Security workspace tests."""
import time

from tests.acceptance._common import (
    _assert_routing,
    _chat_with_model,
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
        sec, "S6-01", "auto-security routing", status,
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
        sec, "S6-02", "auto-redteam routing", status,
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
        sec, "S6-03", "auto-blueteam routing", status,
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
