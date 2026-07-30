"""UAT dispatcher URL resolution — the fix for 31 never-executed via_dispatcher cases.

`.env` sets PIPELINE_URL to a compose-internal hostname for the containerized bots.
The UAT driver runs host-side, where that name does not resolve, so every
via_dispatcher test failed transport and was recorded as SKIP — silently reducing
the effective catalog by 31 cases. These tests pin the host-side resolution so the
regression cannot return unnoticed.
"""

from __future__ import annotations

import pytest

from tests.uat.config import _host_side_url

_FALLBACK = "http://localhost:9099"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Compose-internal names → localhost, port and path preserved.
        ("http://portal-pipeline:9099", "http://localhost:9099"),
        ("http://portal5-pipeline:9099", "http://localhost:9099"),
        ("http://portal-5-pipeline:9099", "http://localhost:9099"),
        ("http://host.docker.internal:9099", "http://localhost:9099"),
        ("http://portal-pipeline:9099/v1", "http://localhost:9099/v1"),
        ("http://portal-pipeline", "http://localhost"),
        # Already host-reachable, or deliberately remote → untouched.
        ("http://localhost:9099", "http://localhost:9099"),
        ("http://127.0.0.1:9099", "http://127.0.0.1:9099"),
        ("https://pipeline.example.com/api", "https://pipeline.example.com/api"),
        # Unset → documented default.
        ("", _FALLBACK),
    ],
)
def test_host_side_url_resolution(raw: str, expected: str) -> None:
    assert _host_side_url(raw, _FALLBACK) == expected


def test_module_constant_is_never_a_compose_hostname() -> None:
    """Whatever the ambient .env says, the exported constant must be dialable."""
    from tests.uat import config

    assert "portal-pipeline" not in config.PIPELINE_URL
    assert "portal5-pipeline" not in config.PIPELINE_URL
    assert "host.docker.internal" not in config.PIPELINE_URL


def test_dispatcher_reads_config_not_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_via_dispatcher must honor a monkeypatched config, proving it no longer
    reads os.environ directly — otherwise the fix is bypassable."""
    from tests.uat import config, skips

    monkeypatch.setenv("PIPELINE_URL", "http://portal-pipeline:9099")
    monkeypatch.setattr(config, "PIPELINE_URL", "http://localhost:9099", raising=True)

    captured: dict[str, str] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "ok"}}]}

    class _FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def post(self, url: str, **_kwargs) -> _FakeResponse:
            captured["url"] = url
            return _FakeResponse()

    monkeypatch.setattr(skips.httpx, "AsyncClient", _FakeClient)

    import asyncio

    result = asyncio.run(skips._run_via_dispatcher("auto-coding", "hello", 30))
    assert result == "ok"
    assert captured["url"] == "http://localhost:9099/v1/chat/completions"
