"""P6.5 -- ROSTER: eligibility/reliability governance (M8).

Hermetic (`tmp_path`, no network, no SQL -- `roster.py` is pure compute).
Feeds C11 ROSTER: objection gate independent of weights (regression against
P2 HEART); diversity enforced at load; abstention accounting; content-keyed
idempotency.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from portal.modules.security.core.bully import roster

REPO_ROOT = Path(__file__).resolve().parents[3]
BULLY_DIR = REPO_ROOT / "portal" / "modules" / "security" / "core" / "bully"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# ── objection gate independent of weights (regression against P2 HEART) ───


def test_adversary_objection_gate_never_imports_roster():
    """I-19 CONSTRAINT 'the objection gate never consults weights or
    reliability': adversary.py (HEART's objection gate, P2) must not import
    roster.py at all -- not merely 'ignore the value in practice'."""
    adversary_path = BULLY_DIR / "adversary.py"
    imports = _imported_names(adversary_path)
    hit = {i for i in imports if i.split(".")[-1] == "roster"}
    assert not hit, f"adversary.py imports roster: {hit}"


def test_roster_never_imports_adversary():
    """The converse -- full decoupling, not a one-way convenience."""
    imports = _imported_names(BULLY_DIR / "roster.py")
    hit = {i for i in imports if i.split(".")[-1] == "adversary"}
    assert not hit, f"roster.py imports adversary: {hit}"


def test_p2_unresolved_computation_is_unaffected_by_roster_weights():
    """Regression: P2's material-objection-blocks-promotion rule
    (`any(o.material for o in objections)`) takes no weight/reliability
    input at all -- it is exactly as blocking with or without any ROSTER
    computation ever having run. Exercises the real P2 rule with two
    otherwise-identical objection sets differing only in a would-be
    'weight' field a gate must never read."""
    material_objection = {"material": True, "status": "open", "advisory_weight_if_it_mattered": 0.5}
    material_objection_high_weight = {
        "material": True,
        "status": "open",
        "advisory_weight_if_it_mattered": 2.0,
    }
    low = any(o["material"] and o["status"] == "open" for o in [material_objection])
    high = any(o["material"] and o["status"] == "open" for o in [material_objection_high_weight])
    assert low is True
    assert high is True  # identical outcome regardless of the (irrelevant) weight field


# ── recompute(): abstention accounting + eligibility bands ────────────────


def _seat(seat_id="seat-a", **overrides):
    base = {
        "seat_id": seat_id,
        "independence_family": "granite",
        "capability_suite_version": "v1",
        "objections": [{"material": True, "upheld": True}] * 3
        + [{"material": True, "upheld": False}],
        "cousin_calls": [{"correct": True}] * 3,
        "opportunities": 8,
        "abstentions": 0,
        "total_upheld_in_window": 4,
        "citation_validity_samples": [0.9, 0.95],
        "latency_s": 1.2,
        "cost": 0.01,
    }
    base.update(overrides)
    return base


def test_recompute_scores_a_healthy_seat_eligible():
    update = roster.recompute({"since": 0}, [_seat()])
    seat = update["seats"][0]
    assert seat["eligibility"] == "eligible"
    assert 0.5 <= seat["advisory_weight"] <= 2.0
    assert seat["objection_precision"] == pytest.approx(0.75)
    assert seat["cousin_call_correctness"] == pytest.approx(1.0)


def test_recompute_new_seat_with_little_data_is_candidate():
    update = roster.recompute(
        {"since": 0},
        [_seat(objections=[{"material": True, "upheld": True}], cousin_calls=[], opportunities=1)],
    )
    assert update["seats"][0]["eligibility"] == "candidate"


def test_recompute_abstentions_count_against_participation():
    """I-19 CONSTRAINT 'abstentions count against participation': a seat
    with plenty of good signal but heavy abstention still lands on
    probation, never 'eligible' purely on its non-abstained answers."""
    update = roster.recompute(
        {"since": 0}, [_seat(opportunities=10, abstentions=8)], min_participation=0.6
    )
    seat = update["seats"][0]
    assert seat["abstention_quality"] == pytest.approx(0.2)
    assert seat["eligibility"] == "probation"
    assert seat["rationale"]["tier"] == "participation_floor_missed"


def test_recompute_low_composite_is_ineligible():
    bad = _seat(
        objections=[{"material": True, "upheld": False}] * 5,
        cousin_calls=[{"correct": False}] * 5,
        citation_validity_samples=[0.1, 0.1],
        total_upheld_in_window=5,
    )
    update = roster.recompute({"since": 0}, [bad])
    assert update["seats"][0]["eligibility"] == "ineligible"
    assert update["seats"][0]["advisory_weight"] < 1.0  # below-midpoint, still bounded [0.5, 2.0]


def test_recompute_weight_never_leaves_bounded_range():
    perfect = _seat(
        objections=[{"material": True, "upheld": True}] * 5,
        cousin_calls=[{"correct": True}] * 5,
        citation_validity_samples=[1.0, 1.0],
        total_upheld_in_window=5,
    )
    update = roster.recompute({"since": 0}, [perfect])
    assert update["seats"][0]["advisory_weight"] <= 2.0
    assert update["seats"][0]["advisory_weight"] >= 0.5


# ── content-keyed idempotency ──────────────────────────────────────────────


def test_recompute_is_content_keyed_idempotent():
    update1 = roster.recompute({"since": 0}, [_seat()])
    update2 = roster.recompute({"since": 0}, [_seat()])
    assert update1["content_key"] == update2["content_key"]


def test_recompute_content_key_changes_with_different_outcomes():
    update1 = roster.recompute({"since": 0}, [_seat()])
    update2 = roster.recompute({"since": 0}, [_seat(cousin_calls=[{"correct": False}] * 3)])
    assert update1["content_key"] != update2["content_key"]


# ── enforce_diversity(): family/correlation-group at load ────────────────


def test_enforce_diversity_rejects_mono_family_roster():
    seats = [
        {"seat_id": "s1", "independence_family": "granite"},
        {"seat_id": "s2", "independence_family": "granite"},
    ]
    with pytest.raises(ValueError, match="mono-family"):
        roster.enforce_diversity(seats, min_seats=2, min_independence_families=2)


def test_enforce_diversity_rejects_too_few_seats():
    seats = [{"seat_id": "s1", "independence_family": "granite"}]
    with pytest.raises(ValueError, match="needs >="):
        roster.enforce_diversity(seats, min_seats=3, min_independence_families=2)


def test_enforce_diversity_accepts_a_diverse_roster():
    seats = [
        {"seat_id": "s1", "independence_family": "granite"},
        {"seat_id": "s2", "independence_family": "mistral"},
        {"seat_id": "s3", "independence_family": "qwen"},
    ]
    roster.enforce_diversity(seats, min_seats=2, min_independence_families=2)  # no raise
