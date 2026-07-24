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
_EPISODE_PIPE_COMMANDS = frozenset(
    {
        "search",
        "where",
        "regex",
        "fields",
        "table",
        "head",
        "sort",
        "stats",
        "dedup",
        "eval",
        "rex",
        "spath",
        "rename",
        "bin",
        "bucket",
        "timechart",
        "top",
        "rare",
        "transaction",
    }
)


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

        This legacy technique-specific method never performs a broad fallback.
        Returning an episode-wide haystack once per expected technique
        duplicates the same event under the answer-key labels and turns
        unrelated ambient data into apparent supporting evidence.

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

    def query_episode(
        self,
        window: dict,
        *,
        episode_id: str,
        host: str | None = None,
        limit: int = 500,
    ) -> dict:
        """Return one unlabeled, episode-scoped telemetry haystack.

        Ground-truth technique IDs are intentionally absent from this API.
        ``episode_id`` is an indexed HEC field attached at collection time, so
        concurrent or back-to-back runs cannot contaminate one another.
        """
        earliest = window.get("earliest", "-15m")
        latest = window.get("latest", "now")
        clauses = [f"index={self.index}", f'episode_id="{episode_id}"']
        if host:
            clauses.append(f'host="{host}"')
        search = f"search {' '.join(clauses)} | head {max(1, min(int(limit), 5000))}"
        error: str | None = None
        try:
            rows = self._run_search(search, earliest, latest)
        except Exception as exc:
            rows = []
            error = str(exc)
        origins: set[str] = set()
        for row in rows:
            fields = row.get("fields", {})
            origin = fields.get("evidence_origin")
            source = str(fields.get("source", ""))
            if origin:
                origins.add(str(origin))
            elif source.startswith("portal5:"):
                origins.add(source.split(":", 1)[1])
        return {
            "rows": rows,
            "source": "observed" if rows else "empty",
            "origins": sorted(origins),
            "backend": self.name,
            "spl": search,
            "time_bounds": {"earliest": earliest, "latest": latest},
            "error": error,
            "telemetry": "\n".join(row["raw"] for row in rows),
        }

    def query_freeform(
        self,
        spl: str,
        window: dict,
        *,
        episode_id: str,
        host: str | None = None,
    ) -> dict:
        """Execute blue's requested SPL inside an immutable episode scope."""
        earliest = window.get("earliest", "-15m")
        latest = window.get("latest", "now")
        requested = (spl or "").strip()
        if any(token in requested for token in ("[", "]", "`", ";")):
            return {
                "rows": [],
                "source": "empty",
                "origin": "observed_query",
                "backend": self.name,
                "spl": "",
                "requested_spl": spl,
                "time_bounds": {"earliest": earliest, "latest": latest},
                "error": "query rejected: subsearches and command separators are not allowed",
                "telemetry": "",
            }
        if requested.lower().startswith("search "):
            requested = requested[7:].strip()
        pipeline = requested.split("|")
        for segment in pipeline[1:]:
            command = segment.strip().split(maxsplit=1)[0].lower() if segment.strip() else ""
            if command not in _EPISODE_PIPE_COMMANDS:
                return {
                    "rows": [],
                    "source": "empty",
                    "origin": "observed_query",
                    "backend": self.name,
                    "spl": "",
                    "requested_spl": spl,
                    "time_bounds": {"earliest": earliest, "latest": latest},
                    "error": f"query rejected: pipeline command {command!r} is not allowed",
                    "telemetry": "",
                }
        base = f'search index={self.index} episode_id="{episode_id}"'
        if host:
            base += f' host="{host}"'
        search = f"{base} | search {requested}" if requested else f"{base} | head 500"
        try:
            rows = self._run_search(search, earliest, latest)
            error = None
        except Exception as exc:
            rows = []
            error = str(exc)
        return {
            "rows": rows,
            "source": "observed" if rows else "empty",
            "origin": "observed_query",
            "backend": self.name,
            "spl": search,
            "requested_spl": spl,
            "time_bounds": {"earliest": earliest, "latest": latest},
            "error": error,
            "telemetry": "\n".join(row["raw"] for row in rows),
        }
