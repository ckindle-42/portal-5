"""bully.plateau -- PLT, statistical plateau + resets (P4.4, I-12).

Pure compute over injected data (MASTER SS3): no SQL, no network. Same
documented `evaluate(neighborhood, window)` reinterpretation used
throughout P4 (`drift_engine`/`costing`/`scoreboard`/`targeting`): the
pure function scores a `trials` list the caller already fetched from SUB
-- this module never touches `hunt_state.db` itself. LOOP (`orchestrator.py`)
persists the returned `PlateauDecision` via `store.plateau_put`.

FINAL_DESIGN SS21 "Plateau model (PLT)" -- the literal exhaustion rule: a
neighborhood is exhausted when ALL hold over its valid trials:

- >= 8 valid trials spanning >= 2 mutation dimensions
- no promoted discovery in the window
- marginal unique defense-response gain < 1 (no brand-new response state
  appeared in the second half of the window vs the first half)
- the upper 95% bound of discovery yield < `plateau_yield_bound` (default
  5%)

Blocked/infrastructure-failed trials never count (excluded from every
denominator before any of the above is computed). Embedding-cluster
stability is explicitly NOT a stop signal (never referenced here). A
material version change (detection/telemetry/environment/ATT&CK/
cousin-algorithm/evidence) resets the neighborhood: the window is
re-filtered to the latest version's trials, discarding the pre-reset
trials from every metric -- a genuine restart, not a soft discount. Plateau
is neighborhood-local: `trials` outside the target `neighborhood` are
never counted, no matter how the caller assembled the list.
"""

from __future__ import annotations

import uuid
from typing import Any

from .contracts import PlateauDecision

__all__ = ["evaluate"]

MIN_VALID_TRIALS = 8
MIN_MUTATION_DIMENSIONS = 2
DEFAULT_PLATEAU_YIELD_BOUND = 0.05
Z_95 = 1.959964  # two-sided 95% normal-approximation z-score


def _wilson_upper_bound(successes: int, n: int, z: float = Z_95) -> float:
    """Normal-approximation upper bound on a proportion -- 'the upper 95%
    bound of discovery yield' (DESIGN SS21). Clipped to [0, 1]."""
    if n == 0:
        return 1.0  # no evidence yet -- can't claim yield is low
    p = successes / n
    margin = z * ((p * (1 - p) / n) ** 0.5)
    return min(1.0, max(0.0, p + margin))


def _marginal_unique_gain(windowed: list[dict[str, Any]]) -> int:
    """Count of brand-new `response_state` values introduced in the second
    half of the window vs the first half -- 'marginal unique
    defense-response gain'."""
    mid = len(windowed) // 2
    first_half_states = {t.get("response_state") for t in windowed[:mid]}
    second_half_states = {t.get("response_state") for t in windowed[mid:]}
    return len(second_half_states - first_half_states)


def evaluate(
    neighborhood: str,
    trials: list[dict[str, Any]],
    window: int,
    *,
    plateau_yield_bound: float = DEFAULT_PLATEAU_YIELD_BOUND,
    has_other_neighborhoods: bool = True,
    override: dict[str, Any] | None = None,
    now: float | None = None,
    hunt_id: str | None = None,
    policy_version: str = "plt-v1",
) -> PlateauDecision:
    """I-12: `evaluate(neighborhood, window) -> continue|rotate|stop`.

    `trials` is the caller-fetched SUB series (already read-only data);
    each trial dict: `neighborhood`, `mutation_dim`, `valid` (bool -- False
    for blocked/infrastructure-failed, excluded from every denominator),
    `promoted` (bool), `response_state` (str), `discovery_positive` (bool
    -- whether this trial's SCORE discovery axis was > 0), `version` (str,
    the material-evidence/algorithm version this trial ran under),
    `trial_id`.

    `override`, when given, is `{"reason": ..., "expiry": <epoch float>}`
    -- a recorded policy exception (I-12 OPERATOR BOUNDARY) that forces
    `action="continue"` regardless of the exhaustion rule, as long as
    `now < expiry`. A reason is mandatory; an expired or reason-less
    override is rejected/ignored, never silently honored forever.
    """
    if override is not None and (not override.get("reason") or override.get("expiry") is None):
        raise ValueError("[GATE] plateau override requires a reason and an expiry")

    now = time_now() if now is None else now

    neighborhood_valid = [
        t for t in trials if t.get("neighborhood") == neighborhood and t.get("valid", True)
    ]
    # Chronological order is the caller's responsibility (SUB returns rows
    # in insertion order); take the most recent `window` valid trials.
    windowed = neighborhood_valid[-window:] if window > 0 else neighborhood_valid

    reset_trigger: str | None = None
    reset_version: str | None = None
    if windowed:
        latest_version = windowed[-1].get("version")
        current_version_only = [t for t in windowed if t.get("version") == latest_version]
        if len(current_version_only) < len(windowed):
            reset_trigger = "version_change"
            reset_version = latest_version
            windowed = current_version_only

    n_valid = len(windowed)
    dims = {t.get("mutation_dim") for t in windowed if t.get("mutation_dim") is not None}

    def _insufficient(note: str) -> PlateauDecision:
        return PlateauDecision(
            plateau_id=f"plt-{uuid.uuid4().hex[:12]}",
            hunt_id=hunt_id,
            neighborhood=neighborhood,
            qualifying_trial_ids=tuple(t.get("trial_id", "") for t in windowed),
            promotions=sum(1 for t in windowed if t.get("promoted")),
            unique_response_gain=0.0,
            posterior_upper_bound=1.0,
            saturation=0.0,
            policy_version=policy_version,
            decision="INSUFFICIENT",
            action="continue",
            note=note,
            reset_trigger=reset_trigger,
            reset_version=reset_version,
        )

    if n_valid < MIN_VALID_TRIALS or len(dims) < MIN_MUTATION_DIMENSIONS:
        return _insufficient(
            f"{n_valid} valid trial(s) spanning {len(dims)} mutation dimension(s); "
            f"need >= {MIN_VALID_TRIALS} trials and >= {MIN_MUTATION_DIMENSIONS} dimensions"
        )

    promotions = sum(1 for t in windowed if t.get("promoted"))
    marginal_gain = _marginal_unique_gain(windowed)
    discoveries = sum(1 for t in windowed if t.get("discovery_positive"))
    yield_upper_bound = _wilson_upper_bound(discoveries, n_valid)
    unique_states = {t.get("response_state") for t in windowed}
    unique_response_gain = len(unique_states) / n_valid
    saturation = 1.0 - unique_response_gain

    exhausted = promotions == 0 and marginal_gain < 1 and yield_upper_bound < plateau_yield_bound

    override_active = override is not None and now < override["expiry"]

    if exhausted and not override_active:
        decision = "PLATEAU"
        action = "rotate" if has_other_neighborhoods else "stop"
        note = (
            f"exhausted: {n_valid} valid trials, 0 promotions, marginal_gain={marginal_gain}, "
            f"yield_upper_bound={yield_upper_bound:.4f} < {plateau_yield_bound}"
        )
    else:
        decision = "CONTINUE"
        action = "continue"
        note = (
            f"override active until {override['expiry']}: {override['reason']}"
            if exhausted and override_active
            else f"not exhausted: promotions={promotions}, marginal_gain={marginal_gain}, "
            f"yield_upper_bound={yield_upper_bound:.4f}"
        )

    return PlateauDecision(
        plateau_id=f"plt-{uuid.uuid4().hex[:12]}",
        hunt_id=hunt_id,
        neighborhood=neighborhood,
        qualifying_trial_ids=tuple(t.get("trial_id", "") for t in windowed),
        promotions=promotions,
        unique_response_gain=round(unique_response_gain, 4),
        posterior_upper_bound=round(yield_upper_bound, 4),
        saturation=round(saturation, 4),
        policy_version=policy_version,
        decision=decision,
        action=action,
        note=note,
        reset_trigger=reset_trigger,
        reset_version=reset_version,
        override=override if override_active else None,
        expiry=override.get("expiry") if override_active else None,
    )


def time_now() -> float:
    """Indirection so tests can freeze 'now' without monkeypatching the
    stdlib -- pure module, no wall-clock dependency baked into the
    exhaustion math itself."""
    import time

    return time.time()
