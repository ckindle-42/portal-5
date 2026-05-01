"""Loader and parameterizer for tests/fixtures/compliance_scenarios.yaml.

Produces concrete (persona_slug, framework, prompt, assertion_callables) tuples
that the acceptance and matrix harnesses iterate. The fixture YAML is the
single source of truth — Python code below is purely a transform.
"""

from __future__ import annotations

import glob
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.lib import compliance_assertions as ca


# ── Resolve file paths ────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_PATH = _REPO_ROOT / "tests" / "fixtures" / "compliance_scenarios.yaml"
PERSONAS_DIR = _REPO_ROOT / "config" / "personas"


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Framework:
    id: str
    label: str
    example_requirement: str
    authoritative_source: str


@dataclass(frozen=True)
class ConcreteScenario:
    """A scenario after framework substitution — directly runnable."""

    scenario_id: str
    persona_slug: str
    framework_id: str | None  # None = framework-independent
    prompt: str
    assertion_specs: tuple[str, ...]  # e.g. ("structural.table_columns", ...)

    @property
    def display_name(self) -> str:
        fw = self.framework_id or "any"
        return f"{self.scenario_id}[{fw}]→{self.persona_slug}"


# ── Loader ────────────────────────────────────────────────────────────────

def load_scenarios_yaml(path: Path = SCENARIOS_PATH) -> dict[str, Any]:
    """Read and parse the scenario YAML."""
    if not path.is_file():
        raise FileNotFoundError(f"compliance scenarios fixture missing: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_compliance_persona_slugs(
    personas_dir: Path = PERSONAS_DIR,
) -> tuple[str, ...]:
    """Read every persona YAML under config/personas/ and return the slugs of
    those with category == 'compliance'.
    """
    slugs: list[str] = []
    for f in sorted(glob.glob(str(personas_dir / "*.yaml"))):
        try:
            d = yaml.safe_load(open(f)) or {}
            if d.get("category") == "compliance" and d.get("slug"):
                slugs.append(d["slug"])
        except Exception:  # pragma: no cover — IO/parse errors
            continue
    return tuple(slugs)


# ── Expansion ─────────────────────────────────────────────────────────────

def _resolve_personas(
    applies_to: list[str], all_compliance: tuple[str, ...]
) -> tuple[str, ...]:
    """Expand the applies_to list. The token 'compliance:*' expands to every
    compliance-category persona slug.
    """
    out: list[str] = []
    for entry in applies_to:
        if entry == "compliance:*":
            out.extend(all_compliance)
        else:
            out.append(entry)
    # Dedup while preserving order
    seen: set[str] = set()
    return tuple(s for s in out if not (s in seen or seen.add(s)))


def expand_scenarios(
    raw: dict[str, Any] | None = None,
    personas_dir: Path = PERSONAS_DIR,
) -> tuple[ConcreteScenario, ...]:
    """Expand the YAML fixture into concrete (persona, framework) scenarios.

    For each scenario:
        - if multi_framework=True, emit one ConcreteScenario per (framework,
          persona) pair (with placeholder substitution)
        - if multi_framework=False, emit one ConcreteScenario per persona
          (no substitution)

    Filters duplicates by display_name.
    """
    raw = raw or load_scenarios_yaml()
    frameworks = {f["id"]: Framework(**f) for f in raw.get("frameworks", [])}
    compliance_personas = load_compliance_persona_slugs(personas_dir)

    out: list[ConcreteScenario] = []
    for scenario in raw.get("scenarios", []):
        sid = scenario["id"]
        prompt_template = scenario["prompt"]
        applies_to = scenario.get("applies_to", [])
        assertion_specs = tuple(scenario.get("assertions", []))
        personas = _resolve_personas(applies_to, compliance_personas)

        if scenario.get("multi_framework"):
            for fw_id, fw in frameworks.items():
                concrete_prompt = prompt_template.format(
                    framework_label=fw.label,
                    example_requirement=fw.example_requirement,
                )
                for persona in personas:
                    out.append(
                        ConcreteScenario(
                            scenario_id=sid,
                            persona_slug=persona,
                            framework_id=fw_id,
                            prompt=concrete_prompt,
                            assertion_specs=assertion_specs,
                        )
                    )
        else:
            for persona in personas:
                out.append(
                    ConcreteScenario(
                        scenario_id=sid,
                        persona_slug=persona,
                        framework_id=None,
                        prompt=prompt_template,
                        assertion_specs=assertion_specs,
                    )
                )
    return tuple(out)


# ── Assertion dispatch ────────────────────────────────────────────────────

def _resolve_citation_assertion(
    spec: str,
) -> "tuple[str | None, str | None]":
    """Parse 'citation.format[FRAMEWORK]' into ('citation.format', FRAMEWORK).
    Bare 'citation.format' returns ('citation.format', None) — caller resolves
    framework from the scenario context.
    """
    if not spec.startswith("citation.format"):
        return None, None
    rest = spec[len("citation.format"):]
    if rest.startswith("[") and rest.endswith("]"):
        return "citation.format", rest[1:-1]
    return "citation.format", None


def run_assertions(
    scenario: ConcreteScenario, response: str
) -> ca.ScenarioOutcome:
    """Run all assertions for one scenario against one response. Returns a
    ScenarioOutcome aggregating every result.
    """
    results: list[ca.AssertionResult] = []
    for spec in scenario.assertion_specs:
        cit_name, cit_framework = _resolve_citation_assertion(spec)
        if cit_name == "citation.format":
            framework = cit_framework or scenario.framework_id
            if framework:
                results.append(
                    ca.assert_citation_present(response, framework)
                )
            continue
        # Plain assertion dispatch table
        dispatch = {
            "structural.table_columns": ca.assert_table_columns,
            "structural.policy_sections": ca.assert_policy_sections,
            "classification.exact_token": ca.assert_classification_token,
            "anti_fabrication.refusal_pattern":
                ca.assert_no_fabrication_when_asked,
            "refuse_to_certify": ca.assert_refuses_to_certify,
            "insufficient_context.exact_phrase":
                ca.assert_insufficient_context_pattern,
            "policy.modal_verbs": ca.assert_uses_modal_verbs,
        }
        fn = dispatch.get(spec)
        if fn is None:
            results.append(
                ca.AssertionResult(
                    name=spec,
                    passed=False,
                    detail=f"unknown assertion spec '{spec}' — fixture refers to an assertion not implemented",
                    severity="INFO",
                )
            )
            continue
        results.append(fn(response))

    return ca.ScenarioOutcome(
        scenario_id=scenario.scenario_id,
        framework=scenario.framework_id,
        results=tuple(results),
    )
