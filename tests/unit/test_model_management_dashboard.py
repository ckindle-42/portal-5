"""portal5_model_management.json: valid JSON whose PromQL names only guard metrics."""

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
DASHBOARD = _REPO / "config/grafana/dashboards/portal5_model_management.json"
METRICS_SOURCE = _REPO / "portal/platform/inference/router/metrics.py"

#: Histogram exposition adds these suffixes to the declared base name.
_SUFFIXES = ("", "_total", "_bucket", "_count", "_sum", "_created")


def _declared_guard_metrics() -> set[str]:
    """The portal5_load_guard_* collectors router/metrics.py declares."""
    return set(re.findall(r'"(portal5_load_guard_[a-z_]+)"', METRICS_SOURCE.read_text()))


def _exprs() -> list[str]:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    return [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets") or []
        if target.get("expr")
    ]


def test_dashboard_json_loads_with_provisioning_fields():
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "portal5-model-management"
    assert dashboard["schemaVersion"] == 38
    assert dashboard["panels"]


def test_every_promql_references_a_metric_the_guard_declares():
    declared = _declared_guard_metrics()
    assert declared
    exprs = _exprs()
    assert len(exprs) >= 6
    for expr in exprs:
        named = set(re.findall(r"portal5_[a-z_]+", expr))
        assert named, f"no portal5 metric in {expr}"
        unknown = {
            name
            for name in named
            if not any(name == d + suffix for d in declared for suffix in _SUFFIXES)
        }
        assert not unknown, f"{expr} references undeclared metrics {unknown}"


def test_each_required_quantity_has_a_panel():
    joined = "\n".join(_exprs())
    for fragment in (
        "portal5_load_guard_admissions_total",
        "portal5_load_guard_refusals_total",
        "portal5_load_guard_wait_seconds_bucket",
        "portal5_load_guard_unloads_total",
        "portal5_load_guard_headroom_bytes",
        "portal5_load_guard_ceiling_bytes",
    ):
        assert fragment in joined
