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

LIVE_CAPTURE_MODE = "lab-exercise"
LIVE_CAPTURE_ORIGIN = "live:portal:red"
ANSWER_KEY_VISIBILITY = "scorer_only"


def canonical_target_host(data: dict) -> str:
    """Resolve stale capture metadata through the current scenario catalog."""
    scenario = str(data.get("scenario") or "")
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS

        configured = SCENARIOS.get(scenario, {}).get("target_host")
    except Exception:
        configured = None
    return str(configured or data.get("target_host") or "")


def capture_replay_warnings(data: dict) -> list[str]:
    stored = str(data.get("target_host") or "")
    canonical = canonical_target_host(data)
    if stored and canonical and stored != canonical:
        return [f"STALE_TARGET_METADATA:{stored}->{canonical}"]
    return []


def capture_ground_truth_status(data: dict) -> dict:
    """Revalidate immutable telemetry against the current scenario contract.

    Stored validity is an audit record of the validator that existed when the
    capture was written.  Blue scoring needs the current catalog and current
    signal rules, otherwise a later ground-truth change can silently leave an
    old capture certified for labels its telemetry never proved.
    """
    scenario = str(data.get("scenario") or "")
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS

        known_scenario = scenario in SCENARIOS
    except Exception:
        known_scenario = False
    if known_scenario:
        from .capture_enrichment import validate_capture_signals

        return validate_capture_signals(scenario, data.get("telemetry") or {})
    return dict(data.get("validity") or {})


def capture_replay_issues(data: dict, *, require_pcap: bool = False) -> list[str]:
    """Return integrity failures that make a saved red capture unsafe to replay.

    Replay is a scoring input, so merely having non-empty telemetry is not
    sufficient.  A replayable capture must be episode-scoped and must have
    passed the scenario-specific ground-truth validator.  PCAP is optional for
    ordinary replay, but combined-corpus readiness requires it as independent
    network evidence.
    """
    issues: list[str] = []
    if data.get("schema_version") != 2:
        issues.append("LEGACY_CAPTURE_UNSCOPED")
    if not data.get("episode_id"):
        issues.append("MISSING_EPISODE_ID")
    if not any((data.get("telemetry") or {}).values()):
        issues.append("NO_OBSERVED_TELEMETRY")
    validity = capture_ground_truth_status(data)
    if not validity.get("checked") or not validity.get("valid"):
        # Current validation results do not carry the historical ``checked``
        # flag; a non-empty checked-technique count is the equivalent proof.
        currently_checked = validity.get("techniques_checked", 0) > 0
        if not currently_checked or not validity.get("valid"):
            issues.append("CAPTURE_GROUND_TRUTH_INVALID")
    unchecked = sorted(validity.get("unchecked") or [])
    if unchecked:
        issues.append(f"UNVERIFIED_GROUND_TRUTH:{','.join(unchecked)}")
    if require_pcap:
        pcap_path = data.get("pcap_path")
        pcap_exists = bool(pcap_path and Path(str(pcap_path)).is_file())
        if pcap_path and not pcap_exists:
            # Captures are committed with their PCAPs, but older payloads store
            # an absolute path from the machine that produced them.  Resolve by
            # basename after a clone rather than declaring portable evidence
            # missing.
            pcap_exists = (CAPTURE_DIR / "pcap" / Path(str(pcap_path)).name).is_file()
        if not pcap_exists:
            issues.append("MISSING_PCAP")
    return issues


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

    target_host = canonical_target_host({"scenario": scenario, "target_host": target_host})
    payload = {
        "scenario": scenario,
        "target_host": target_host,
        "kind": kind,
        "collected_since_epoch": since_epoch,
        "captured_at": time.time(),
        "schema_version": 2,
        "data_mode": LIVE_CAPTURE_MODE,
        "evidence_origin": LIVE_CAPTURE_ORIGIN,
        "answer_key_visibility": ANSWER_KEY_VISIBILITY,
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
    target_host = canonical_target_host(data)
    telemetry = data["telemetry"]
    telemetry_origins = data.get("telemetry_origins") or {}
    episode_id = data.get("episode_id")
    integrity_issues = capture_replay_issues(data)
    if integrity_issues:
        return {
            "ok": False,
            "error": integrity_issues[0],
            "integrity_issues": integrity_issues,
            "integrity_warnings": capture_replay_warnings(data),
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
        "integrity_warnings": capture_replay_warnings(data),
    }
