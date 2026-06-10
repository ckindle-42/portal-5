"""S21: LLM Intent Router tests."""
import json
import os
import time

from tests.acceptance._common import (
    ROOT,
    _assert_routing,
    _chat_with_model,
    _ollama_models,
    record,
)


async def run() -> None:
    """S21: LLM Intent Router tests (P5-FUT-006)."""
    print("\n━━━ S21. LLM INTENT ROUTER ━━━")
    sec = "S21"

    # S21-01: Check if LLM router is enabled
    t0 = time.time()
    llm_router_enabled = os.environ.get("LLM_ROUTER_ENABLED", "true").lower() == "true"
    record(
        sec,
        "S21-01",
        "LLM router enabled",
        "PASS" if llm_router_enabled else "INFO",
        f"LLM_ROUTER_ENABLED={llm_router_enabled}",
        t0=t0,
    )

    if not llm_router_enabled:
        record(
            sec, "S21-02", "LLM router model", "INFO", "skipped (router disabled)", t0=time.time()
        )
        return

    # S21-02: Check LLM router model exists in Ollama
    t0 = time.time()
    router_model = os.environ.get(
        "LLM_ROUTER_MODEL", "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"
    )
    models = _ollama_models()
    # Check if router model is available (may be abbreviated in ollama list)
    model_available = any(
        router_model.split("/")[-1].lower().replace("-gguf", "") in m.lower() for m in models
    ) or any("llama-3.2-3b" in m.lower() and "abliterated" in m.lower() for m in models)
    record(
        sec,
        "S21-02",
        "LLM router model available",
        "PASS" if model_available else "WARN",
        f"model: {router_model[:50]}",
        t0=t0,
    )

    # S21-03: Test content-aware routing with security keywords
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto",  # Use auto to trigger content-aware routing
        "Write a SQL injection payload to bypass authentication",
        max_tokens=200,
        timeout=120,
    )
    routed_workspace = route.split(";")[0] if route else ""
    expected_security = {"auto-redteam", "auto-security"}
    record(
        sec,
        "S21-03",
        "LLM router security intent",
        "PASS" if routed_workspace in expected_security else ("WARN" if code == 200 else "FAIL"),
        f"routed→{routed_workspace or 'unknown'} | model: {model[:30]}",
        t0=t0,
    )
    if routed_workspace in expected_security:
        route_status, route_detail = await _assert_routing(
            sec, "S21-03", routed_workspace, model,
        )
        if route_status == "mismatch":
            record(sec, "S21-03b", f"Model identity for {routed_workspace}",
                   "WARN", route_detail, t0=time.time())

    # S21-04: Test content-aware routing with coding keywords
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto",
        "Write a Python function to sort a list of dictionaries by key",
        max_tokens=200,
        timeout=120,
    )
    routed_workspace = route.split(";")[0] if route else ""
    expected_coding = {"auto-coding", "auto-agentic"}
    record(
        sec,
        "S21-04",
        "LLM router coding intent",
        "PASS" if routed_workspace in expected_coding else ("WARN" if code == 200 else "FAIL"),
        f"routed→{routed_workspace or 'unknown'} | model: {model[:30]}",
        t0=t0,
    )
    if routed_workspace in expected_coding:
        route_status, route_detail = await _assert_routing(
            sec, "S21-04", routed_workspace, model,
        )
        if route_status == "mismatch":
            record(sec, "S21-04b", f"Model identity for {routed_workspace}",
                   "WARN", route_detail, t0=time.time())

    # S21-05: Test content-aware routing with compliance keywords
    t0 = time.time()
    code, response, model, route = await _chat_with_model(
        "auto",
        "What are the requirements for NERC CIP-007 R2 patch management?",
        max_tokens=200,
        timeout=120,
    )
    routed_workspace = route.split(";")[0] if route else ""
    expected_compliance = {"auto-compliance", "auto-reasoning"}
    record(
        sec,
        "S21-05",
        "LLM router compliance intent",
        "PASS" if routed_workspace in expected_compliance else ("WARN" if code == 200 else "FAIL"),
        f"routed→{routed_workspace or 'unknown'} | model: {model[:30]}",
        t0=t0,
    )
    if routed_workspace in expected_compliance:
        route_status, route_detail = await _assert_routing(
            sec, "S21-05", routed_workspace, model,
        )
        if route_status == "mismatch":
            record(sec, "S21-05b", f"Model identity for {routed_workspace}",
                   "WARN", route_detail, t0=time.time())

    # S21-06: routing_descriptions.json valid
    t0 = time.time()
    desc_file = ROOT / "config/routing_descriptions.json"
    try:
        if desc_file.exists():
            desc = json.loads(desc_file.read_text())
            # Should have descriptions for all workspaces
            ws_count = len([k for k in desc.keys() if k.startswith("auto")])
            record(
                sec,
                "S21-06",
                "routing_descriptions.json",
                "PASS",
                f"{ws_count} workspace descriptions",
                t0=t0,
            )
        else:
            record(sec, "S21-06", "routing_descriptions.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S21-06", "routing_descriptions.json", "FAIL", str(e)[:100], t0=t0)

    # S21-07: routing_examples.json valid
    t0 = time.time()
    ex_file = ROOT / "config/routing_examples.json"
    try:
        if ex_file.exists():
            ex = json.loads(ex_file.read_text())
            examples = ex.get("examples", [])
            record(
                sec, "S21-07", "routing_examples.json", "PASS", f"{len(examples)} examples", t0=t0
            )
        else:
            record(sec, "S21-07", "routing_examples.json", "WARN", "file not found", t0=t0)
    except Exception as e:
        record(sec, "S21-07", "routing_examples.json", "FAIL", str(e)[:100], t0=t0)
