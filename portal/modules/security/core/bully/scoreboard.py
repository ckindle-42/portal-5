"""bully.scoreboard -- SCORE, the discovery-first scoreboard (P4.2, I-10).

Pure compute over injected data (MASTER SS3): no SQL, no network. Mirrors
the documented split used by `drift_engine.py`/`costing.py` -- I-10's
literal `update(hunt_id)` signature is reinterpreted the same way: the
*pure* function scores a list of records the caller already fetched via
`store.py` (this module never touches `hunt_state.db` itself); `hunt_id`
is folded into `update`'s output purely as provenance.

Preserves `notify_scoreboard.py`'s catch/trust semantics (I-10) while
adding the discovery axis:

- **catch** (Axis 1) -- a cousin grade "notified": `ANOMALOUS_UNCLASSIFIED`
  is always a catch (BN), and so is any non-`DIFFERENT` relationship (the
  cousin engine placed the subject in a family or flagged it, as opposed
  to concluding it isn't a cousin at all).
- **trust** (ordinal, preserved: `CONFIRMED_CORRECT > HONEST_ANOMALY >
  CONFIRMED_WRONG`) -- bully is label-blind in production (Rule BM: never
  import `recall_attribution`/corpus ground truth), so unlike
  `notify_scoreboard`'s corpus-oracle-backed axis, this build's trust
  ordinal is grounded in the BIN pipeline's own operator-confirmed outcome
  (`candidate_state`, already real operator judgment, not a ground-truth
  import): `PROMOTED` -> CONFIRMED_CORRECT, `KILLED`/`DISPROVED` ->
  CONFIRMED_WRONG, `ANOMALOUS_UNCLASSIFIED` relationship (with or without a
  resolved candidate) -> HONEST_ANOMALY. A record with no candidate yet and
  no anomaly is simply not yet trust-scored (`None`) -- data absence is
  reported, never faked (I-10 FAILURE SEMANTICS).
- **discovery** (new) -- distance-weighted: the discovery product
  `(SIMILAR | NEW) x (NEAR_MISS | MISSED)` (FINAL_DESIGN SS "product
  bands") scores `composite` (the graded distance) directly, so farther
  (more novel) scores higher and NEW naturally outranks SIMILAR at the
  same coverage gap (NEW's distance band starts where SIMILAR's ends).
  `ANOMALOUS_UNCLASSIFIED` is the concept's primary product and always
  scores at least as high as the discovery floor. `SAME` (known-bad) never
  scores on this axis (0.0) -- "far-NEW >= known-bad" holds trivially and
  monotonically for every value of distance.
- benign false-flag typing (BQ) -- preserved from `notify_scoreboard`:
  `CONFIRMED_ON_BENIGN` / `ANOMALY_ON_BENIGN`, keyed off a caller-supplied
  `known_benign` flag (this build's known-benign signal is a live
  `known_state` entry, never a corpus ground-truth import).
"""

from __future__ import annotations

from typing import Any

__all__ = ["score_record", "update", "report"]

CONFIRMED_CORRECT = "confirmed_correct"
HONEST_ANOMALY = "honest_anomaly"
CONFIRMED_WRONG = "confirmed_wrong"

# Ordinal only -- these values encode the required preference ordering and
# must not be interpreted as cardinal utility (notify_scoreboard.py parity).
TRUSTWORTHINESS_RANK = {
    CONFIRMED_CORRECT: 2,
    HONEST_ANOMALY: 1,
    CONFIRMED_WRONG: 0,
}

CONFIRMED_ON_BENIGN = "confirmed_on_benign"
ANOMALY_ON_BENIGN = "anomaly_on_benign"

_PROMOTED_STATES = frozenset({"PROMOTED"})
_WRONG_STATES = frozenset({"KILLED", "DISPROVED"})

_DISCOVERY_RELATIONSHIPS = frozenset({"SIMILAR", "NEW"})
_DISCOVERY_RESPONSES = frozenset({"NEAR_MISS", "MISSED"})
_FAMILY_GAIN_WEIGHT = 0.25  # NEW x COVERED: family knowledge gain, not a gap
_ANOMALY_DISCOVERY_FLOOR = 0.60  # first-class catch; at least a NEW-band value


def _trust_class(relationship: str, candidate_state: str | None) -> str | None:
    if candidate_state in _PROMOTED_STATES:
        return CONFIRMED_CORRECT
    if candidate_state in _WRONG_STATES:
        return CONFIRMED_WRONG
    if relationship == "ANOMALOUS_UNCLASSIFIED":
        return HONEST_ANOMALY
    return None


def _is_catch(relationship: str) -> bool:
    """Axis-1 catch: anything the cousin engine placed or flagged, not a
    clean 'not a cousin' verdict. ANOMALOUS_UNCLASSIFIED is always a catch
    (BN), matching notify_scoreboard's NOTIFY_VERDICTS semantics."""
    return relationship != "DIFFERENT"


def _discovery_value(relationship: str, defense_response: str, composite: float) -> float:
    if relationship == "ANOMALOUS_UNCLASSIFIED":
        return max(composite, _ANOMALY_DISCOVERY_FLOOR)
    if relationship in _DISCOVERY_RELATIONSHIPS and defense_response in _DISCOVERY_RESPONSES:
        return composite
    if relationship == "NEW" and defense_response == "COVERED":
        return composite * _FAMILY_GAIN_WEIGHT
    return 0.0  # SAME (known-bad), DIFFERENT, or a covered/near-miss SAME -- no discovery credit


def score_record(record: dict[str, Any]) -> dict[str, Any]:
    """Score one cousin-assessment-shaped record.

    Expected keys: `assessment_id`, `relationship`, `defense_response`,
    `composite` (float distance), `candidate_state` (BIN `current_state` or
    `None`), `known_benign` (bool, caller-determined via live `known_state`
    -- never a corpus oracle).
    """
    relationship = record["relationship"]
    defense_response = record["defense_response"]
    composite = float(record.get("composite") or 0.0)
    candidate_state = record.get("candidate_state")
    known_benign = bool(record.get("known_benign", False))

    catch = _is_catch(relationship)
    trust = _trust_class(relationship, candidate_state)
    discovery = _discovery_value(relationship, defense_response, composite)

    false_flag_kind = None
    if known_benign and catch:
        false_flag_kind = (
            ANOMALY_ON_BENIGN if relationship == "ANOMALOUS_UNCLASSIFIED" else CONFIRMED_ON_BENIGN
        )

    return {
        "assessment_id": record.get("assessment_id"),
        "relationship": relationship,
        "defense_response": defense_response,
        "composite": composite,
        "catch": catch,
        "trust_class": None if known_benign else trust,
        "trust_rank": (None if (known_benign or trust is None) else TRUSTWORTHINESS_RANK[trust]),
        "discovery_value": 0.0 if known_benign else round(discovery, 4),
        "known_benign": known_benign,
        "false_flag": known_benign and catch,
        "false_flag_kind": false_flag_kind,
    }


def update(hunt_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """I-10 `update(hunt_id) -> ScoreboardRow`, reinterpreted (module
    docstring): scores the caller-supplied records and returns one
    per-hunt row. `records` is already read-only data the caller fetched
    from SUB (cousin assessments joined with candidate state and
    known-state) -- this function performs no I/O itself."""
    scored = [score_record(r) for r in records]
    catches = [s for s in scored if s["catch"] and not s["known_benign"]]
    trust_scored = [s for s in scored if s["trust_rank"] is not None]
    discovery_scored = [s for s in scored if s["discovery_value"] > 0.0]
    false_flags = [s for s in scored if s["false_flag"]]

    return {
        "hunt_id": hunt_id,
        "n_records": len(scored),
        "catch_count": len(catches),
        "catch_rate": (len(catches) / len(scored)) if scored else None,
        "trust_mean_rank": (
            sum(s["trust_rank"] for s in trust_scored) / len(trust_scored) if trust_scored else None
        ),
        "discovery_total": round(sum(s["discovery_value"] for s in scored), 4),
        "discovery_mean": (
            round(sum(s["discovery_value"] for s in discovery_scored) / len(discovery_scored), 4)
            if discovery_scored
            else None
        ),
        "false_flag_count": len(false_flags),
        "records": scored,
    }


def report(scope: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """I-10 `report(scope: hunt|series) -> Scoreboard`. `rows` is a list of
    `update(...)`-shaped dicts (one per hunt); `scope="hunt"` expects
    exactly one row and passes it through, `scope="series"` aggregates
    across all of them. Data absence is reported, never faked: an empty
    `rows` list for either scope yields `None` aggregates, not zeros."""
    if scope not in ("hunt", "series"):
        raise ValueError(f"unknown scoreboard report scope: {scope!r}")
    if scope == "hunt":
        if len(rows) != 1:
            raise ValueError(f"scope='hunt' expects exactly one row, got {len(rows)}")
        return {"scope": "hunt", **rows[0]}

    total_records = sum(r["n_records"] for r in rows)
    total_catches = sum(r["catch_count"] for r in rows)
    total_false_flags = sum(r["false_flag_count"] for r in rows)
    trust_ranks = [r["trust_mean_rank"] for r in rows if r["trust_mean_rank"] is not None]
    discovery_totals = [r["discovery_total"] for r in rows]

    return {
        "scope": "series",
        "n_hunts": len(rows),
        "n_records": total_records,
        "catch_count": total_catches,
        "catch_rate": (total_catches / total_records) if total_records else None,
        "trust_mean_rank": (sum(trust_ranks) / len(trust_ranks)) if trust_ranks else None,
        "discovery_total": round(sum(discovery_totals), 4) if discovery_totals else None,
        "false_flag_count": total_false_flags,
        "hunts": rows,
    }
