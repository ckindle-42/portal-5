"""Loader for tests/fixtures/coding_scenarios.yaml.

Mirrors tests/lib/compliance_fixtures.py — same ConcreteScenario type,
same expand_scenarios() / run_assertions() interface — so the matrix
driver consumes both identically. The dispatch table here knows about
coding-specific assertions (language.X, constraint.X).
"""

from __future__ import annotations

import glob
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.lib import coding_assertions as ca
from tests.lib.compliance_fixtures import ConcreteScenario  # reuse type

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_PATH = _REPO_ROOT / "tests" / "fixtures" / "coding_scenarios.yaml"
PERSONAS_DIR = _REPO_ROOT / "config" / "personas"


def load_scenarios_yaml(path: Path = SCENARIOS_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"coding scenarios fixture missing: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_coding_persona_slugs(
    personas_dir: Path = PERSONAS_DIR,
) -> tuple[str, ...]:
    out: list[str] = []
    coding_cats = ("coding", "software", "development", "systems")
    for f in sorted(glob.glob(str(personas_dir / "*.yaml"))):
        try:
            d = yaml.safe_load(open(f)) or {}
            if d.get("category") in coding_cats and d.get("slug"):
                out.append(d["slug"])
        except Exception:
            continue
    return tuple(out)


def _resolve_personas(
    applies_to: list[str], all_coding: tuple[str, ...]
) -> tuple[str, ...]:
    out: list[str] = []
    for entry in applies_to:
        if entry == "coding:*":
            out.extend(all_coding)
        else:
            out.append(entry)
    seen: set[str] = set()
    return tuple(s for s in out if not (s in seen or seen.add(s)))


def expand_scenarios(
    raw: dict[str, Any] | None = None,
    personas_dir: Path = PERSONAS_DIR,
) -> tuple[ConcreteScenario, ...]:
    raw = raw or load_scenarios_yaml()
    coding_personas = load_coding_persona_slugs(personas_dir)
    out: list[ConcreteScenario] = []

    for scenario in raw.get("scenarios", []):
        sid = scenario["id"]
        prompt = scenario["prompt"]
        applies_to = scenario.get("applies_to", [])
        assertion_specs = tuple(scenario.get("assertions", []))
        context_tag = scenario.get("language") or scenario.get("constraint")
        personas = _resolve_personas(applies_to, coding_personas)

        for persona in personas:
            out.append(
                ConcreteScenario(
                    scenario_id=sid,
                    persona_slug=persona,
                    framework_id=context_tag,
                    prompt=prompt,
                    assertion_specs=assertion_specs,
                )
            )
    return tuple(out)


def _resolve_parameterized_assertion(
    spec: str,
) -> tuple[str | None, str | None]:
    if "." not in spec:
        return None, None
    base, _, param = spec.partition(".")
    if base in ("language", "constraint"):
        return base, param
    return None, None


def run_assertions(
    scenario: ConcreteScenario, response: str
):
    from tests.lib.compliance_assertions import ScenarioOutcome

    results: list = []
    for spec in scenario.assertion_specs:
        base, param = _resolve_parameterized_assertion(spec)
        if base == "language":
            results.append(ca.assert_uses_language(response, param or ""))
            continue
        if base == "constraint":
            results.append(ca.assert_respects_constraint(response, param or ""))
            continue

        dispatch = {
            "structural.code_block_present": ca.assert_code_block_present,
            "structural.no_truncation_or_placeholders":
                ca.assert_no_truncation_or_placeholders,
            "behavioral.no_clarification_stall":
                ca.assert_no_clarification_stall,
        }
        fn = dispatch.get(spec)
        if fn is None:
            from tests.lib.compliance_assertions import AssertionResult
            results.append(
                AssertionResult(
                    name=spec,
                    passed=False,
                    detail=f"unknown coding assertion '{spec}'",
                    severity="INFO",
                )
            )
            continue
        results.append(fn(response))

    return ScenarioOutcome(
        scenario_id=scenario.scenario_id,
        framework=scenario.framework_id,
        results=tuple(results),
    )
