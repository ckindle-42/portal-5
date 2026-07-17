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
        self.index = os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")

    def _run_search(self, search: str, earliest: str, latest: str) -> list[dict]:
        """POST one SPL search to the export endpoint and parse hits into rows.

        Shared by the exact technique-SPL query and the broad discovery
        fallback below — same request/parse path, different search string.
        """
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

            _time_raw = result.get("_time", "")
            try:
                _time = float(_time_raw) if _time_raw else time.time()
            except (ValueError, TypeError):
                _time = time.time()

            host = ""
            for hf in _HOST_FIELDS:
                if result.get(hf):
                    host = str(result[hf])
                    break

            fields = {k: v for k, v in result.items() if k != "_time" and k not in _HOST_FIELDS}
            rows.append({"_time": _time, "host": host, "raw": line, "fields": fields})
        return rows

    def query(self, technique_id: str, window: dict) -> dict:
        """Run the SPL for technique_id via /services/search/jobs/export (oneshot, json).

        If the exact technique SPL returns nothing, falls back to a broad,
        index-wide search over the same time window before giving up (see
        P5-PURPLE-DISCOVERY-001, 2026-07-17: found live that T1059/T1078's
        SPL requires an exact `sourcetype="linux:auditd"` match, but a
        target's actual collected telemetry can land under a different
        sourcetype — the narrow query then reports "nothing here" even
        though real, relevant data exists in the index. Real detections
        should not be silently discarded just because they don't match the
        exact classification a query author guessed at. Tagged distinctly
        (`source="live-broad-fallback"`) so callers can tell "matched
        exactly" from "found via broad search" — this is not a substitute
        for fixing collection coverage or SPL accuracy, just a safety net
        so real evidence isn't invisible in the meantime.)

        Returns:
            {
                "rows": [{"_time": float, "host": str, "raw": str, "fields": dict}, ...],
                "source": "live" | "live-broad-fallback" | "synthetic-fallback" | "synthetic",
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

        rows: list[dict] = []
        error: str | None = None
        if spl:
            search = (
                spl
                if spl.strip().startswith("search") or "|" in spl.split()[0:1]
                else f"search {spl}"
            )
            try:
                rows = self._run_search(search, earliest, latest)
            except Exception as e:
                error = str(e)

        source = "live" if rows else "synthetic-fallback"

        # Broad discovery fallback — only when the exact query found nothing
        # and didn't error (an error means Splunk itself is unreachable;
        # retrying broader would just fail the same way).
        if not rows and error is None:
            try:
                broad_rows = self._run_search(
                    f"search index={self.index} | head 200", earliest, latest
                )
            except Exception:
                broad_rows = []
            if broad_rows:
                rows = broad_rows
                source = "live-broad-fallback"

        telemetry = "\n".join(r["raw"] for r in rows)

        return {
            "rows": rows,
            "source": source,
            "backend": self.name,
            "spl": spl,
            "query_id": query_id,
            "time_bounds": time_bounds,
            "error": error,
            "telemetry": telemetry,
        }
