"""bully.drift_engine -- BR-DRIFT, the temporal-cousin engine (P3.2, I-9).

Pure compute over injected data (MASTER SS3): no SQL, no network, no model
calls. Baselines are handed in and handed back updated -- `store.py` is the
only module that persists them (drift_engine never touches `hunt_state.db`
itself, per the boundary rule enforced by
`tests/security/bully/test_boundaries.py`). This is a documented
interpretation of I-9's literal 2-arg `update(episode, detections)` signature:
the STATE EFFECT ("baseline rows updated in SUB") is the *caller's*
responsibility (LOOP loads baselines via `store`, calls this pure function,
then persists what it returns) -- MASTER SS0's "drift is a finding, not a
silent fix" note, re-anchored here rather than silently making this module
do SQL.

Statistics pattern reused from `drift_gate.py:35-51` (module untouched):
window, noise floor, min-baseline, INSUFFICIENT-BASELINE. `drift_gate.py`
compares whole *runs* against a rolling window of prior runs; this module
compares one detection's per-episode sample against the rolling window baked
into its `DetectionBaseline`, because BR-DRIFT is evaluated one episode at a
time as hunts execute (never a batch of historical result files).

Cause-attribution order is deterministic (I-9 FAILURE SEMANTICS) and
**sensor failure always takes precedence** over an attack/detection label --
checked first, unconditionally:

  1. INSUFFICIENT_BASELINE  -- baseline sample_count < min_baseline
  2. TELEMETRY_DEGRADATION  -- sensor/sourcetype health collapsed this episode
  3. (no drift -- fire rate within noise floor of baseline)          -> no flag
  4. fire rate dropped beyond the noise floor, in order:
       a. DETECTION_DEGRADATION -- events present, correlation clause failed
       b. ATTACKER_EVOLUTION    -- observed row shape differs from baseline
                                    (routes to BR-COUSIN as a temporal-cousin
                                    lead -- the only class with routed=True)
       c. ENVIRONMENT_CHANGE    -- environment fingerprint differs from baseline,
                                    or model-canary evidence corroborates a
                                    model/environment change
       d. UNCLASSIFIED          -- ambiguous combination; an honest non-guess,
                                    never a forced label

Baseline update is idempotent, keyed by `(detection_id, episode_id)`: a
sample already present in the baseline's window is never re-counted (a
re-drive of the same episode is a no-op on the baseline, though the flags it
computes are recomputed the same way each time -- pure function). A
`policy_version` change is folded into the baseline key upstream (by the
caller, mirroring DATA_MODEL SS1.8's documented key: "hash(procedure family,
detection id/version, environment fingerprint, telemetry schema version,
policy version)" -- simplified here to `(detection_id, policy_version)`,
since the fuller key's other components are not available data in this
build); a version change therefore naturally lands on a *different* baseline
key, which starts fresh in `warmup` with zero inherited confidence -- no
special-cased "supersede" logic is needed.
"""

from __future__ import annotations

import uuid
from typing import Any

from .contracts import DriftFlag

DEFAULT_WINDOW = 7
MIN_BASELINE_RUNS = 3
NOISE_FLOOR = 0.15  # fire-rate drop below this (0..1 scale) is noise, never a flag
SENSOR_FAILURE_COMPLETENESS_DROP = 0.25  # sourcetype completeness drop vs baseline mean
CANARY_CORROBORATING_STATUSES = ("MEDIUM", "HIGH")

__all__ = ["update", "new_baseline", "baseline_key"]


def baseline_key(detection_id: str, policy_version: str) -> str:
    """DATA_MODEL SS1.8 baseline key, simplified to the two components this
    build has real data for (see module docstring). A `policy_version`
    change yields a different key -- the warm-up mechanism."""
    return f"bl-{detection_id}-{policy_version}"


def new_baseline(detection_id: str, policy_version: str) -> dict[str, Any]:
    """An empty baseline in `warmup` status -- DATA_MODEL SS1.8 shape."""
    return {
        "baseline_key": baseline_key(detection_id, policy_version),
        "detection_id": detection_id,
        "policy_version": policy_version,
        "status": "warmup",
        "window": [],
        "sample_count": 0,
        "model_canary_ref": None,
        "last_episode_id": None,
    }


def _window_stats(window: list[dict[str, Any]]) -> dict[str, Any]:
    fired_vals = [1.0 if s.get("fired") else 0.0 for s in window]
    completeness_vals = [
        s["sourcetype_completeness"] for s in window if s.get("sourcetype_completeness") is not None
    ]
    return {
        "fire_rate_mean": sum(fired_vals) / len(fired_vals) if fired_vals else None,
        "sourcetype_completeness_mean": (
            sum(completeness_vals) / len(completeness_vals) if completeness_vals else None
        ),
        "row_shape_signature": window[-1].get("row_shape") if window else None,
        "environment_fingerprint": window[-1].get("environment_fingerprint") if window else None,
    }


def _classify(
    sample: dict[str, Any],
    stats: dict[str, Any],
    *,
    noise_floor: float,
    sensor_failure_drop: float,
    canary: dict[str, Any] | None,
) -> tuple[str, float, str] | None:
    """Returns (drift_class, score, detail) or None (no drift this pass).
    Sensor failure is checked first, unconditionally (I-9: "sensor failure
    takes precedence over attack/detection labels")."""
    sensor_healthy = sample.get("sensor_healthy", True)
    completeness = sample.get("sourcetype_completeness")
    baseline_completeness = stats.get("sourcetype_completeness_mean")
    completeness_drop = (
        (baseline_completeness - completeness)
        if (baseline_completeness is not None and completeness is not None)
        else 0.0
    )
    if not sensor_healthy or completeness_drop > sensor_failure_drop:
        return (
            "TELEMETRY_DEGRADATION",
            round(max(completeness_drop, 0.0) if sensor_healthy else 1.0, 4),
            "sensor/sourcetype health collapsed this episode",
        )

    baseline_fire_rate = stats.get("fire_rate_mean")
    if baseline_fire_rate is None:
        return None
    fired = 1.0 if sample.get("fired") else 0.0
    drop = baseline_fire_rate - fired
    if drop <= noise_floor:
        return None  # within noise -- no flag, healthy

    if sample.get("clause_satisfied") is False:
        return (
            "DETECTION_DEGRADATION",
            round(drop, 4),
            "events present but correlation clause failed to satisfy",
        )

    baseline_shape = stats.get("row_shape_signature")
    if baseline_shape is not None and sample.get("row_shape") not in (None, baseline_shape):
        return (
            "ATTACKER_EVOLUTION",
            round(drop, 4),
            f"observed row shape {sample.get('row_shape')!r} differs from baseline {baseline_shape!r}",
        )

    baseline_env = stats.get("environment_fingerprint")
    if baseline_env is not None and sample.get("environment_fingerprint") not in (
        None,
        baseline_env,
    ):
        return (
            "ENVIRONMENT_CHANGE",
            round(drop, 4),
            f"environment fingerprint {sample.get('environment_fingerprint')!r} differs from "
            f"baseline {baseline_env!r}",
        )

    if canary and canary.get("status") in CANARY_CORROBORATING_STATUSES:
        return (
            "ENVIRONMENT_CHANGE",
            round(drop, 4),
            f"model-canary status={canary.get('status')} corroborates an environment/model change",
        )

    return ("UNCLASSIFIED", round(drop, 4), "fire rate dropped but cause could not be attributed")


def update(
    episode_id: str,
    detections: list[dict[str, Any]],
    baselines: dict[str, dict[str, Any]],
    *,
    window: int = DEFAULT_WINDOW,
    min_baseline: int = MIN_BASELINE_RUNS,
    noise_floor: float = NOISE_FLOOR,
    sensor_failure_drop: float = SENSOR_FAILURE_COMPLETENESS_DROP,
    canary: dict[str, Any] | None = None,
    policy_version: str = "v1",
) -> tuple[list[DriftFlag], dict[str, dict[str, Any]]]:
    """I-9: classify drift for each detection outcome this episode against
    its rolling baseline, then fold this episode's sample into that
    baseline. Returns `(flags, updated_baselines)` -- the caller persists
    `updated_baselines` via `store.py` (this function never does).

    `detections`: one dict per detection this episode, keys `detection_id`
    (required), `fired` (bool), `sourcetype_completeness` (0..1 or None),
    `clause_satisfied` (bool or None), `row_shape` (str or None),
    `environment_fingerprint` (str or None), `sensor_healthy` (bool,
    default True).
    """
    flags: list[DriftFlag] = []
    # Starts as a copy of the injected baselines so untouched
    # (detection_id, policy_version) baselines pass through unchanged --
    # callers can persist the full returned map without losing entries this
    # call didn't touch.
    updated: dict[str, dict[str, Any]] = dict(baselines)

    for sample in detections:
        detection_id = sample["detection_id"]
        key = baseline_key(detection_id, policy_version)
        baseline = baselines.get(key) or new_baseline(detection_id, policy_version)

        already_seen = any(s.get("episode_id") == episode_id for s in baseline["window"])

        if baseline["sample_count"] < min_baseline:
            flags.append(
                DriftFlag(
                    flag_id=f"df-{uuid.uuid4().hex[:12]}",
                    detection_id=detection_id,
                    episode_id=episode_id,
                    drift_class="UNCLASSIFIED",
                    status="INSUFFICIENT_BASELINE",
                    score=0.0,
                    detail=(
                        f"baseline has {baseline['sample_count']} sample(s), "
                        f"needs >= {min_baseline}"
                    ),
                )
            )
        else:
            stats = _window_stats(baseline["window"][-window:])
            result = _classify(
                sample,
                stats,
                noise_floor=noise_floor,
                sensor_failure_drop=sensor_failure_drop,
                canary=canary,
            )
            if result is not None:
                drift_class, score, detail = result
                flags.append(
                    DriftFlag(
                        flag_id=f"df-{uuid.uuid4().hex[:12]}",
                        detection_id=detection_id,
                        episode_id=episode_id,
                        drift_class=drift_class,
                        status="FLAGGED",
                        score=score,
                        signals={
                            k: sample.get(k)
                            for k in ("fired", "row_shape", "environment_fingerprint")
                        },
                        bands={
                            "noise_floor": noise_floor,
                            "sensor_failure_drop": sensor_failure_drop,
                        },
                        detail=detail,
                        routed=(drift_class == "ATTACKER_EVOLUTION"),
                    )
                )

        if not already_seen:
            new_window = [*baseline["window"], {**sample, "episode_id": episode_id}]
            new_count = baseline["sample_count"] + 1
            new_status = "active" if new_count >= min_baseline else "warmup"
            baseline = {
                **baseline,
                "window": new_window[-window:] if window > 0 else new_window,
                "sample_count": new_count,
                "status": new_status,
                "last_episode_id": episode_id,
                "model_canary_ref": (canary or {}).get("candidate_ts")
                or baseline.get("model_canary_ref"),
            }
        updated[key] = baseline

    return flags, updated
