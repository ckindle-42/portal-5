"""Unit tests for tests/lib/coding_fixtures.py."""

from __future__ import annotations

from tests.lib import coding_fixtures as cf


def test_coding_scenarios_yaml_loads():
    raw = cf.load_scenarios_yaml()
    assert "scenarios" in raw
    sids = [s["id"] for s in raw["scenarios"]]
    assert "self-evident-canvas-snake" in sids
    assert "stdlib-only-python-csv" in sids
    assert len(sids) >= 5


def test_coding_personas_discovered():
    slugs = cf.load_coding_persona_slugs()
    assert len(slugs) >= 5


def test_coding_scenarios_expand():
    concrete = cf.expand_scenarios()
    assert len(concrete) > 10
    sids = {c.scenario_id for c in concrete}
    assert "self-evident-canvas-snake" in sids
    assert "sql-join-with-aggregation" in sids


def test_run_assertions_dispatches_language():
    sample = next(
        c for c in cf.expand_scenarios()
        if c.scenario_id == "self-evident-rust-fizzbuzz"
    )
    rust_response = """
    Here it is:

    ```rust
    fn main() {
        for n in 1..=100 {
            let s = match (n % 3, n % 5) {
                (0, 0) => "FizzBuzz".to_string(),
                (0, _) => "Fizz".to_string(),
                (_, 0) => "Buzz".to_string(),
                _      => n.to_string(),
            };
            println!("{}", s);
        }
    }
    ```
    """
    outcome = cf.run_assertions(sample, rust_response)
    assert outcome.status == "PASS", str(outcome.results)


def test_constraint_violation_detected():
    sample = next(
        c for c in cf.expand_scenarios()
        if c.scenario_id == "stdlib-only-python-csv"
    )
    bad_response = """
    ```python
    import pandas as pd
    df = pd.read_csv("...")
    print(df.groupby(df.columns[0])[df.columns[1]].mean())
    ```
    """
    outcome = cf.run_assertions(sample, bad_response)
    assert outcome.status == "FAIL"


def test_unknown_coding_assertion_doesnt_crash():
    bad = cf.ConcreteScenario(
        scenario_id="x",
        persona_slug="goengineer",
        framework_id=None,
        prompt="anything",
        assertion_specs=("not_a_real_assertion",),
    )
    outcome = cf.run_assertions(bad, "any response")
    assert len(outcome.results) == 1
    assert outcome.results[0].severity == "INFO"
