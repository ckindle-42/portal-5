"""SplunkBackend — Splunk telemetry adapter implementing TelemetryBackend protocol.

Queries via /services/search/jobs/export (oneshot, json) — single round-trip,
no job-poll loop.  Returns per-row structure for downstream correlation.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

import httpx

# Host-field priority order for row extraction
_HOST_FIELDS = ("host", "ComputerName", "dest", "Computer", "src")


class SplunkBackend:
    """Splunk telemetry backend — real SPL via the REST export endpoint."""

    name = "splunk"

    def __init__(self):
        self.url = os.environ.get("LAB_SPLUNK_URL", "https://portal5-lab-splunk:8089")
        self.user = os.environ.get("LAB_SPLUNK_USER", "admin")
        self.pw = os.environ.get("LAB_SPLUNK_PASSWORD", "")

    def query(self, technique_id: str, window: dict) -> dict:
        """Run the SPL for technique_id via /services/search/jobs/export (oneshot, json).

        Returns:
            {
                "rows": [{"_time": float, "host": str, "raw": str, "fields": dict}, ...],
                "source": "live" | "synthetic-fallback" | "synthetic",
                "backend": "splunk",
                "spl": str,
                "query_id": str (sha256[:12]),
                "time_bounds": {"earliest": ..., "latest": ...},
                "error": str | None,
                "telemetry": str,  # backward compat: "\n".join(raw for rows)
            }
        """
        from .spl_detections import spl_for

        spl = spl_for(technique_id)
        earliest = window.get("earliest", "-15m")
        latest = window.get("latest", "now")
        time_bounds = {"earliest": earliest, "latest": latest}

        # Query ID for provenance tracking
        qid_src = f"{spl or ''}{earliest}{latest}{technique_id}"
        query_id = hashlib.sha256(qid_src.encode()).hexdigest()[:12]

        if not spl:
            return {
                "rows": [],
                "source": "synthetic-fallback",
                "backend": self.name,
                "spl": None,
                "query_id": query_id,
                "time_bounds": time_bounds,
                "error": None,
                "telemetry": "",
            }

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
            r.raise_for_status()
        except Exception as e:
            return {
                "rows": [],
                "source": "synthetic-fallback",
                "backend": self.name,
                "spl": spl,
                "query_id": query_id,
                "time_bounds": time_bounds,
                "error": str(e),
                "telemetry": "",
            }

        # Parse each hit line into a structured row
        rows = []
        for line in r.text.splitlines():
            line = line.strip()
            if not line.startswith("{") or '"result"' not in line:
                continue
            try:
                obj = json.loads(line)
                result = obj.get("result", obj)
            except json.JSONDecodeError:
                continue

            # Extract _time
            _time_raw = result.get("_time", "")
            try:
                _time = float(_time_raw) if _time_raw else time.time()
            except (ValueError, TypeError):
                _time = time.time()

            # Extract host (first present field)
            host = ""
            for hf in _HOST_FIELDS:
                if result.get(hf):
                    host = str(result[hf])
                    break

            # Fields = everything except _time and host aliases
            fields = {
                k: v
                for k, v in result.items()
                if k != "_time" and k not in _HOST_FIELDS
            }

            rows.append({
                "_time": _time,
                "host": host,
                "raw": line,
                "fields": fields,
            })

        source = "live" if rows else "synthetic-fallback"
        telemetry = "\n".join(r["raw"] for r in rows)

        return {
            "rows": rows,
            "source": source,
            "backend": self.name,
            "spl": spl,
            "query_id": query_id,
            "time_bounds": time_bounds,
            "error": None,
            "telemetry": telemetry,
        }
