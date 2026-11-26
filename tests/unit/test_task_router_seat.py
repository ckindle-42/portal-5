"""The OWUI task seat stays addressable while the eval module is off."""

from __future__ import annotations

import pytest

from portal.platform.inference.config import (
    TASK_MODEL_WORKSPACE,
    get_workspace_dict,
    load_portal_config,
)
from portal.platform.wiki.adapters.modules import is_workspace_disabled, preset_ids


@pytest.fixture
def eval_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORTAL_ENABLE_EVAL", raising=False)
    monkeypatch.delenv("PORTAL_BENCH_WORKSPACES", raising=False)


def test_task_router_is_served_when_eval_is_off(eval_off: None) -> None:
    del eval_off
    config = load_portal_config(_force_reload=True)
    assert config.modules["eval"].enabled is False
    seat = config.workspaces[TASK_MODEL_WORKSPACE]
    assert seat.module == "eval"
    assert seat.router is False
    assert seat.expose_to_owui is False
    runtime = get_workspace_dict(config)
    assert TASK_MODEL_WORKSPACE in runtime
    assert runtime[TASK_MODEL_WORKSPACE]["model_hint"].endswith("-ctx2k")
    assert runtime[TASK_MODEL_WORKSPACE]["context_limit"] == 2048
    assert runtime[TASK_MODEL_WORKSPACE]["think"] is False
    assert runtime[TASK_MODEL_WORKSPACE]["temperature"] == 0.2
    assert is_workspace_disabled(TASK_MODEL_WORKSPACE, config=config) is False
    assert TASK_MODEL_WORKSPACE not in preset_ids(config)


def test_task_router_is_not_an_auto_route_label() -> None:
    from portal.platform.inference.router.routing import _VALID_WORKSPACE_IDS

    assert TASK_MODEL_WORKSPACE not in _VALID_WORKSPACE_IDS
