"""Hunt jobs for the analyst surface: start a blind hunt over an index, dig its top leads, keep
the result on disk, and hand back compact views an 8K-context model can read.

The job runs the same engine and investigator the measurements use -- there is no second path.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .engine import HOUR, Search, hunt
from .investigate import Investigator

_ROOT = Path(
    os.environ.get("PORTAL5_HUNT_DIR", str(Path.home() / "AI_Output" / "review" / "hunts"))
)
_lock = threading.Lock()


def _path(job_id: str) -> Path:
    return _ROOT / f"{job_id}.json"


def _write(job_id: str, payload: dict[str, Any]) -> None:
    _ROOT.mkdir(parents=True, exist_ok=True)
    tmp = _path(job_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(_path(job_id))


def load(job_id: str) -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads(_path(job_id).read_text())
        return data
    except FileNotFoundError:
        return None


def _hm(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t))


def _run(job_id: str, search: Search, index: str, start: float, end: float, dig: int) -> None:
    state: dict[str, Any] = {
        "job_id": job_id,
        "index": index,
        "status": "RUNNING",
        "stage": "leads",
        "started": time.time(),
    }
    _write(job_id, state)
    try:
        leads = hunt(search, index, start, end)
        state.update(stage="investigating", leads=[lead.as_dict() for lead in leads[:50]])
        _write(job_id, state)
        inv = Investigator(search, index, start, end)
        cases = inv.investigate_all(leads, dig=dig)
        state.update(
            status="COMPLETE",
            stage="done",
            finished=time.time(),
            cases=[{**c.summary(), "evidence": list(c.events.values())} for c in cases],
            degraded=inv.degraded,
        )
    except Exception as exc:  # noqa: BLE001 -- the analyst sees the failure, not a hang
        state.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
    _write(job_id, state)


def start(search: Search, index: str, start_t: float, end_t: float, dig: int) -> str:
    job_id = "hunt-" + uuid.uuid4().hex[:12]
    with _lock:
        threading.Thread(
            target=_run, args=(job_id, search, index, start_t, end_t, dig), daemon=True
        ).start()
    return job_id


def status(job_id: str) -> dict[str, Any]:
    job = load(job_id)
    if job is None:
        return {"error": f"unknown hunt {job_id!r}"}
    keep = ("job_id", "index", "status", "stage", "started", "finished", "error")
    out = {k: job[k] for k in keep if k in job}
    out["elapsed_s"] = round(job.get("finished", time.time()) - job["started"], 1)
    out["cases"] = len(job.get("cases", []))
    return out


def leads_view(job_id: str, n: int) -> dict[str, Any]:
    job = load(job_id) or {}
    rows = []
    for rank, lead in enumerate(job.get("leads", [])[:n], 1):
        top = lead["bursts"][0] if lead.get("bursts") else None
        rows.append(
            {
                "rank": rank,
                "start_utc": lead["hour_utc"],
                "span_s": lead.get("span", 3600),
                "host": lead["host"],
                "score": lead["score"],
                "template_novelty": lead["novelty"],
                "top_burst": None
                if top is None
                else f"{top['token']} {top['this_hour']} this bucket vs usual {top['prior_median']}",
            }
        )
    return {"job_id": job_id, "leads": rows}


def case_view(job_id: str, case_no: int, n: int) -> dict[str, Any]:
    job = load(job_id) or {}
    cases = job.get("cases", [])
    if not 1 <= case_no <= len(cases):
        return {"error": f"case {case_no} not in 1..{len(cases)}"}
    c = cases[case_no - 1]
    pivots = sorted(c["pivots"], key=lambda p: -p["weight"])[:10]
    core = c.get("core", c["picture"])
    return {
        "job_id": job_id,
        "case": case_no,
        "seeds": c["merged_from"],
        "core_events": c.get("core_events", c["events"]),
        "core_hosts": c.get("core_hosts", len(c["hosts"])),
        "span_hours": c["span_hours"],
        "pivots": [f"{p['token']} ({p['count']} events, {p['hosts']} hosts)" for p in pivots],
        "core": [f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}" for e in core[:n]],
        "picture": [
            f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}"
            for e in c["picture"][:n]
        ],
    }


__all__ = ["HOUR", "case_view", "leads_view", "load", "start", "status"]
