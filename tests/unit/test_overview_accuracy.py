"""The overview dashboard must reflect real pipeline usage, not a 5-minute window.

Two contracts meet here. The dashboard may only query metrics the pipeline emits
on a path real traffic takes, and a counter may only be read through
``rate()``/``increase()`` — the pipeline restarts often and every counter starts
again at zero. At the source, one served turn is one persona count, one model
call is one ``portal_requests_by_model_total`` sample even when the engine sends
no usage frame, and ``portal_concurrent_requests`` is summed across workers.
"""

from __future__ import annotations

import json
import re
import typing
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.auth import PIPELINE_API_KEY
from portal.platform.inference.router.metrics import _REGISTRY

_REPO = Path(__file__).resolve().parents[2]
_DASHBOARD = _REPO / "config/grafana/dashboards/portal5_overview.json"
_METRICS_SOURCE = _REPO / "portal/platform/inference/router/metrics.py"

#: Written straight into the /metrics text by handlers.metrics(), not the registry.
_HANDROLLED = {
    "portal_backends_healthy",
    "portal_backends_total",
    "portal_uptime_seconds",
    "portal_workspaces_total",
}

#: Shared palette with portal5_orchestrate_usage.json; red is direction-only.
_FIXED_COLOURS = {"#199e70", "#c98500", "#3987e5", "#d95926", "#d55181"}
_THRESHOLD_COLOURS = {"#199e70", "#c98500", "red"}

#: Histogram exposition adds these to the declared base name.
_HISTOGRAM_SUFFIXES = ("_bucket", "_count", "_sum", "_created")


def _dashboard() -> dict[str, typing.Any]:
    return json.loads(_DASHBOARD.read_text(encoding="utf-8"))


def _targets() -> list[tuple[dict[str, typing.Any], dict[str, typing.Any]]]:
    return [
        (panel, target)
        for panel in _dashboard()["panels"]
        for target in panel.get("targets") or []
        if isinstance(target.get("expr"), str)
    ]


def _declared_metrics() -> set[str]:
    return set(
        re.findall(r'"((?:portal|portal5|persona)_[a-z0-9_]+)"', _METRICS_SOURCE.read_text())
    )


def _declared_counters() -> set[str]:
    return set(re.findall(r'Counter\(\s*"([a-z0-9_]+)"', _METRICS_SOURCE.read_text()))


def _known_metric(name: str) -> bool:
    if name in _HANDROLLED or name in _declared_metrics():
        return True
    return any(
        name == base + suffix for suffix in _HISTOGRAM_SUFFIXES for base in _declared_metrics()
    )


def _sample(metric: str, **labels: str) -> float:
    return _REGISTRY.get_sample_value(metric, labels) or 0.0


def _declarations() -> dict[str, str]:
    """Collector metric name -> the Python variable router/metrics.py declares it as."""
    pattern = re.compile(r'(\w+)\s*=\s*(?:Counter|Gauge|Histogram)\(\s*"([a-z0-9_]+)"')
    return {name: var for var, name in pattern.findall(_METRICS_SOURCE.read_text())}


def _pipeline_source() -> str:
    """Every portal module except the router_pipe facade, whose imports record nothing."""
    return "\n".join(
        path.read_text()
        for path in (_REPO / "portal").rglob("*.py")
        if path.name != "router_pipe.py"
    )


# ── dashboard contract ───────────────────────────────────────────────


def test_dashboard_is_valid_provisioning_json_with_unique_panel_ids() -> None:
    dashboard = _dashboard()
    assert dashboard["uid"] == "portal5-overview"
    assert dashboard["schemaVersion"] == 38
    ids = [panel["id"] for panel in dashboard["panels"]]
    assert len(ids) == len(set(ids)), f"duplicate panel ids: {ids}"


def test_every_query_names_a_metric_the_pipeline_emits() -> None:
    for panel, target in _targets():
        names = set(re.findall(r"\b(?:portal|portal5|persona)_[a-z0-9_]+", target["expr"]))
        unknown = {name for name in names if not _known_metric(name)}
        assert not unknown, f"{panel['title']!r} queries undeclared metrics {unknown}"


def test_every_queried_collector_is_recorded_somewhere() -> None:
    """A declared collector that nothing records is a permanently empty panel."""
    declarations = _declarations()
    source = _pipeline_source()
    for panel, target in _targets():
        names = set(re.findall(r"\b(?:portal|portal5|persona)_[a-z0-9_]+", target["expr"]))
        for name in names - _HANDROLLED:
            base = next(
                (
                    candidate
                    for candidate in (name, *(name.removesuffix(s) for s in _HISTOGRAM_SUFFIXES))
                    if candidate in declarations
                ),
                None,
            )
            assert base, f"{panel['title']!r} queries undeclared {name}"
            variable = re.escape(declarations[base])
            recorded = re.search(
                rf"{variable}\.(?:labels|inc|observe|set|dec)\b",
                source,
            )
            assert recorded, (
                f"{panel['title']!r} queries {name}, but {declarations[base]} is only "
                "declared, never recorded"
            )


def test_counters_are_only_read_through_rate_or_increase() -> None:
    counters = _declared_counters()
    assert counters, "no Counter declarations found in router/metrics.py"
    for panel, target in _targets():
        expr = target["expr"]
        for counter in counters:
            for match in re.finditer(re.escape(counter), expr):
                before = expr[: match.start()].rstrip()
                assert before.endswith(("rate(", "increase(")), (
                    f"{panel['title']!r} reads counter {counter} without rate()/increase(): {expr}"
                )


def test_session_totals_are_range_based() -> None:
    exprs = [target["expr"] for _, target in _targets()]
    assert "sum(increase(portal_requests_total[$__range]))" in exprs
    assert "sum(increase(portal_errors_total[$__range]))" in exprs
    assert (
        "topk(10, sum by(model) (increase(portal_requests_by_model_total"
        '{workspace!~"internal-.*"}[$__range])))' in exprs
    )
    assert (
        "topk(10, sum by(model) (increase(portal_output_tokens_total"
        '{workspace!~"internal-.*"}[$__range])))' in exprs
    )
    # No panel may display a raw counter as a total.
    for expr in exprs:
        assert not re.fullmatch(r"sum\(portal_[a-z_]+_total\)", expr), expr


def test_overview_excludes_internal_pipeline_traffic() -> None:
    """Warmup, intent-router and tool-preselect calls are counted but not user traffic."""
    engine_traffic = (
        "portal_decode",
        "portal_answer",
        "portal_output_tokens",
        "portal_input_tokens",
    )
    for panel, target in _targets():
        expr = target["expr"]
        if any(name in expr for name in engine_traffic) or re.search(
            r"portal_(requests_by_model|ttft)_", expr
        ):
            assert 'workspace!~"internal-.*"' in expr, (
                f"{panel['title']!r} mixes internal engine traffic into user metrics: {expr}"
            )


def test_retired_mlx_panels_and_queries_are_gone() -> None:
    dashboard = _dashboard()
    assert not [p for p in dashboard["panels"] if "[RETIRED]" in p.get("title", "")]
    assert not [t["expr"] for _, t in _targets() if "mlx_" in t["expr"]]


def test_load_guard_row_summarises_and_links_to_the_full_panels() -> None:
    dashboard = _dashboard()
    titles = [panel.get("title", "") for panel in dashboard["panels"]]
    assert "Load Guard & No-Answer" in titles
    exprs = "\n".join(target["expr"] for _, target in _targets())
    for fragment in (
        "portal5_load_guard_refusals_total",
        "portal5_load_guard_unloads_total",
        "portal5_load_guard_headroom_bytes",
        "portal5_no_answer_total",
    ):
        assert fragment in exprs
    links = [link for panel in dashboard["panels"] for link in panel.get("links") or []]
    assert any(link["url"] == "/d/portal5-model-management" for link in links)


def test_colours_use_the_shared_palette() -> None:
    for panel in _dashboard()["panels"]:
        defaults = (panel.get("fieldConfig") or {}).get("defaults") or {}
        fixed = (defaults.get("color") or {}).get("fixedColor")
        if fixed is not None:
            assert fixed in _FIXED_COLOURS, f"{panel['title']!r} fixedColor {fixed}"
        for step in (defaults.get("thresholds") or {}).get("steps") or []:
            assert step["color"] in _THRESHOLD_COLOURS, f"{panel['title']!r} step {step}"


# ── source emission ──────────────────────────────────────────────────


@pytest.fixture
def client() -> typing.Iterator[TestClient]:
    import portal.platform.inference.router.handlers as handlers_mod
    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


def test_one_served_turn_is_one_persona_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old pre-dispatch count double-counted every served turn as model="unknown"."""
    from fastapi.responses import JSONResponse

    import portal.platform.inference.router.handlers as handlers_mod

    workspace, served = "auto-daily", "persona-count-model"

    async def capture(*_args: typing.Any, **_kwargs: typing.Any) -> JSONResponse:
        return JSONResponse(
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            headers={"x-portal-route": f"{workspace};fake;{served}"},
        )

    monkeypatch.setattr(handlers_mod, "_try_non_streaming", capture)
    before_served = _sample("persona_usage_total", persona=workspace, model=served)
    before_unknown = _sample("persona_usage_total", persona=workspace, model="unknown")

    response = client.post(
        "/v1/chat/completions",
        json={"model": workspace, "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
    )

    assert response.status_code == 200, response.text
    assert _sample("persona_usage_total", persona=workspace, model=served) - before_served == 1
    assert _sample("persona_usage_total", persona=workspace, model="unknown") == before_unknown


def test_concurrent_requests_gauge_is_summed_across_workers() -> None:
    from portal.platform.inference.router.metrics import _concurrent_requests

    assert _concurrent_requests._multiprocess_mode == "livesum"


def _stream_client(monkeypatch: pytest.MonkeyPatch, *responses: typing.Any) -> MagicMock:
    from tests.unit.test_pipeline_hardening import _serve

    client = MagicMock()
    monkeypatch.setattr(st, "_http_client", client)
    _serve(client, *responses)
    return client


@pytest.mark.anyio
async def test_stream_without_a_usage_frame_still_counts_the_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_pipeline_hardening import _delta, _drain, _Resp

    _stream_client(monkeypatch, _Resp(200, [_delta(content="hello"), "data: [DONE]"]))
    model, workspace = "no-usage-model", "no-usage-ws"
    before_calls = _sample("portal_requests_by_model_total", model=model, workspace=workspace)
    before_tokens = _sample("portal_output_tokens_total", model=model, workspace=workspace)

    await _drain(
        st._stream_from_backend_guarded(
            "http://x/v1/chat/completions",
            {},
            workspace_id=workspace,
            model=model,
            start_time=None,
        )
    )

    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=workspace) - before_calls
        == 1
    )
    assert _sample("portal_output_tokens_total", model=model, workspace=workspace) == before_tokens


@pytest.mark.anyio
async def test_stream_with_a_usage_frame_counts_the_model_call_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.test_pipeline_hardening import _data, _delta, _drain, _Resp

    usage = _data({"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 6}})
    _stream_client(monkeypatch, _Resp(200, [_delta(content="hello"), usage, "data: [DONE]"]))
    model, workspace = "usage-model", "usage-ws"
    before = _sample("portal_requests_by_model_total", model=model, workspace=workspace)

    await _drain(
        st._stream_from_backend_guarded(
            "http://x/v1/chat/completions",
            {},
            workspace_id=workspace,
            model=model,
            start_time=None,
        )
    )

    assert _sample("portal_requests_by_model_total", model=model, workspace=workspace) - before == 1
