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
    event_time: float | None = None,
) -> dict:
    """Post one event to HEC. Returns {'ok': bool, 'code': int|None, 'dry_run'?: True}.

    event_time overrides the HEC 'time' field (epoch seconds) — pass the real
    attack time so the event lands on the SIEM timeline as if it happened then,
    instead of at whatever moment it happened to get shipped.
    """
    envelope = {
        "time": event_time if event_time is not None else time.time(),
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
    events: list[dict | str],
    *,
    sourcetype: str,
    host: str,
    index: str = INDEX,
    dry_run: bool = False,
    event_time: float | None = None,
) -> dict:
    """Batch to /services/collector/event (newline-concatenated event objects).

    event_time overrides the HEC 'time' field (epoch seconds) for every event in
    the batch — pass the real attack time so the batch lands on the SIEM
    timeline as if it happened then, instead of at ship time.
    """
    if dry_run:
        return {"ok": True, "dry_run": True, "count": len(events)}
    stamp = event_time if event_time is not None else time.time()
    payload = "\n".join(
        json.dumps(
            {
                "time": stamp,
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
