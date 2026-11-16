"""``portal trace`` lab section: Splunk auth and one labelled event, through the hunt's builders.

Contributed to the platform CLI through the plugin seam (``trace_sections``) so the
platform never imports module code; hops travel as plain dicts.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from portal.modules.security.core.hunt.engine import ladder
from portal.modules.security.core.review.window import SplunkWindowSource
from portal.modules.security.core.siem.spl_backend import SplunkBackend
from portal.modules.security.core.siem.spl_detections import spl_for

#: Techniques the lab's own live chains emit; the first the library covers is queried.
LAB_TECHNIQUES = ("T1018", "T1087", "T1059.001", "T1083")


def parse_server_info(text: str) -> dict[str, str]:
    """Version and server name from ``/services/server/info?output_mode=json``."""
    try:
        payload = json.loads(text)
    except ValueError:
        return {}
    try:
        content = payload["entry"][0]["content"]
    except (KeyError, IndexError, TypeError):
        return {}
    return {key: str(content[key]) for key in ("version", "serverName") if key in content}


def _hop(
    name: str, status: str, observed: object = "", expected: str = "", detail: object = ""
) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "observed": str(observed),
        "expected": expected,
        "detail": str(detail),
    }


def auth_hop(backend: Any) -> dict[str, str]:
    """Splunk answers an authenticated metadata call on the URL the hunt uses."""
    try:
        response = httpx.get(
            f"{str(backend.url).rstrip('/')}/services/server/info",
            auth=(backend.user, backend.pw),
            params={"output_mode": "json"},
            verify=False,
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return _hop("splunk auth", "FAIL", f"{type(exc).__name__}: {exc}", "200")
    info = parse_server_info(response.text)
    observed = f"{backend.url} version={info.get('version', '?')}"
    return _hop("splunk auth", "PASS", observed, "authenticated", info.get("serverName", ""))


def hunt_search() -> Any:
    """The exact ``Search`` the hunt surface builds for its jobs (review_mcp._hunt_search)."""
    return SplunkWindowSource(timeout_seconds=60)


def hunt_query_hop(index: str) -> dict[str, str]:
    """Run the hunt's own zoom-ladder query; it proves the index answers the hunt's path."""
    try:
        levels = ladder(hunt_search(), index, 0.0, time.time())
    except Exception as exc:  # noqa: BLE001 - an unreachable hop is the finding
        return _hop("hunt query", "FAIL", f"{type(exc).__name__}: {exc}", "levels")
    if not levels:
        return _hop("hunt query", "FAIL", "no zoom levels", "index readable")
    return _hop("hunt query", "PASS", f"index={index} levels={levels}", "index readable")


def labelled_event_hop(backend: Any) -> dict[str, str]:
    """One event found by the detection library's own SPL for a technique the lab emits."""
    for technique in LAB_TECHNIQUES:
        if not spl_for(technique):
            continue
        result = backend.query(technique, {"earliest": "-7d", "latest": "now"})
        rows = result.get("rows") or []
        if rows:
            hosts = sorted({str(row.get("host") or "?") for row in rows})[:3]
            observed = f"{technique} rows={len(rows)} hosts={','.join(hosts)}"
            return _hop("labelled event", "PASS", observed, "live rows")
        return _hop(
            "labelled event",
            "FAIL",
            f"{technique} rows=0",
            "live rows",
            result.get("error") or "no labelled event in -7d",
        )
    return _hop("labelled event", "FAIL", "no detection SPL", "spl_detections entry")


def run() -> list[dict[str, str]]:
    """Splunk auth, the hunt's own query, and one labelled event read back."""
    backend = SplunkBackend()
    return [
        auth_hop(backend),
        hunt_query_hop(str(backend.index)),
        labelled_event_hop(backend),
    ]
