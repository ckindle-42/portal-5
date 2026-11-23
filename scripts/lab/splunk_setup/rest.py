"""Splunk REST client for the setup stages: app enable, index create, HEC allowlist, job API.

Credentials come only from the named keys in .env.example (``LAB_SPLUNK_URL``,
``LAB_SPLUNK_USER``, ``LAB_SPLUNK_PASSWORD``, ``LAB_SPLUNK_HEC_TOKEN``). The file is never
sourced; the process environment supplies them.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

Transport = Callable[[str, str, dict[str, str] | None], dict[str, Any]]

DEFAULT_URL = "https://10.0.1.30:8089"
POLL_SECONDS = 3.0


def _datamodel_path(kind: str, app: str, model: str) -> str:
    return f"/servicesNS/nobody/{quote(app, safe='')}/{kind}/{quote(model, safe='')}"


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

    # -- data models ---------------------------------------------------------------
    def datamodel_acceleration(self, app: str, model: str) -> dict[str, Any]:
        """What the model reports it accelerates over: the effective state, not the conf row."""
        entry = self.entry(_datamodel_path("datamodel/model", app, model))
        content = dict((entry or {}).get("content") or {})
        reported = content.get("acceleration")
        if isinstance(reported, str):
            try:
                reported = json.loads(reported)
            except json.JSONDecodeError:
                reported = None
        state: dict[str, Any] = dict(reported) if isinstance(reported, dict) else {}
        if isinstance(reported, bool):
            state["enabled"] = reported
        state.update(
            {
                key.split(".", 1)[1]: value
                for key, value in content.items()
                if key.startswith("acceleration.")
            }
        )
        state["enabled"] = str(state.get("enabled", "")).lower() in ("1", "true", "t")
        return state

    def ensure_datamodel_acceleration(
        self, app: str, model: str, settings: dict[str, str], *, dry_run: bool = False
    ) -> Action:
        """Write the settings into ``app``'s local conf unless the model already reports them."""
        reported = self.datamodel_acceleration(app, model)
        window = settings["acceleration.earliest_time"]
        if reported.get("enabled") and reported.get("earliest_time") == window:
            return Action(False, f"{app} {model} already reports enabled {window}")
        before = f"{'enabled' if reported.get('enabled') else 'disabled'} " + str(
            reported.get("earliest_time", "?")
        )
        if not dry_run:
            self.request("POST", _datamodel_path("configs/conf-datamodels", app, model), settings)
        return Action(True, f"{app} {model} reports {before} -> enabled {window}")

    def rebuild_datamodel_acceleration(
        self, app: str, model: str, settings: dict[str, str], *, dry_run: bool = False
    ) -> Action:
        """Disable then re-enable. CIM manual_rebuilds leaves a macro edit unbackfilled."""
        window = settings["acceleration.earliest_time"]
        if dry_run:
            return Action(True, f"{app} {model} would rebuild over {window}")
        path = _datamodel_path("configs/conf-datamodels", app, model)
        self.request("POST", path, {"acceleration": "false"})
        self.request("POST", path, settings)
        return Action(True, f"{app} {model} rebuilt over {window}")

    def revert_datamodel_acceleration(
        self, app: str, model: str, *, dry_run: bool = False
    ) -> Action:
        """Drop the local override so the model reports the app's own default again."""
        if not self.datamodel_acceleration(app, model).get("enabled"):
            return Action(False, f"{app} {model} already reports its default")
        detail = f"{app} {model} local row would be removed"
        if not dry_run:
            try:
                self.request("DELETE", _datamodel_path("configs/conf-datamodels", app, model))
            except SplunkError as exc:
                if exc.status != 404:
                    raise
            reported = self.datamodel_acceleration(app, model)
            detail = (
                f"{app} {model} local row removed; reports {reported.get('earliest_time', '?')}"
            )
        return Action(True, detail)

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
        if not result.failed:
            results = self.request("GET", f"/services/search/jobs/{sid}/results?count=0")
            result.rows = list(results.get("results") or [])
        return result

    def macro_expansion(self, macro: str) -> str:
        """The search the parser actually runs for a macro invocation, read from the parser API."""
        payload = self.request(
            "POST",
            "/servicesNS/nobody/search/search/parser",
            {"q": f"search `{macro}`"},
        )
        expansion = str(payload.get("normalizedSearch") or "")
        if not expansion:
            raise SplunkError(f"parser returned no normalizedSearch for `{macro}`")
        return expansion
