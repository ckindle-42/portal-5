"""Durable capture of raw telemetry collected off a lab target, independent of Splunk.

collect_target() + ship_batch() gets red's real activity into Splunk, but Splunk's
own retention/rotation means that data can age out. save_capture() persists the same
raw {sourcetype: [lines]} payload to disk (results/captures/) so it survives beyond
Splunk's retention window and can be re-shipped later — replay_capture() re-runs
ship_batch()+wait_indexed() against a saved capture, which lands with a brand-new
`time.time()` timestamp (ship()/ship_batch() always stamp at call time, not from the
captured data), making a capture replayable as "current" telemetry for a fresh blue/
purple test without ever re-running red.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
CAPTURE_DIR = _PROJECT_ROOT / "tests" / "benchmarks" / "bench_security" / "results" / "captures"


def save_capture(
    *,
    scenario: str,
    target_host: str,
    kind: str,
    since_epoch: float,
    telemetry: dict[str, list[str]],
) -> str | None:
    """Persist a collect_target() result to disk. Returns the file path, or None if empty."""
    if not any(telemetry.values()):
        return None
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = CAPTURE_DIR / f"{scenario}_{ts}.json"
    payload = {
        "scenario": scenario,
        "target_host": target_host,
        "kind": kind,
        "collected_since_epoch": since_epoch,
        "captured_at": time.time(),
        "telemetry": telemetry,
    }
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def list_captures(scenario: str | None = None) -> list[Path]:
    """List saved capture files, optionally filtered to one scenario, newest first."""
    if not CAPTURE_DIR.exists():
        return []
    pattern = f"{scenario}_*.json" if scenario else "*.json"
    return sorted(CAPTURE_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)


def save_evidence(kind: str, scenario: str, payload: dict) -> str:
    """Persist an arbitrary red/blue/purple evidence payload to disk (results/captures/<kind>/).

    Unlike save_capture (blue-telemetry-specific, skips empty payloads), this
    always writes — a weak/failed red attempt is itself evidence worth keeping,
    so it can be inspected or diffed against later without re-running it live.
    """
    d = CAPTURE_DIR / kind
    d.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = d / f"{scenario}_{ts}.json"
    body = {"kind": kind, "scenario": scenario, "captured_at": time.time(), **payload}
    path.write_text(json.dumps(body, indent=2, default=str))
    return str(path)


def list_evidence(kind: str, scenario: str | None = None) -> list[Path]:
    """List saved kind-specific evidence files (red/blue/purple), newest first."""
    d = CAPTURE_DIR / kind
    if not d.exists():
        return []
    pattern = f"{scenario}_*.json" if scenario else "*.json"
    return sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)


def replay_capture(path: str | Path, *, dry_run: bool = False, timeout_s: int = 30) -> dict:
    """Re-ship a saved capture to Splunk (fresh timestamp) and confirm it indexed.

    This is the "reload with updated timestamps" mechanism — no red execution needed.
    Returns {ok, shipped, indexed_confirmed, scenario, target_host}.
    """
    from .hec_ship import ship_batch
    from .index_wait import wait_indexed

    p = Path(path)
    data = json.loads(p.read_text())
    scenario = data["scenario"]
    target_host = data["target_host"]
    telemetry = data["telemetry"]

    replay_start = time.time()
    shipped = 0
    for sourcetype, lines in telemetry.items():
        if not lines:
            continue
        r = ship_batch(
            [{"raw": line} for line in lines],
            sourcetype=sourcetype,
            host=target_host,
            dry_run=dry_run,
        )
        if r.get("ok"):
            shipped += len(lines)

    indexed_confirmed = None
    if shipped and not dry_run:
        indexed_confirmed = wait_indexed(
            host=target_host, since_epoch=replay_start, expect_min=1, timeout_s=timeout_s
        )

    return {
        "ok": shipped > 0,
        "scenario": scenario,
        "target_host": target_host,
        "shipped": shipped,
        "indexed_confirmed": indexed_confirmed,
        "replayed_from": str(p),
    }
