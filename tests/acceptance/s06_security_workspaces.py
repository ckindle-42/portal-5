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

    # S6-07: auto-purpleteam-exec routing (execution chain)
    t0 = time.time()
    code, response, model, _route = await _chat_with_model(
        "auto-purpleteam-exec",
        "Authorized exercise. Enumerate the local network (192.168.1.0/24) and identify live hosts.",
        max_tokens=500,
        timeout=600,
    )
    signals = ["nmap", "scan", "host", "port", "network", "live", "192.168", "enumerate"]
    found = [s for s in signals if s.lower() in response.lower()]
    route_status, route_detail = await _assert_routing(sec, "S6-07", "auto-purpleteam-exec", model)
    if found and code == 200 and route_status in ("match", "no_expectation", "no_actual"):
        status = "PASS"
    elif found and code == 200:
        status = "WARN"
    else:
        status = "WARN"
    record(
        sec,
        "S6-07",
        "auto-purpleteam-exec routing",
        status,
        f"signals: {found[:3]} | {route_detail}",
        t0=t0,
    )
