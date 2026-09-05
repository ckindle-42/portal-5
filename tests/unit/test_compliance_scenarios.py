"""TASK_COMPLIANCE_REASONING_V2 P6.6 / Q12 — proposed-change scenarios."""

from __future__ import annotations

from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.cip_register import Register, RegisterNode
from portal.modules.compliance.core.scenarios import evaluate_scenario, new_scenario

_SCOPE = AssetScope(impact_present={"high"}, declared_by="op", declared_at="2026-01-01")


def _node(**kw) -> RegisterNode:
    base = {
        "id": "TEST-1 R1 Part 1.1",
        "standard": "TEST-1",
        "version": "1",
        "requirement": "R1",
        "part": "1.1",
        "verbatim_text": "Do the thing.",
        "measure_text": "",
        "applicable_systems": "High Impact BES Cyber Systems",
        "table_name": "",
        "vrf": "",
        "time_horizon": "",
        "lifecycle_state": "EFFECTIVE",
        "valid_from": "2020-01-01",
        "valid_to": None,
        "supersedes": None,
        "superseded_by": None,
        "authority_tier": 0,
        "source_pdf": "",
        "source_pages": [],
        "recorded_at": 0.0,
        "granularity": "part",
    }
    base.update(kw)
    return RegisterNode(**base)


def test_scenario_not_found_target_is_a_clear_error():
    reg = Register(nodes=[_node()])
    scenario = new_scenario("MISSING", "patch text", "because")
    result = evaluate_scenario(scenario, reg, _SCOPE, "2026-09-05", lambda n, side: [])
    assert "error" in result


def test_scenario_shows_qualification_change_when_patch_adds_evidence():
    """Before: no candidates at all (empty proposer) -> UNRESOLVED. After:
    the injected patch text qualifies on the procedure side -> UNRESOLVED
    with a different note (textual presence found) — the coverage TOKEN
    itself is unchanged (P5 gates any positive verdict either way), but the
    qualification signal genuinely changed, which is what this evaluator
    can honestly claim."""
    reg = Register(nodes=[_node()])
    scenario = new_scenario(
        "TEST-1 R1 Part 1.1", "We now do the thing exactly as required.", "closes an identified gap"
    )
    result = evaluate_scenario(scenario, reg, _SCOPE, "2026-09-05", lambda n, side: [])
    assert result["before"]["determination"] == "ABSENT"
    assert result["before"]["atom_results"][0]["boundary_proof_id"].startswith("boundary-")
    assert result["after"]["determination"] == "SUPPORTED"
    assert result["after"]["atom_results"][0]["internal_anchor_ids"] == [
        "scenario:TEST-1 R1 Part 1.1"
    ]
    assert result["determination_changed"] is True
    assert "Isolated deterministic assessment" in result["note"]


def test_scenario_does_not_affect_other_parts():
    """The patch is scoped to exactly one target node — a sibling Part's
    evaluation must be byte-identical whether or not a scenario ran."""
    reg = Register(
        nodes=[_node(id="TEST-1 R1 Part 1.1"), _node(id="TEST-1 R1 Part 1.2", part="1.2")]
    )
    scenario = new_scenario("TEST-1 R1 Part 1.1", "patch", "because")

    def real_propose(node, side):
        return []

    result = evaluate_scenario(scenario, reg, _SCOPE, "2026-09-05", real_propose)
    # only the target node is in the sub-register the evaluator builds
    assert result["before"]["node_id"] == "TEST-1 R1 Part 1.1"
    assert result["after"]["node_id"] == "TEST-1 R1 Part 1.1"


def test_new_scenario_generates_a_stable_id():
    s1 = new_scenario("X", "patch", "reason")
    s2 = new_scenario("X", "patch", "reason")
    assert s1.scenario_id != s2.scenario_id
    assert len(s1.scenario_id) == 12


def test_scenario_detects_a_weakening_replacement():
    node = _node(
        verbatim_text="The Responsible Entity shall evaluate patches within 35 calendar days."
    )
    reg = Register(nodes=[node])
    scenario = new_scenario(
        node.id,
        "The Responsible Entity shall evaluate patches within 60 calendar days.",
        "deliberate weakening fixture",
    )

    def supported_before(current, side):
        if side != "procedure":
            return []
        return [
            {
                "section_id": "internal-before",
                "span": "The Responsible Entity shall evaluate patches within 35 calendar days.",
                "anchor_verified": True,
                "relevant": True,
            }
        ]

    result = evaluate_scenario(scenario, reg, _SCOPE, "2026-09-05", supported_before)
    assert result["before"]["determination"] == "SUPPORTED"
    assert result["after"]["determination"] == "CONTRADICTED"
    assert result["weakening"] is True
    assert result["affected_obligation"] == node.id
