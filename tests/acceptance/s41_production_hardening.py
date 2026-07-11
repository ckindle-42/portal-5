"""S41: M6 production hardening tests."""

import os
import time

from tests.acceptance._common import (
    PIPELINE_URL,
    ROOT,
    _get_acc_client,
    record,
)


async def run() -> None:
    """S41: M6 production hardening tests — /health/all, rate limiting, admin endpoints."""
    print("\n━━━ S41. M6 PRODUCTION HARDENING ━━━")
    sec = "S41"

    # S41-01: /health/all aggregator
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/health/all", timeout=15)
        if r.status_code == 200:
            checks = r.json()
            services = list(checks.keys())
            ok_count = sum(
                1 for v in checks.values() if isinstance(v, dict) and v.get("status") == "ok"
            )
            record(
                sec,
                "S41-01",
                "/health/all aggregator",
                "PASS",
                f"{ok_count}/{len(services)} services ok: {', '.join(services[:5])}",
                t0=t0,
            )
        else:
            record(sec, "S41-01", "/health/all aggregator", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S41-01", "/health/all aggregator", "FAIL", str(e)[:100], t0=t0)

    # S41-02: Workspace concurrency config (bench-* should be 1)
    t0 = time.time()
    try:
        from portal.platform.inference.router_pipe import (
            WORKSPACES,
            _get_workspace_concurrency_limit,
        )

        bench_ok = True
        for wsid in sorted(WORKSPACES.keys()):
            if wsid.startswith("bench-"):
                limit = _get_workspace_concurrency_limit(wsid)
                if limit != 1:
                    bench_ok = False
                    record(
                        sec,
                        "S41-02",
                        "bench-* concurrency=1",
                        "WARN",
                        f"{wsid} limit={limit}, expected 1",
                        t0=t0,
                    )
                    # Continue checking all bench workspaces, don't break
        if bench_ok:
            bench_count = sum(1 for k in WORKSPACES if k.startswith("bench-"))
            record(
                sec,
                "S41-02",
                "bench-* concurrency=1",
                "PASS",
                f"all {bench_count} bench-* workspaces capped at 1",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S41-02", "bench-* concurrency=1", "FAIL", str(e)[:100], t0=t0)

    # S41-03: /admin/refresh-tools endpoint exists
    t0 = time.time()
    try:
        c = _get_acc_client()
        api_key = os.environ.get("PIPELINE_API_KEY", "")
        r = await c.post(
            f"{PIPELINE_URL}/admin/refresh-tools",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            record(
                sec,
                "S41-03",
                "/admin/refresh-tools",
                "PASS",
                f"{data.get('tools_registered', 0)} tools registered",
                t0=t0,
            )
        else:
            record(sec, "S41-03", "/admin/refresh-tools", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S41-03", "/admin/refresh-tools", "FAIL", str(e)[:100], t0=t0)

    # S41-04: Power metrics gauges present in /metrics
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/metrics", timeout=10)
        if r.status_code == 200:
            has_power = "portal5_power_current_watts" in r.text
            has_energy = "portal5_energy_consumed_watt_seconds_total" in r.text
            if has_power and has_energy:
                record(
                    sec,
                    "S41-04",
                    "Power metrics in /metrics",
                    "PASS",
                    "portal5_power_* and portal5_energy_* present",
                    t0=t0,
                )
            else:
                missing = []
                if not has_power:
                    missing.append("portal5_power_current_watts")
                if not has_energy:
                    missing.append("portal5_energy_consumed_watt_seconds_total")
                record(
                    sec,
                    "S41-04",
                    "Power metrics in /metrics",
                    "WARN",
                    f"missing: {', '.join(missing)}",
                    t0=t0,
                )
        else:
            record(
                sec, "S41-04", "Power metrics in /metrics", "FAIL", f"HTTP {r.status_code}", t0=t0
            )
    except Exception as e:
        record(sec, "S41-04", "Power metrics in /metrics", "FAIL", str(e)[:100], t0=t0)

    # S41-05: Workspace count matches config (27)
    t0 = time.time()
    try:
        import yaml

        from portal.platform.inference.router_pipe import WORKSPACES

        cfg = yaml.safe_load(open(ROOT / "config" / "backends.yaml"))
        yaml_ids = set(cfg.get("workspace_routing", {}).keys())
        pipe_ids = set(WORKSPACES.keys())
        if yaml_ids == pipe_ids:
            record(
                sec,
                "S41-05",
                "Workspace consistency",
                "PASS",
                f"{len(pipe_ids)} workspaces, pipe+yaml match",
                t0=t0,
            )
        else:
            diff = yaml_ids.symmetric_difference(pipe_ids)
            record(sec, "S41-05", "Workspace consistency", "FAIL", f"mismatch: {diff}", t0=t0)
    except Exception as e:
        record(sec, "S41-05", "Workspace consistency", "FAIL", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S42: M5 Browser Automation — MCP Service Check
# ══════════════════════════════════════════════════════════════════════════════
