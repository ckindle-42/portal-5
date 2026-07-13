"""Unit test: tests.uat.skips._run_via_dispatcher forwards route_params as
URL query params on the direct-to-pipeline POST.

BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3 / TASK_UAT_CATALOG_RECONCILE_V1
discovery finding: Open WebUI mediates the browser-driven UAT test path
(owui_create_chat addresses a model preset by slug; OWUI — not the test
driver — makes the actual pipeline POST), so a query param set by the test
driver never rides along for browser tests. The only dispatch path that
builds the pipeline request directly is `_run_via_dispatcher` (the
Telegram/Slack bot code path), so retired-alias UAT tests needing an
explicit ``?variant=``/``?model=`` param are routed through it. This test
locks down that the param plumbing actually reaches the outgoing request.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.uat.skips import _run_via_dispatcher


@pytest.mark.asyncio
async def test_run_via_dispatcher_forwards_route_params():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("tests.uat.skips.httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await _run_via_dispatcher(
            workspace="auto-security",
            prompt="hello",
            timeout=30,
            route_params={"variant": "redteam-deep"},
        )

    assert result == "ok"
    call_args = mock_client.post.call_args
    assert "/v1/chat/completions" in call_args[0][0]
    assert call_args[1]["json"]["model"] == "auto-security"
    assert call_args[1]["params"] == {"variant": "redteam-deep"}


@pytest.mark.asyncio
async def test_run_via_dispatcher_no_route_params_passes_none():
    """Omitting route_params (the pre-existing bot-dispatch call shape) must
    still work — params=None is a no-op query string for httpx."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("tests.uat.skips.httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await _run_via_dispatcher(workspace="auto", prompt="hi", timeout=30)

    call_args = mock_client.post.call_args
    assert call_args[1]["params"] is None


def test_runner_forwards_test_route_params_to_dispatcher():
    """The runner's via_dispatcher branch must pass test['route_params']
    through to _run_via_dispatcher (not silently drop it)."""
    import inspect

    from tests.uat import runner

    src = inspect.getsource(runner.run_test)
    assert 'route_params=test.get("route_params")' in src, (
        "runner.run_test's via_dispatcher call must forward test['route_params']"
    )


if __name__ == "__main__":
    asyncio.run(test_run_via_dispatcher_forwards_route_params())
