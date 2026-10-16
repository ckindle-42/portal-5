"""A partial discovery (an MCP not up at startup) is retried on the short retry TTL, not hidden
for the full refresh TTL; once every server has answered, the long TTL applies again."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from portal.platform.inference import tool_registry as tr


class _Resp:
    def __init__(self, status: int, payload=None) -> None:
        self.status_code = status
        self._payload = payload or []

    def json(self):
        return self._payload


class _Client:
    def __init__(self, up: dict[str, bool], hits: list[str]) -> None:
        self._up = up
        self._hits = hits

    async def get(self, url: str):
        sid = url.split("//")[1].split(".")[0]
        self._hits.append(sid)
        if not self._up[sid]:
            raise OSError("connection refused")
        return _Resp(200, [{"name": f"tool_{sid}", "description": "", "parameters": {}}])


@pytest.fixture
def setup(monkeypatch):
    clock = [1_000_000.0]  # a real epoch: the first refresh must not fall inside the TTL of t=0
    monkeypatch.setattr(tr, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(
        tr, "MCP_SERVERS", {"alpha": "http://alpha.test", "beta": "http://beta.test"}
    )
    monkeypatch.setattr(tr, "TOOL_REGISTRY_REFRESH_S", 3600.0)
    monkeypatch.setattr(tr, "TOOL_REGISTRY_RETRY_S", 30.0)
    up = {"alpha": True, "beta": False}
    hits: list[str] = []
    reg = tr.ToolRegistry()

    async def fake_client():
        return _Client(up, hits)

    monkeypatch.setattr(reg, "_client", fake_client)
    return SimpleNamespace(reg=reg, clock=clock, up=up, hits=hits)


def test_a_partial_discovery_is_retried_after_the_retry_ttl_not_before(setup) -> None:
    reg, clock, up, hits = setup.reg, setup.clock, setup.up, setup.hits
    asyncio.run(reg.refresh())  # beta is down
    assert reg._partial is True and "tool_beta" not in reg._tools

    clock[0] += 20  # inside the 30 s retry window: no network
    asyncio.run(reg.refresh())
    assert hits.count("beta") == 1

    up["beta"] = True
    clock[0] += 11  # past the window
    asyncio.run(reg.refresh())
    assert "tool_beta" in reg._tools
    assert reg._partial is False


def test_once_every_server_answers_the_long_ttl_holds(setup) -> None:
    reg, clock, up, hits = setup.reg, setup.clock, setup.up, setup.hits
    up["beta"] = True
    asyncio.run(reg.refresh())
    assert reg._partial is False

    clock[0] += 31  # would be a retry in a partial state; here it is not
    before = len(hits)
    asyncio.run(reg.refresh())
    assert len(hits) == before
