"""P3.2 -- BR-DRIFT temporal-cousin engine.

Hermetic (no network, no SQL -- baselines are injected/returned dicts).
FINAL_VALIDATION C6 "Drift engine": given synthetic firing series, the
engine distinguishes the four causes + UNCLASSIFIED via the deterministic
attribution order; ATTACKER_EVOLUTION routes to BR-COUSIN; insufficient
history yields INSUFFICIENT-BASELINE; sensor failure takes precedence;
version change starts warm-up, not inherited confidence.
"""

from __future__ import annotations

from portal.modules.security.core.bully import drift_engine

DETECTION = "det-1"


def _healthy_sample(**overrides) -> dict:
    base = {
        "detection_id": DETECTION,
        "fired": True,
        "sourcetype_completeness": 0.95,
        "clause_satisfied": True,
        "row_shape": "shape-a",
        "environment_fingerprint": "env-a",
        "sensor_healthy": True,
    }
    base.update(overrides)
    return base


def _seed_baseline(n: int = 3, policy_version: str = "v1") -> dict[str, dict]:
    """Build up a healthy baseline over `n` episodes so subsequent calls see
    a sufficient (active) baseline."""
    baselines: dict[str, dict] = {}
    for i in range(n):
        _flags, baselines = drift_engine.update(
            f"ep-seed-{i}", [_healthy_sample()], baselines, policy_version=policy_version
        )
    return baselines


# ── insufficient baseline ───────────────────────────────────────────────


def test_insufficient_baseline_is_an_honest_flag_not_a_guess():
    flags, baselines = drift_engine.update("ep-1", [_healthy_sample()], {})
    assert len(flags) == 1
    assert flags[0].status == "INSUFFICIENT_BASELINE"
    assert flags[0].drift_class == "UNCLASSIFIED"
    key = drift_engine.baseline_key(DETECTION, "v1")
    assert baselines[key]["sample_count"] == 1
    assert baselines[key]["status"] == "warmup"


def test_baseline_accumulates_to_active_after_min_samples():
    baselines = _seed_baseline(n=3)
    key = drift_engine.baseline_key(DETECTION, "v1")
    assert baselines[key]["status"] == "active"
    assert baselines[key]["sample_count"] == 3


# ── idempotent baseline update ──────────────────────────────────────────


def test_idempotent_baseline_update_same_episode_counts_once():
    _flags, baselines = drift_engine.update("ep-dup", [_healthy_sample()], {})
    _flags2, baselines2 = drift_engine.update("ep-dup", [_healthy_sample()], baselines)
    key = drift_engine.baseline_key(DETECTION, "v1")
    assert baselines2[key]["sample_count"] == 1  # not 2 -- same episode_id


# ── no drift: healthy, within noise floor ───────────────────────────────


def test_healthy_repeat_yields_no_flag():
    baselines = _seed_baseline(n=3)
    flags, _baselines = drift_engine.update("ep-healthy", [_healthy_sample()], baselines)
    assert flags == []


# ── sensor failure takes precedence ─────────────────────────────────────


def test_sensor_failure_takes_precedence_over_attack_or_detection_label():
    baselines = _seed_baseline(n=3)
    # Even though row_shape AND fire outcome both look like an attacker-
    # evolution signature, sensor_healthy=False must win.
    sample = _healthy_sample(
        fired=False, row_shape="shape-mutated", sensor_healthy=False, clause_satisfied=False
    )
    flags, _baselines = drift_engine.update("ep-sensor", [sample], baselines)
    assert len(flags) == 1
    assert flags[0].drift_class == "TELEMETRY_DEGRADATION"
    assert flags[0].status == "FLAGGED"


def test_telemetry_completeness_collapse_flags_telemetry_degradation():
    baselines = _seed_baseline(n=3)
    sample = _healthy_sample(sourcetype_completeness=0.2)  # big drop vs baseline ~0.95
    flags, _baselines = drift_engine.update("ep-collapse", [sample], baselines)
    assert len(flags) == 1
    assert flags[0].drift_class == "TELEMETRY_DEGRADATION"


# ── DETECTION_DEGRADATION: rule change, stable attack ───────────────────


def test_detection_degradation_when_clause_fails_with_events_present():
    baselines = _seed_baseline(n=3)
    sample = _healthy_sample(fired=False, clause_satisfied=False, row_shape="shape-a")
    flags, _baselines = drift_engine.update("ep-rule-change", [sample], baselines)
    assert len(flags) == 1
    assert flags[0].drift_class == "DETECTION_DEGRADATION"
    assert flags[0].routed is False


# ── ATTACKER_EVOLUTION: behavior shift, healthy controls, routes to cousin ──


def test_attacker_evolution_when_row_shape_differs_and_routes_to_cousin():
    baselines = _seed_baseline(n=3)
    sample = _healthy_sample(fired=False, clause_satisfied=None, row_shape="shape-mutated")
    flags, _baselines = drift_engine.update("ep-evolved", [sample], baselines)
    assert len(flags) == 1
    assert flags[0].drift_class == "ATTACKER_EVOLUTION"
    assert flags[0].routed is True


# ── ENVIRONMENT_CHANGE: population shift ─────────────────────────────────


def test_environment_change_when_fingerprint_differs():
    baselines = _seed_baseline(n=3)
    sample = _healthy_sample(
        fired=False, clause_satisfied=None, row_shape="shape-a", environment_fingerprint="env-b"
    )
    flags, _baselines = drift_engine.update("ep-env", [sample], baselines)
    assert len(flags) == 1
    assert flags[0].drift_class == "ENVIRONMENT_CHANGE"


# ── UNCLASSIFIED: ambiguous combination, honest non-guess ────────────────


def test_unclassified_when_signals_are_ambiguous():
    baselines = _seed_baseline(n=3)
    sample = _healthy_sample(
        fired=False, clause_satisfied=None, row_shape="shape-a", environment_fingerprint="env-a"
    )
    flags, _baselines = drift_engine.update("ep-ambiguous", [sample], baselines)
    assert len(flags) == 1
    assert flags[0].drift_class == "UNCLASSIFIED"
    assert flags[0].status == "FLAGGED"


def test_model_canary_evidence_held_constant_across_the_same_ambiguous_case():
    """Same ambiguous fixture, evaluated twice with the same canary evidence
    held constant -- deterministic, not order-dependent."""
    baselines = _seed_baseline(n=3)
    sample = _healthy_sample(
        fired=False, clause_satisfied=None, row_shape="shape-a", environment_fingerprint="env-a"
    )
    canary = {"status": "HIGH", "candidate_ts": "2026-08-15T00:00:00Z"}
    flags_a, _ = drift_engine.update("ep-canary-a", [sample], baselines, canary=canary)
    flags_b, _ = drift_engine.update("ep-canary-b", [sample], baselines, canary=canary)
    assert flags_a[0].drift_class == flags_b[0].drift_class == "ENVIRONMENT_CHANGE"


# ── warm-up on version change ─────────────────────────────────────────────


def test_version_change_starts_warmup_not_inherited_confidence():
    baselines = _seed_baseline(n=5, policy_version="v1")
    v1_key = drift_engine.baseline_key(DETECTION, "v1")
    assert baselines[v1_key]["status"] == "active"

    # A new detection rule version is a *different* baseline key -- starts
    # fresh, never inherits v1's confidence.
    flags, baselines_v2 = drift_engine.update(
        "ep-v2-1", [_healthy_sample()], baselines, policy_version="v2"
    )
    v2_key = drift_engine.baseline_key(DETECTION, "v2")
    assert v2_key != v1_key
    assert baselines_v2[v2_key]["status"] == "warmup"
    assert baselines_v2[v2_key]["sample_count"] == 1
    assert flags[0].status == "INSUFFICIENT_BASELINE"
    # The old v1 baseline is untouched by the v2 call.
    assert baselines_v2[v1_key]["sample_count"] == 5
