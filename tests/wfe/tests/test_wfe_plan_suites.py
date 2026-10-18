"""The decision floor vs the suites plans reference.

decision.py refuses any cell with fewer than DECISION_FLOOR compared tasks — the
defect that made every O5 cell NO_DECISION live (wfe_math_20261018b: 12-task suites
against a 30-task floor). This file pins the invariant that defect violated: every
PRODUCTION suite any plan references carries at least the floor.

Scope, stated plainly: suites whose name does not end in ``_production`` (coding,
research, creative, the compliance_agentic* sets, rig_short) are the pre-decision
diagnostic instruments — engine A/B sets, seat baselines, prompt-surface loopsets —
and are out of the floor's scope, which decision.py applies to decision cells. Two
production-named suites are pinned at their known counts as recorded gaps rather than
silently exempted: general_core_production (24 — the uncensored lanes' tool-compatible
half of general_production cannot reach the floor without re-scoping O3's suite) and
rig_production (4 — the P2a acceptance rig, production-named only by accident).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tests.wfe.decision import DECISION_FLOOR

REPO = Path(__file__).resolve().parents[3]
PLANS = REPO / "tests/wfe/plans"
SUITES = REPO / "tests/wfe/suites"

#: Production-named suites recorded UNDER the floor, with the reason they stand.
KNOWN_GAPS = {
    "general_core_production": (
        24,
        "the uncensored lanes' tool-compatible subset of general_production; reaching "
        "30 needs new computed/memory kinds in O3's suite — an orchestrator decision",
    ),
    "rig_production": (
        4,
        "the P2a acceptance rig, production-named only by accident; it is a fixture, "
        "not a decision instrument",
    ),
}


def _referenced_production_suites() -> dict[str, set[str]]:
    """suite name -> the plans that reference it (home or discovery)."""
    out: dict[str, set[str]] = {}
    for plan_path in sorted(PLANS.glob("*.yaml")):
        plan = yaml.safe_load(plan_path.read_text()) or {}
        for wl in (plan.get("workloads") or {}).values():
            for suite in [wl.get("home")] + list(wl.get("discovery") or []):
                if suite and suite.endswith("_production"):
                    out.setdefault(suite, set()).add(plan_path.name)
    return out


def _count(suite: str) -> int:
    return len((SUITES / f"{suite}.jsonl").read_text().splitlines())


def test_every_referenced_production_suite_meets_the_decision_floor():
    under = []
    for suite, plans in _referenced_production_suites().items():
        if suite in KNOWN_GAPS:
            continue
        n = _count(suite)
        if n < DECISION_FLOOR:
            under.append(f"{suite} ({n} tasks, referenced by {sorted(plans)})")
    assert under == [], f"suites under DECISION_FLOOR={DECISION_FLOOR}: {under}"


def test_the_known_gaps_are_exactly_at_their_recorded_counts():
    for suite, (expected, reason) in KNOWN_GAPS.items():
        assert suite in _referenced_production_suites(), (
            f"{suite} is no longer referenced; retire the gap"
        )
        assert _count(suite) == expected, f"{suite}: {reason}"


def test_every_plan_suite_file_exists():
    missing = []
    for plan_path in sorted(PLANS.glob("*.yaml")):
        plan = yaml.safe_load(plan_path.read_text()) or {}
        for wl in (plan.get("workloads") or {}).values():
            for suite in [wl.get("home")] + list(wl.get("discovery") or []):
                if suite and not (SUITES / f"{suite}.jsonl").exists():
                    missing.append(f"{plan_path.name}: {suite}")
    assert missing == [], f"plans reference missing suites: {missing}"


def test_the_six_o5_suites_carry_the_full_shape():
    """36 tasks / 12 screen: the expansion that answered wfe_math_20261018b."""
    for suite, kinds in {
        "reasoning_math_production": {"arithmetic": 12, "combinatorics": 12, "logic-grid": 12},
        "cad_production": {"plate-holes": 12, "extrusion": 12, "revolve": 12},
        "tools_specialist_production": {"compute": 12, "store-recall": 12, "chain": 12},
        "reading_production": {"determination": 12, "lookup": 24},
        "extract_production": {"entities": 12, "fields": 12, "summary-facts": 12},
        "routing_production": {
            "auto-coding": 9,
            "auto-compliance": 9,
            "auto-security": 9,
            "auto-spl": 9,
        },
    }.items():
        tasks = [json.loads(x) for x in (SUITES / f"{suite}.jsonl").read_text().splitlines()]
        assert len(tasks) == 36 and sum(t["screen"] for t in tasks) == 12, suite
        by_kind: dict[str, int] = {}
        for t in tasks:
            by_kind[t["kind"]] = by_kind.get(t["kind"], 0) + 1
        assert by_kind == kinds, suite
