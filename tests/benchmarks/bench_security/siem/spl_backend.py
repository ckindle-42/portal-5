"""SplunkBackend — Splunk telemetry adapter implementing TelemetryBackend protocol.

Queries via /services/search/jobs/export (oneshot, json) — single round-trip,
no job-poll loop.
"""

from __future__ import annotations

import os

import httpx


class SplunkBackend:
    """Splunk telemetry backend — real SPL via the REST export endpoint."""

    name = "splunk"

    def __init__(self):
        self.url = os.environ.get("LAB_SPLUNK_URL", "https://portal5-lab-splunk:8089")
        self.user = os.environ.get("LAB_SPLUNK_USER", "admin")
        self.pw = os.environ.get("LAB_SPLUNK_PASSWORD", "")

    def query(self, technique_id: str, window: dict) -> dict:
        """Run the SPL for technique_id via /services/search/jobs/export (oneshot, json).

        Returns {signals, source, backend}.  No hits -> synthetic-fallback (never PASS).
        """
        from .spl_detections import spl_for

        spl = spl_for(technique_id)
        if not spl:
            return {"signals": [], "source": "synthetic-fallback", "backend": self.name}
        earliest = window.get("earliest", "-15m")
        latest = window.get("latest", "now")
        search = (
            spl if spl.strip().startswith("search") or "|" in spl.split()[0:1] else f"search {spl}"
        )
        try:
            r = httpx.post(
                f"{self.url.rstrip('/')}/services/search/jobs/export",
                auth=(self.user, self.pw),
                verify=False,
                timeout=90.0,
                data={
                    "search": search,
                    "exec_mode": "oneshot",
                    "earliest_time": earliest,
                    "latest_time": latest,
                    "output_mode": "json",
                },
            )
            # export streams one JSON object per line; a 'result' object == a matched event
            hits = [
                ln for ln in r.text.splitlines() if ln.strip().startswith("{") and '"result"' in ln
            ]
            if hits:
                return {"signals": hits, "source": "live", "backend": self.name}
            return {"signals": [], "source": "synthetic-fallback", "backend": self.name}
        except Exception as e:
            return {
                "signals": [],
                "source": "synthetic-fallback",
                "backend": self.name,
                "error": str(e),
            }
