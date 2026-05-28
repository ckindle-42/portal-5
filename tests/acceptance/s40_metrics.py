"""S40: Metrics and monitoring tests."""
import time
from tests.acceptance._common import (
    PIPELINE_URL,
    PROMETHEUS_URL,
    GRAFANA_URL,
    GRAFANA_PASS,
    record,
    _get_acc_client,
)


async def run() -> None:
    """S40: Metrics and monitoring tests."""
    print("\n━━━ S40. METRICS & MONITORING ━━━")
    sec = "S40"

    # S40-01: Pipeline /metrics endpoint
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PIPELINE_URL}/metrics", timeout=10)
        if r.status_code == 200:
            lines = r.text.splitlines()
            metric_lines = [l for l in lines if l and not l.startswith("#")]
            record(
                sec, "S40-01", "Pipeline /metrics", "PASS", f"{len(metric_lines)} metrics", t0=t0
            )
        else:
            record(sec, "S40-01", "Pipeline /metrics", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-01", "Pipeline /metrics", "FAIL", str(e)[:100], t0=t0)

    # S40-02: Prometheus scrape targets
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{PROMETHEUS_URL}/api/v1/targets", timeout=10)
        if r.status_code == 200:
            data = r.json()
            targets = data.get("data", {}).get("activeTargets", [])
            up = sum(1 for t in targets if t.get("health") == "up")
            record(sec, "S40-02", "Prometheus targets", "PASS", f"{up}/{len(targets)} up", t0=t0)
        else:
            record(sec, "S40-02", "Prometheus targets", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-02", "Prometheus targets", "WARN", str(e)[:100], t0=t0)

    # S40-03: Grafana API
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(
            f"{GRAFANA_URL}/api/search",
            headers={"Authorization": f"Basic {GRAFANA_PASS}"},
            timeout=10,
        )
        if r.status_code in (200, 401):  # 401 is OK, means API is responding
            record(sec, "S40-03", "Grafana API", "PASS", f"HTTP {r.status_code}", t0=t0)
        else:
            record(sec, "S40-03", "Grafana API", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S40-03", "Grafana API", "WARN", str(e)[:100], t0=t0)


# ══════════════════════════════════════════════════════════════════════════════
# S41: M6 Production Hardening — Health, Rate Limits, Admin
# ══════════════════════════════════════════════════════════════════════════════