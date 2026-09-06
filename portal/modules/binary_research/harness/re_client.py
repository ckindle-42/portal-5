"""HTTP client to the binary research toolchain MCP (port 8930)."""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


class REClientError(RuntimeError):
    pass


class REClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8930", timeout: float = 620.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(f"{self._base}/health")
            r.raise_for_status()
            return cast(dict[str, Any], r.json())

    def _post(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self._timeout) as c:
                r = c.post(f"{self._base}/tools/{tool}", json={"arguments": arguments})
                r.raise_for_status()
                return cast(dict[str, Any], r.json())
        except httpx.HTTPError as exc:
            raise REClientError(f"RE MCP call {tool} failed: {exc}") from exc

    def exec(self, command: str, project: str = "", timeout: int = 120) -> dict[str, Any]:
        return self._post("re_exec", {"command": command, "project": project, "timeout": timeout})

    def python(self, code: str, project: str = "", timeout: int = 120) -> dict[str, Any]:
        return self._post("re_python", {"code": code, "project": project, "timeout": timeout})

    def tools(self) -> dict[str, Any]:
        return self._post("re_tools", {})
