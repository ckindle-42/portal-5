"""Engine calls outside the main dispatchers are counted once and labelled internal."""

from __future__ import annotations

import pytest

from portal.platform.inference.router.metrics import _REGISTRY
from portal.platform.inference.router.power import (
    INTERNAL_ROUTER_WORKSPACE,
)


def _sample(metric: str, **labels: str) -> float:
    return _REGISTRY.get_sample_value(metric, labels) or 0.0


@pytest.mark.asyncio
async def test_internal_traffic_stays_out_of_daily_digest() -> None:
    from portal.platform.inference.router import state
    from portal.platform.inference.router.power import _record_engine_call

    model = "digest-internal-model"
    before_in = state._total_input_tokens
    before_out = state._total_output_tokens
    before_requests = _sample(
        "portal_requests_by_model_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE
    )

    _record_engine_call(
        model,
        INTERNAL_ROUTER_WORKSPACE,
        {"usage": {"prompt_tokens": 3, "completion_tokens": 4}},
    )

    assert (
        _sample("portal_requests_by_model_total", model=model, workspace=INTERNAL_ROUTER_WORKSPACE)
        - (before_requests)
        == 1
    )
    assert state._total_input_tokens == before_in
    assert state._total_output_tokens == before_out
    assert model not in state._req_count_by_model
