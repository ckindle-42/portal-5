"""Splunk REST client for the setup stages: app enable, index create, HEC allowlist, job API.

Credentials come only from the named keys in .env.example (``LAB_SPLUNK_URL``,
``LAB_SPLUNK_USER``, ``LAB_SPLUNK_PASSWORD``, ``LAB_SPLUNK_HEC_TOKEN``). The file is never
sourced; the process environment supplies them.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

Transport = Callable[[str, str, dict[str, str] | None], dict[str, Any]]

DEFAULT_URL = "https://10.0.1.30:8089"
POLL_SECONDS = 3.0


class SplunkError(RuntimeError):
    """A Splunk REST call failed; the message carries the status and body."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Action:
    changed: bool
    detail: str


@dataclass
class SearchResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    scan_count: int = 0
    run_seconds: float = 0.0
    failed: bool = False
    messages: list[str] = field(default_factory=list)
    normalized_search: str = ""


def _httpx_transport(method: str, path: str, data: dict[str, str] | None) -> dict[str, Any]:
    import httpx

    url = os.environ.get("LAB_SPLUNK_URL", DEFAULT_URL).rstrip("/") + path
    auth = (os.environ.get("LAB_SPLUNK_USER", "admin"), os.environ.get("LAB_SPLUNK_PASSWORD", ""))
    response = httpx.request(
        method, url, auth=auth, verify=False, data=data, timeout=180.0, follow_redirects=True
    )
    if response.status_code >= 400:
        raise SplunkError(
            f"{method} {path} -> {response.status_code}: {response.text[:400]}",
            status=response.status_code,
        )
    return response.json() if response.text.strip() else {}


class SplunkREST:
    """Idempotent-by-construction mutations: read state, write only when it differs."""

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport or _httpx_transport

    # -- plumbing ------------------------------------------------------------------
    def request(self, method: str, path: str, data: dict[str, str] | None = None) -> dict[str, Any]:
        sep = "&" if "?" in path else "?"
        if "output_mode=json" not in path:
            path = f"{path}{sep}output_mode=json"
        return self._transport(method, path, data)

    def entry(self, path: str) -> dict[str, Any] | None:
        try:
            payload = self.request("GET", path)
        except SplunkError as exc:
            if exc.status == 404:
                return None
            raise
        entries = payload.get("entry") or []
        return entries[0] if entries else None

    # -- apps ----------------------------------------------------------------------
    def app_state(self, name: str) -> bool | None:
        entry = self.entry(f"/services/apps/local/{quote(name, safe='')}")
        if entry is None:
            return None
        return not bool(entry.get("content", {}).get("disabled", False))

    def ensure_app(self, name: str, *, enabled: bool, dry_run: bool = False) -> Action:
        state = self.app_state(name)
        if state is None:
            return Action(False, f"app {name} not installed")
        if state == enabled:
            return Action(False, f"app {name} already {'enabled' if enabled else 'disabled'}")
        verb = "enable" if enabled else "disable"
        if not dry_run:
            self.request("POST", f"/services/apps/local/{quote(name, safe='')}/{verb}")
        return Action(True, f"app {name} {verb}d")

    # -- indexes -------------------------------------------------------------------
    def index_settings(self, name: str) -> dict[str, Any] | None:
        entry = self.entry(f"/services/data/indexes/{quote(name, safe='')}")
        return None if entry is None else dict(entry.get("content", {}))

    def ensure_index(self, name: str, settings: dict[str, str], *, dry_run: bool = False) -> Action:
        current = self.index_settings(name)
        if current is None:
            if not dry_run:
                self.request("POST", "/services/data/indexes", {"name": name, **settings})
            return Action(True, f"index {name} created")
        drift = {
            key: value for key, value in settings.items() if str(current.get(key)) != str(value)
        }
        if not drift:
            return Action(False, f"index {name} already matches")
        if not dry_run:
            self.request("POST", f"/services/data/indexes/{quote(name, safe='')}", drift)
        return Action(True, f"index {name} updated {sorted(drift)}")

    # -- HEC token -----------------------------------------------------------------
    def ensure_hec_index(self, token: str, index: str, *, dry_run: bool = False) -> Action:
        payload = self.request("GET", "/services/data/inputs/http")
        for entry in payload.get("entry") or []:
            content = entry.get("content", {})
            if content.get("token") != token:
                continue
            allowed = str(content.get("indexes", "") or "")
            if not allowed or allowed.strip() == "*":
                return Action(False, f"HEC token allows all indexes ({index} covered)")
            names = [part.strip() for part in allowed.split(",") if part.strip()]
            if index in names:
                return Action(False, f"HEC token already allows {index}")
            names.append(index)
            if not dry_run:
                self.request(
                    "POST",
                    f"/services/data/inputs/http/{quote(str(entry['name']), safe='')}",
                    {"indexes": ",".join(names)},
                )
            return Action(True, f"HEC token allowlist extended with {index}")
        raise SplunkError(
            "HEC token with LAB_SPLUNK_HEC_TOKEN not found in /services/data/inputs/http"
        )

    # -- macros --------------------------------------------------------------------
    def ensure_macro(
        self, app: str, name: str, definition: str, *, dry_run: bool = False
    ) -> Action:
        """Write a macro into ``app``'s local conf, and only when it differs from ``definition``."""
        path = (
            f"/servicesNS/nobody/{quote(app, safe='')}/configs/conf-macros/{quote(name, safe='')}"
        )
        entry = self.entry(path)
        if str((entry or {}).get("content", {}).get("definition")) == definition:
            return Action(False, f"{app} {name} already matches")
        if not dry_run:
            self.request("POST", path, {"definition": definition})
        return Action(True, f"{app} {name} set")

    # -- searches ------------------------------------------------------------------
    def search(
        self,
        spl: str,
        *,
        earliest: str = "-10y",
        latest: str = "now",
        max_wait: float = 900.0,
        poll: float = POLL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> SearchResult:
        payload = self.request(
            "POST",
            "/services/search/jobs",
            {
                "search": spl if spl.startswith(("search ", "|")) else f"search {spl}",
                "earliest_time": earliest,
                "latest_time": latest,
                "exec_mode": "normal",
            },
        )
        sid = payload.get("sid")
        if not sid:
            raise SplunkError(f"no sid returned for {spl[:80]!r}")
        result = SearchResult()
        deadline = time.monotonic() + max_wait
        content: dict[str, Any] = {}
        while time.monotonic() < deadline:
            entry = self.entry(f"/services/search/jobs/{sid}") or {}
            content = entry.get("content", {})
            if content.get("isDone") or content.get("isFailed"):
                break
            sleep(poll)
        result.failed = bool(content.get("isFailed"))
        result.scan_count = int(content.get("scanCount") or 0)
        result.run_seconds = float(content.get("runDuration") or 0.0)
        result.messages = [str(m.get("text", m)) for m in content.get("messages") or []]
        result.normalized_search = str(
            content.get("normalizedSearch") or content.get("optimizedSearch") or ""
        )
        if not result.failed:
            results = self.request("GET", f"/services/search/jobs/{sid}/results?count=0")
            result.rows = list(results.get("results") or [])
        return result

    def macro_expansion(self, macro: str) -> str:
        """What the parser makes of a macro invocation: the search it actually runs."""
        result = self.search(f"search `{macro}` | head 0", earliest="-1s", max_wait=120.0)
        if not result.normalized_search:
            raise SplunkError(f"no parser expansion returned for `{macro}`")
        return result.normalized_search
