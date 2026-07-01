"""Ship lab telemetry to Splunk HEC.

POST /services/collector/event, auth 'Splunk <token>'.
"""

from __future__ import annotations

import json
import os
import time

import httpx

HEC_URL = os.environ.get("LAB_SPLUNK_HEC_URL", "https://portal5-lab-splunk:8088")
HEC_TOKEN = os.environ.get("LAB_SPLUNK_HEC_TOKEN", "")
INDEX = os.environ.get("LAB_SPLUNK_INDEX", "portal5_lab")


def ship(
    event: dict | str,
    *,
    sourcetype: str,
    host: str,
    source: str = "portal5-bench",
    index: str = INDEX,
    dry_run: bool = False,
) -> dict:
    """Post one event to HEC. Returns {'ok': bool, 'code': int|None, 'dry_run'?: True}."""
    envelope = {
        "time": time.time(),
        "host": host,
        "source": source,
        "sourcetype": sourcetype,
        "index": index,
        "event": event,
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "envelope": envelope}
    try:
        r = httpx.post(
            f"{HEC_URL.rstrip('/')}/services/collector/event",
            headers={"Authorization": f"Splunk {HEC_TOKEN}"},
            json=envelope,
            verify=False,
            timeout=15.0,
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {"ok": r.status_code == 200 and body.get("code") == 0, "code": r.status_code}
    except Exception as e:
        return {"ok": False, "code": None, "error": str(e)}


def ship_batch(
    events: list[dict],
    *,
    sourcetype: str,
    host: str,
    index: str = INDEX,
    dry_run: bool = False,
) -> dict:
    """Batch to /services/collector/event (newline-concatenated event objects)."""
    if dry_run:
        return {"ok": True, "dry_run": True, "count": len(events)}
    payload = "\n".join(
        json.dumps(
            {
                "time": time.time(),
                "host": host,
                "sourcetype": sourcetype,
                "index": index,
                "event": e,
            }
        )
        for e in events
    )
    try:
        r = httpx.post(
            f"{HEC_URL.rstrip('/')}/services/collector/event",
            headers={"Authorization": f"Splunk {HEC_TOKEN}"},
            content=payload,
            verify=False,
            timeout=30.0,
        )
        return {"ok": r.status_code == 200, "code": r.status_code, "count": len(events)}
    except Exception as e:
        return {"ok": False, "code": None, "error": str(e)}
