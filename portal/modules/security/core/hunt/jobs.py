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

from .engine import HOUR, Lead, Search, hunt
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


def _stripped(lead: Lead) -> dict[str, Any]:
    """Scalar fields, top 3 bursts without link lists, 5 novel templates: full list, bounded file."""
    out = lead.as_dict()
    out["bursts"] = [{k: v for k, v in b.items() if k != "links"} for b in out["bursts"][:3]]
    out["novel_templates"] = out["novel_templates"][:5]
    return out


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
        state.update(stage="investigating", leads=[_stripped(lead) for lead in leads])
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


_MAX_CHARS = 6000  # an 8K-context seat


def _levenshtein(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def _all() -> list[dict[str, Any]]:
    """Every stored job, most recently started first."""
    found = [job for p in _ROOT.glob("hunt-*.json") if (job := load(p.stem)) is not None]
    found.sort(key=lambda j: j.get("started", 0.0), reverse=True)
    return found


def _recent(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: j.get(k) for k in ("job_id", "index", "status", "started")} for j in found[:3]]


def _resolve(job_id: str | None, index: str | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The job to read: an exact id, else the newest hunt on the index, else a near-miss id
    (edit distance <= 3 -- a mis-copied id resolves instead of stranding the analyst)."""
    found = _all()
    if not job_id and not index:
        return None, {"error": "give job_id or index"}
    if job_id:
        job = next((j for j in found if j.get("job_id") == job_id), None)
        if job is not None:
            return job, {}
        near = [j for j in found if _levenshtein(str(j.get("job_id", "")), job_id) <= 3]
        if len(near) == 1:
            return near[0], {"resolved_from": job_id}
        return None, {"error": f"unknown hunt {job_id!r}", "recent": _recent(found)}
    job = next((j for j in found if j.get("index") == index), None)
    if job is None:
        return None, {"error": f"no hunt for index {index!r}", "recent": _recent(found)}
    return job, {}


def compact(out: dict[str, Any]) -> dict[str, Any]:
    """Trim the tail of the largest list field until the response fits an 8K-context seat."""
    trimmed = False
    while len(json.dumps(out)) >= _MAX_CHARS:
        sizes = {k: len(v) for k, v in out.items() if isinstance(v, list) and v}
        if not sizes:
            break
        big = max(sizes, key=lambda k: sizes[k])
        out[big] = out[big][:-1]
        trimmed = True
    if trimmed:
        out["truncated"] = True
    return out


def status(job_id: str | None = None, index: str | None = None) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return compact(out)
    keep = ("job_id", "index", "status", "stage", "started", "finished", "error")
    out.update({k: job[k] for k in keep if k in job})
    out["elapsed_s"] = round(job.get("finished", time.time()) - job["started"], 1)
    out["cases"] = len(job.get("cases", []))
    return compact(out)


def leads_view(job_id: str | None = None, index: str | None = None, n: int = 10) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return compact(out)
    rows = []
    for rank, lead in enumerate(job.get("leads", [])[: max(0, min(n, 25))], 1):
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
    out["job_id"] = job["job_id"]
    out["leads"] = rows
    return compact(out)


def case_view(
    job_id: str | None = None, index: str | None = None, case_no: int = 1, n: int = 15
) -> dict[str, Any]:
    job, out = _resolve(job_id, index)
    if job is None:
        return compact(out)
    cases = job.get("cases", [])
    if not 1 <= case_no <= len(cases):
        out["error"] = f"case {case_no} not in 1..{len(cases)}"
        return compact(out)
    c = cases[case_no - 1]
    pivots = sorted(c["pivots"], key=lambda p: -p["weight"])[:10]
    core = c.get("core", c["picture"])
    out.update(
        {
            "job_id": job["job_id"],
            "case": case_no,
            "seeds": c["merged_from"],
            "core_events": c.get("core_events", c["events"]),
            "core_hosts": c.get("core_hosts", len(c["hosts"])),
            "span_hours": c["span_hours"],
            "pivots": [f"{p['token']} ({p['count']} events, {p['hosts']} hosts)" for p in pivots],
            "core": [
                f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}" for e in core[:n]
            ],
            "picture": [
                f"{_hm(e['time'])} {e['host']} {e['source']}: {e['raw'][:180]}"
                for e in c["picture"][:n]
            ],
        }
    )
    return compact(out)


__all__ = ["HOUR", "case_view", "compact", "leads_view", "load", "start", "status"]
