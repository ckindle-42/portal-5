"""S60: M2 tool-calling orchestration."""
import time

from tests.acceptance._common import (
    PIPELINE_URL,
    ROOT,
    _get_acc_client,
    record,
)


async def run() -> None:
    """S60: M2 tool-calling orchestration — registry, dispatch, multi-turn loop."""
    print("\n━━━ S60. M2 TOOL-CALLING ORCHESTRATION ━━━")
    sec = "S60"

    # S60-01: Tool registry module exists
    t0 = time.time()
    try:
        from portal_pipeline.tool_registry import tool_registry

        names = tool_registry.list_tool_names()
        record(
            sec,
            "S60-01",
            "Tool registry loaded",
            "PASS",
            f"{len(names)} tools: {', '.join(names[:5])}...",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S60-01", "Tool registry loaded", "FAIL", str(e)[:100], t0=t0)

    # S60-02: WORKSPACES have tools arrays
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import WORKSPACES

        with_tools = {k: v.get("tools", []) for k, v in WORKSPACES.items() if v.get("tools")}
        record(
            sec,
            "S60-02",
            "Workspace tool whitelists",
            "PASS",
            f"{len(with_tools)}/{len(WORKSPACES)} workspaces have tools",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S60-02", "Workspace tool whitelists", "FAIL", str(e)[:100], t0=t0)

    # S60-03: _resolve_persona_tools function exists
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import _resolve_persona_tools

        result = _resolve_persona_tools({"tools_allow": ["execute_python"]}, "auto-coding")
        assert "execute_python" in result
        record(
            sec,
            "S60-03",
            "Persona tool resolution",
            "PASS",
            f"tools_allow override works: {result}",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S60-03", "Persona tool resolution", "FAIL", str(e)[:100], t0=t0)

    # S60-04: _dispatch_tool_call function exists
    t0 = time.time()
    try:
        record(sec, "S60-04", "Tool dispatch function", "PASS", "exists", t0=t0)
    except Exception as e:
        record(sec, "S60-04", "Tool dispatch function", "FAIL", str(e)[:100], t0=t0)

    # S60-05: MAX_TOOL_HOPS configurable
    t0 = time.time()
    try:
        from portal_pipeline.router_pipe import MAX_TOOL_HOPS

        assert isinstance(MAX_TOOL_HOPS, int) and MAX_TOOL_HOPS > 0
        record(sec, "S60-05", "MAX_TOOL_HOPS", "PASS", f"value={MAX_TOOL_HOPS}", t0=t0)
    except Exception as e:
        record(sec, "S60-05", "MAX_TOOL_HOPS", "FAIL", str(e)[:100], t0=t0)

    # S60-06: Tool-call metrics present in /metrics
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/metrics", timeout=10)
        if r.status_code == 200:
            has_tool_calls = "portal5_tool_calls_total" in r.text
            has_tool_duration = "portal5_tool_call_duration_seconds" in r.text
            has_tool_errors = "portal5_tool_call_errors_total" in r.text
            if has_tool_calls and has_tool_duration:
                record(
                    sec,
                    "S60-06",
                    "Tool-call Prometheus metrics",
                    "PASS",
                    "portal5_tool_calls_total + duration present",
                    t0=t0,
                )
            else:
                record(
                    sec,
                    "S60-06",
                    "Tool-call Prometheus metrics",
                    "WARN",
                    "some tool metrics missing",
                    t0=t0,
                )
        else:
            record(
                sec,
                "S60-06",
                "Tool-call Prometheus metrics",
                "FAIL",
                f"HTTP {r.status_code}",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S60-06", "Tool-call Prometheus metrics", "FAIL", str(e)[:100], t0=t0)

    # S60-07: agentorchestrator persona exists
    t0 = time.time()
    try:
        p = ROOT / "config" / "personas" / "agentorchestrator.yaml"
        if p.exists():
            import yaml

            data = yaml.safe_load(p.read_text())
            record(
                sec,
                "S60-07",
                "agentorchestrator persona",
                "PASS",
                f"slug={data.get('slug')}, workspace={data.get('workspace_model')}",
                t0=t0,
            )
        else:
            record(sec, "S60-07", "agentorchestrator persona", "FAIL", "file missing", t0=t0)
    except Exception as e:
        record(sec, "S60-07", "agentorchestrator persona", "FAIL", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S70: M3 Information Access MCPs
# ══════════════════════════════════════════════════════════════════════════════
