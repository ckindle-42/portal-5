"""Validate that promptfoo configs reference valid Portal 5 workspace models.

Every ollama:chat:<model> reference in config/promptfoo/*_quality.yaml —
including the grading provider — must resolve to a model_hint in WORKSPACES.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, ".")

CONFIG_DIR = Path("config/promptfoo")


@pytest.fixture(scope="module")
def known_models():
    from portal_pipeline.router.workspaces import WORKSPACES

    return {info["model_hint"] for info in WORKSPACES.values() if info.get("model_hint")}


def _extract_model_refs(config_path):
    refs = set()
    for line in Path(config_path).read_text().splitlines():
        m = re.search(r"ollama:chat:(\S+)", line)
        if m:
            refs.add(m.group(1).strip("\"'"))
    return refs


def _configs():
    return sorted(CONFIG_DIR.glob("*_quality.yaml")) if CONFIG_DIR.exists() else []


def test_all_configs_are_valid_yaml():
    cfgs = _configs()
    if not cfgs:
        pytest.skip("config/promptfoo/ does not exist yet")
    for cf in cfgs:
        data = yaml.safe_load(cf.read_text())
        assert isinstance(data, dict), f"{cf.name}: not a mapping"
        assert "providers" in data and "tests" in data, f"{cf.name}: missing providers/tests"


def test_all_configs_set_local_grading_provider():
    """llm-rubric must never fall back to a cloud grader on this host."""
    cfgs = _configs()
    if not cfgs:
        pytest.skip("config/promptfoo/ does not exist yet")
    for cf in cfgs:
        data = yaml.safe_load(cf.read_text())
        provider = data.get("defaultTest", {}).get("options", {}).get("provider", "")
        assert provider.startswith("ollama:"), f"{cf.name}: grading provider not local: {provider!r}"


def test_promptfoo_models_resolve_to_workspaces(known_models):
    cfgs = _configs()
    if not cfgs:
        pytest.skip("config/promptfoo/ does not exist yet")
    missing = set()
    for cf in cfgs:
        for ref in _extract_model_refs(cf):
            if ref not in known_models:
                missing.add(f"{cf.name}: {ref}")
    assert not missing, f"Unresolved model refs: {sorted(missing)}"


def test_seven_config_files_present():
    cfgs = _configs()
    if not cfgs:
        pytest.skip("config/promptfoo/ does not exist yet")
    names = {c.stem for c in cfgs}
    expected = {
        "coding_quality",
        "daily_quality",
        "document_quality",
        "media_quality",
        "reasoning_quality",
        "security_quality",
        "strategic_quality",
    }
    assert names == expected, f"missing={expected - names} extra={names - expected}"


def test_no_invalid_assertion_syntax():
    """Guard against the V1 mistakes: 'values:' key, min-length, contains-or-similar."""
    cfgs = _configs()
    if not cfgs:
        pytest.skip("config/promptfoo/ does not exist yet")
    for cf in cfgs:
        text = cf.read_text()
        assert "values:" not in text, f"{cf.name}: 'values:' is not valid (use 'value:')"
        assert "min-length" not in text, f"{cf.name}: min-length is not a promptfoo assertion"
        assert "contains-or-similar" not in text, f"{cf.name}: contains-or-similar does not exist"
