"""detections-mcp and mitre-mcp answer the Pipeline's POST /tools/{name} (tool_registry), not just GET /tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

pytest.importorskip("mcp")


class _Request:
    def __init__(self, name: str, body: dict[str, Any]) -> None:
        self.path_params = {"tool_name": name}
        self._body = body

    async def json(self) -> dict[str, Any]:
        return self._body


def _call(module: Any, name: str, body: dict[str, Any]) -> tuple[int, Any]:
    response = asyncio.run(module.invoke_tool(_Request(name, body)))
    return response.status_code, json.loads(response.body)


def test_detections_rest_dispatch_runs_a_listed_tool() -> None:
    from portal.modules.security.tools import detections_mcp

    status, body = _call(
        detections_mcp,
        "spl_validate_syntax",
        {"arguments": {"spl": "index=x EventCode=4769 | stats count"}},
    )
    assert status == 200 and isinstance(body, dict)


def test_detections_rest_dispatch_rejects_unlisted_names() -> None:
    from portal.modules.security.tools import detections_mcp

    status, _ = _call(detections_mcp, "health_check", {})
    assert status == 404


def test_every_listed_tool_is_dispatchable() -> None:
    from portal.modules.security.tools import detections_mcp, mitre_mcp

    for module in (detections_mcp, mitre_mcp):
        for tool in module.TOOLS_MANIFEST:
            assert callable(getattr(module, tool["name"])), tool["name"]


def test_mitre_rest_dispatch_reports_bad_arguments() -> None:
    from portal.modules.security.tools import mitre_mcp

    status, _ = _call(mitre_mcp, "mitre_technique_lookup", {"arguments": {"wrong": 1}})
    assert status == 400
