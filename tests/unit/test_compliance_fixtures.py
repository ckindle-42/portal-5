"""Unit tests for tests/lib/compliance_fixtures.py.

Validates fixture loading + scenario expansion. Uses the actual repo
fixture file (tests/fixtures/compliance_scenarios.yaml) as input — not a
mock — so any malformed YAML is caught here.
"""

from __future__ import annotations

from tests.lib import compliance_fixtures as cf


def test_scenarios_yaml_loads():
    raw = cf.load_scenarios_yaml()
    assert "frameworks" in raw
    assert "scenarios" in raw
    assert len(raw["frameworks"]) >= 7
    assert len(raw["scenarios"]) >= 8


def test_compliance_personas_discovered():
    slugs = cf.load_compliance_persona_slugs()
    assert "complianceanalyst" in slugs
    assert "nerccipcomplianceanalyst" in slugs
    assert "cippolicywriter" in slugs
    assert "hipaaprivacyofficer" in slugs
    assert "gdprdpoadvisor" in slugs
    assert "soc2auditor" in slugs


def test_scenarios_expand_to_concrete_pairs():
    concrete = cf.expand_scenarios()
    assert len(concrete) > 100, f"only {len(concrete)} concrete scenarios"


def test_framework_substitution_works():
    concrete = cf.expand_scenarios()
    multi_fw = [c for c in concrete if c.scenario_id == "gap-analysis-table-structure"]
    for c in multi_fw[:3]:
        assert "{framework_label}" not in c.prompt
        assert "{example_requirement}" not in c.prompt
        assert c.framework_id is not None


def test_insufficient_context_scenario_not_multi_framework():
    concrete = cf.expand_scenarios()
    insf = [c for c in concrete if c.scenario_id == "insufficient-context-vague-prompt"]
    for c in insf:
        assert c.framework_id is None


def test_run_assertions_dispatches_correctly():
    concrete = cf.expand_scenarios()
    sample = next(
        c for c in concrete
        if c.scenario_id == "insufficient-context-vague-prompt"
    )
    response_pass = "Insufficient context — needed: framework, scope."
    outcome = cf.run_assertions(sample, response_pass)
    assert outcome.status == "PASS", str(outcome.results)

    response_fail = "Yes, you appear to be compliant overall."
    outcome = cf.run_assertions(sample, response_fail)
    assert outcome.status == "FAIL"


def test_unknown_assertion_spec_doesnt_crash():
    """Fixture refers to an unimplemented assertion → INFO result, no crash."""
    bad_scenario = cf.ConcreteScenario(
        scenario_id="x",
        persona_slug="complianceanalyst",
        framework_id="GDPR",
        prompt="anything",
        assertion_specs=("not_a_real_assertion",),
    )
    outcome = cf.run_assertions(bad_scenario, "any response")
    assert len(outcome.results) == 1
    assert outcome.results[0].severity == "INFO"
    assert "unknown assertion spec" in outcome.results[0].detail
