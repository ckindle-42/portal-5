"""``portal trace`` lab section: Splunk auth and one labelled event, through the hunt's builders.

Contributed to the platform CLI through the plugin seam (``trace_sections``) so the
platform never imports module code; hops travel as plain dicts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from portal.modules.security.core.hunt.engine import hunt
from portal.modules.security.core.review.window import SplunkWindowSource
from portal.modules.security.core.siem.spl_backend import SplunkBackend
from portal.modules.security.core.siem.spl_detections import spl_for

#: Techniques the lab's own live chains emit; each is queried until one returns rows.
LAB_TECHNIQUES = ("T1018", "T1087", "T1059.001", "T1083")
#: Fresh ingest first; the lab's corpus is historical, so the wide window follows.
LAB_WINDOWS = ("-7d", "-400d")
ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


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
    """Run the hunt engine and report whether its query path completed."""
    try:
        leads = hunt(hunt_search(), index, 0.0, time.time())
    except Exception as exc:  # noqa: BLE001 - an unreachable hop is the finding
        return _hop("hunt query", "FAIL", f"{type(exc).__name__}: {exc}", "query completes")
    return _hop("hunt query", "PASS", f"index={index} leads={len(leads)}", "query completes")


def labelled_event_hop(backend: Any) -> dict[str, str]:
    """One event found by the detection library's own SPL for a technique the lab emits."""
    empty: list[str] = []
    for window in LAB_WINDOWS:
        for technique in LAB_TECHNIQUES:
            if not spl_for(technique):
                continue
            result = backend.query(technique, {"earliest": window, "latest": "now"})
            rows = result.get("rows") or []
            if not rows:
                empty.append(f"{technique}{window}=0")
                continue
            hosts = sorted({str(row.get("host") or "?") for row in rows})[:3]
            observed = f"{technique} rows={len(rows)} hosts={','.join(hosts)} window={window}"
            return _hop("labelled event", "PASS", observed, "live rows")
    return _hop(
        "labelled event",
        "FAIL",
        " ".join(empty) or "no detection SPL",
        "live rows",
        "no labelled event in " + ", ".join(LAB_WINDOWS),
    )


def load_lab_env(path: Path = ENV_FILE) -> None:
    """SplunkBackend reads ``LAB_SPLUNK_*`` from os.environ; its default is a container host."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path)


def run() -> list[dict[str, str]]:
    """Splunk auth, the hunt's own query, and one labelled event read back."""
    load_lab_env()
    backend = SplunkBackend()
    return [
        auth_hop(backend),
        hunt_query_hop(str(backend.index)),
        labelled_event_hop(backend),
    ]
