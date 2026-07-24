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

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
CAPTURE_DIR = _PROJECT_ROOT / "portal" / "modules" / "security" / "core" / "results" / "captures"


def save_capture(
    *,
    scenario: str,
    target_host: str,
    kind: str,
    since_epoch: float,
    telemetry: dict[str, list[str]],
    telemetry_origins: dict[str, str] | None = None,
    counterfactual_telemetry: dict[str, list[str]] | None = None,
    episode_id: str | None = None,
    pcap_path: str | None = None,
) -> str | None:
    """Persist a collect_target() result to disk. Returns the file path, or None if empty.

    Gate: validates the telemetry contains ground-truth attack signals for the
    scenario's detect_ground_truth techniques.  Captures that lack their expected
    signals are still saved (red evidence is always worth keeping) but are flagged
    with ``validity`` metadata so downstream consumers can distinguish real
    captures from hollow ones.
    """
    counterfactual_telemetry = counterfactual_telemetry or {}
    if not any(telemetry.values()) and not any(counterfactual_telemetry.values()):
        return None
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    episode_suffix = f"_{episode_id[-8:]}" if episode_id else ""
    path = CAPTURE_DIR / f"{scenario}_{ts}{episode_suffix}.json"

    # ── ground-truth gate ──────────────────────────────────────────────
    validity = {
        "checked": False,
        "valid": False,
        "coverage": 0.0,
        "found": [],
        "missing": [],
        "unchecked": [],
    }
    try:
        from .capture_enrichment import validate_capture_signals

        result = validate_capture_signals(scenario, telemetry)
        validity = {
            "checked": True,
            "valid": result["valid"],
            "coverage": result["coverage"],
            "found": result["found"],
            "missing": result["missing"],
            "unchecked": result.get("unchecked", []),
        }
    except Exception:
        pass  # don't let validation errors block saving

    payload = {
        "scenario": scenario,
        "target_host": target_host,
        "kind": kind,
        "collected_since_epoch": since_epoch,
        "captured_at": time.time(),
        "schema_version": 2,
        "episode_id": episode_id,
        "telemetry": telemetry,
        "telemetry_origins": telemetry_origins or {},
        # Red's command ledger is retained for audit and counterfactual
        # recognition experiments, but replay_capture never ships this plane.
        "counterfactual_telemetry": counterfactual_telemetry,
        "pcap_path": pcap_path,
        "validity": validity,
    }
    path.write_text(json.dumps(payload, indent=2))

    if validity["checked"] and not validity["valid"]:
        import logging

        logging.warning(
            "save_capture: %s capture saved but has NO ground-truth signals "
            "(coverage=%.1f%%, missing=%s) — this capture is hollow",
            scenario,
            validity["coverage"] * 100,
            validity["missing"],
        )

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
    episode_id = payload.get("episode_id")
    episode_suffix = f"_{str(episode_id)[-8:]}" if episode_id else ""
    path = d / f"{scenario}_{ts}{episode_suffix}.json"
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


def replay_capture(
    path: str | Path,
    *,
    dry_run: bool = False,
    timeout_s: int = 30,
    event_time: float | None = None,
) -> dict:
    """Re-ship a saved capture to Splunk and confirm it indexed.

    By default (event_time=None) this is the "reload with updated timestamps"
    mechanism — no red execution needed, and the replayed data lands as fresh
    "current" telemetry so it can drive a blue/purple retest against wall-clock-
    relative queries. Pass event_time=<captured_at epoch> (or the capture's own
    `captured_at` field) to instead force it into the SIEM at its true original
    attack time.

    Returns {ok, shipped, indexed_confirmed, scenario, target_host}.
    """
    from .hec_ship import ship_batch
    from .index_wait import wait_indexed

    p = Path(path)
    data = json.loads(p.read_text())
    scenario = data["scenario"]
    target_host = data["target_host"]
    telemetry = data["telemetry"]
    telemetry_origins = data.get("telemetry_origins") or {}
    episode_id = data.get("episode_id")
    if data.get("schema_version") != 2 or not episode_id:
        return {
            "ok": False,
            "error": "LEGACY_CAPTURE_UNSCOPED",
            "scenario": scenario,
            "target_host": target_host,
            "shipped": 0,
            "indexed_confirmed": None,
            "episode_id": episode_id,
            "replayed_from": str(p),
        }
    if not any(telemetry.values()):
        return {
            "ok": False,
            "error": "NO_OBSERVED_TELEMETRY",
            "scenario": scenario,
            "target_host": target_host,
            "shipped": 0,
            "indexed_confirmed": None,
            "episode_id": episode_id,
            "replayed_from": str(p),
        }

    replay_start = event_time if event_time is not None else time.time()
    shipped = 0
    for sourcetype, lines in telemetry.items():
        if not lines:
            continue
        # Plain strings, not {"raw": line} — found live 2026-07-18: wrapping
        # each line in a JSON envelope meant Splunk indexed the literal text
        # `{"raw": "EventCode=4769 ..."}`, and its automatic key=value field
        # extraction never descends into a nested JSON string value, so
        # every structured-field SPL query (siem/spl_detections.yaml) came
        # back empty even on correctly-shipped, indexed-confirmed events.
        r = ship_batch(
            list(lines),
            sourcetype=sourcetype,
            host=target_host,
            dry_run=dry_run,
            event_time=event_time,
            evidence_origin=telemetry_origins.get(sourcetype, "observed_target_log"),
            episode_id=episode_id,
        )
        if r.get("ok"):
            shipped += len(lines)

    indexed_confirmed = None
    if shipped and not dry_run:
        indexed_confirmed = wait_indexed(
            host=target_host,
            since_epoch=replay_start,
            expect_min=1,
            timeout_s=timeout_s,
            episode_id=episode_id,
        )

    return {
        "ok": shipped > 0,
        "scenario": scenario,
        "target_host": target_host,
        "shipped": shipped,
        "indexed_confirmed": indexed_confirmed,
        "episode_id": episode_id,
        "replay_start": replay_start,
        "replayed_from": str(p),
    }
