"""bully.roster -- ROSTER, council eligibility/reliability governance
(P6.5, I-19).

Pure compute over injected data (MASTER SS3): no SQL, no network. Mirrors
the documented split `scoreboard.py`/`costing.py` established: the *pure*
function scores a list of per-seat records the caller already gathered via
`store.py` (council_opinions/objections/rebuttals joined against each
candidate's eventual disposition) -- this module never touches
`hunt_state.db` itself, and `window` is folded into the output purely as
provenance (I-19 literal `recompute(window) -> RosterUpdate` signature).

A1 (non-obvious choice): "only outcomes unavailable to the reviewer at
decision time" (I-19 INPUT) means every per-seat input here is a
*resolved* outcome (an objection's eventual `upheld` verdict via
rebuttal/waiver disposition, a cousin call's eventual correctness once the
candidate reached a terminal BIN state) -- never something knowable at the
moment the seat cast its opinion. Gathering that join is the caller's job
(a CLI/report script, not this module); `recompute` only trusts the shape
it is handed.

CONSTRAINTS (I-19, enforced in code):
- The objection gate never consults weights or reliability: `adversary.py`
  (HEART's objection gate, P2) never imports this module (import-scan
  test) and this module never imports `adversary.py` -- the two are
  fully decoupled, not merely "weights ignored in practice".
- Family/correlation-group diversity is enforced at roster *load*:
  `enforce_diversity` mirrors `adversary.validate_roster_diversity`'s
  *pattern* (same claim, C8 CLAIM 5) without importing that module --
  same MASTER SS1A precedent `playbooks.py` already established for the
  red-side `playbooks.py` file.
- Abstentions count against participation: an `abstained` seat-turn is a
  participation-denominator hit, never a free pass.
"""

from __future__ import annotations

from typing import Any

from . import config as bully_config

__all__ = ["recompute", "enforce_diversity", "ELIGIBILITY_STATES"]

ELIGIBILITY_STATES = ("candidate", "eligible", "probation", "ineligible", "retired")

_MIN_WEIGHT = 0.5
_MAX_WEIGHT = 2.0
_MIN_SAMPLE_FOR_SIGNAL = 3  # below this, a seat is "candidate" (not enough signal yet)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _score_seat(record: dict[str, Any], *, min_participation: float) -> dict[str, Any]:
    """Pure per-seat metrics + eligibility + bounded advisory weight."""
    objections = record.get("objections") or []
    cousin_calls = record.get("cousin_calls") or []
    opportunities = record.get("opportunities", len(objections) + len(cousin_calls))
    abstentions = record.get("abstentions", 0)

    known_objections = [o for o in objections if o.get("upheld") is not None]
    upheld_count = sum(1 for o in known_objections if o["upheld"])
    objection_precision = _ratio(upheld_count, len(known_objections))
    total_upheld_in_window = record.get("total_upheld_in_window", upheld_count)
    objection_recall = _ratio(upheld_count, total_upheld_in_window)

    known_calls = [c for c in cousin_calls if c.get("correct") is not None]
    correct_calls = sum(1 for c in known_calls if c["correct"])
    cousin_call_correctness = _ratio(correct_calls, len(known_calls))

    citation_scores = [c for c in record.get("citation_validity_samples", []) if c is not None]
    citation_validity = (sum(citation_scores) / len(citation_scores)) if citation_scores else None

    # I-19 "abstentions count against participation": every opportunity
    # (objection or cousin-call turn) the seat *could* have weighed in on
    # is the denominator; an abstained turn still consumes a slot.
    participation = _ratio(opportunities - abstentions, opportunities) if opportunities else None

    sample_size = len(known_objections) + len(known_calls)
    signals = [
        v
        for v in (objection_precision, cousin_call_correctness, citation_validity)
        if v is not None
    ]
    composite = sum(signals) / len(signals) if signals else None

    # DATA_MODEL SS1.17's `eligibility` enum has no separate "additional-
    # review" state -- I-19's "eligibility/probation/additional-review
    # determinations" maps additional-review onto `probation` with a
    # `rationale.tier` note distinguishing "needs closer look" from
    # "participation floor missed" (both land in the same DB-enforced enum).
    tier = None
    if sample_size < _MIN_SAMPLE_FOR_SIGNAL:
        eligibility = "candidate"
    elif participation is not None and participation < min_participation:
        eligibility = "probation"
        tier = "participation_floor_missed"
    elif composite is not None and composite < 0.3:
        eligibility = "ineligible"
    elif composite is not None and composite < 0.55:
        eligibility = "probation"
        tier = "additional_review"
    else:
        eligibility = "eligible"

    if composite is None:
        advisory_weight = 1.0
    else:
        advisory_weight = round(_MIN_WEIGHT + (_MAX_WEIGHT - _MIN_WEIGHT) * composite, 4)
        advisory_weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, advisory_weight))

    rationale = {
        "sample_size": sample_size,
        "objection_precision": objection_precision,
        "objection_recall": objection_recall,
        "cousin_call_correctness": cousin_call_correctness,
        "citation_validity": citation_validity,
        "participation": participation,
        "composite": composite,
        "tier": tier,
    }

    return {
        "seat_id": record["seat_id"],
        "independence_family": record.get("independence_family"),
        "capability_suite_version": record.get("capability_suite_version"),
        "citation_validity": citation_validity,
        "objection_precision": objection_precision,
        "objection_recall": objection_recall,
        "cousin_call_correctness": cousin_call_correctness,
        "abstention_quality": participation,
        "latency_cost": {
            "latency_s": record.get("latency_s"),
            "cost": record.get("cost"),
        },
        "eligibility": eligibility,
        "advisory_weight": advisory_weight,
        "rationale": rationale,
    }


def recompute(
    window: dict[str, Any], seat_records: list[dict[str, Any]], *, min_participation: float = 0.6
) -> dict[str, Any]:
    """I-19 `recompute(window) -> RosterUpdate`. `min_participation`
    defaults to `heart.yaml::council.min_participation`'s 0.6 floor
    (already a config dial, MASTER SS11 -- pass the loaded value rather
    than relying on this default in production callers)."""
    seats = [_score_seat(r, min_participation=min_participation) for r in seat_records]
    content_key = "roster-" + bully_config.content_hash(
        {"window": window, "seats": [(s["seat_id"], s["rationale"]) for s in seats]}
    )
    return {"window": window, "content_key": content_key, "seats": seats}


def enforce_diversity(
    active_seats: list[dict[str, Any]], *, min_seats: int, min_independence_families: int
) -> None:
    """I-19 'family/correlation-group diversity enforced at roster load'
    (C8 CLAIM 5's pattern, mirrored not imported -- see module docstring
    A1). Raises `ValueError` on a roster too small or too mono-family to
    activate; never silently accepts a correlated roster."""
    if len(active_seats) < min_seats:
        raise ValueError(f"ROSTER has {len(active_seats)} active seat(s), needs >= {min_seats}")
    families = {s.get("independence_family") for s in active_seats}
    if len(families) < min_independence_families:
        raise ValueError(
            f"ROSTER spans {len(families)} independent famil{'y' if len(families) == 1 else 'ies'} "
            f"({sorted(str(f) for f in families)}), needs >= {min_independence_families} -- "
            "mono-family roster rejected"
        )
