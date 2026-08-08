import json
from pathlib import Path

import pytest

from portal.modules.security.core.capture_recipes import (
    CAPTURE_RECIPES,
    render_host_command,
    render_postcondition_command,
    render_recipe_command,
)
from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.siem.capture_enrichment import validate_capture_signals
from portal.platform.data_loader import load_data

_REPO_ROOT = Path(__file__).resolve().parents[4]


SAMPLE_EVIDENCE = load_data("tests/data", "security_test_capture_recipes_sample_evidence")

REQUEST_ONLY_EVIDENCE = load_data(
    "tests/data", "security_test_capture_recipes_request_only_evidence"
)


@pytest.mark.parametrize("scenario", sorted(CAPTURE_RECIPES))
def test_recipe_has_positive_and_request_only_negative_control(scenario):
    positive = validate_capture_signals(scenario, {"network:packet": [SAMPLE_EVIDENCE[scenario]]})
    assert positive["valid"], positive
    assert not positive["unchecked"], positive

    negative = validate_capture_signals(
        scenario, {"network:packet": [REQUEST_ONLY_EVIDENCE[scenario]]}
    )
    assert not negative["valid"], negative


def test_recipes_resolve_runtime_placeholders_and_use_image_contract_tools():
    contract_path = Path(__file__).resolve().parents[4] / "config" / "attack_image_contract.json"
    tools = set(json.loads(contract_path.read_text())["tools"])
    assert {"curl", "date", "grep", "php", "python3", "redis-cli", "sleep"}.issubset(tools)
    for name, recipe in CAPTURE_RECIPES.items():
        assert name in SCENARIOS
        rendered = render_recipe_command(recipe, host="10.10.11.50", port=12345)
        assert "$TARGET_HOST" not in rendered
        assert "$TARGET_PORT" not in rendered
        postcondition = render_postcondition_command(recipe, port=12345, host="10.10.11.50")
        assert "$TARGET_PORT" not in postcondition
        assert "$TARGET_HOST" not in postcondition
        for host_command in (recipe.host_setup_command, recipe.host_cleanup_command):
            rendered_host = render_host_command(host_command, host="10.10.11.50", port=12345)
            assert "$TARGET_HOST" not in rendered_host
            assert "$TARGET_PORT" not in rendered_host


def test_corrected_rce_ground_truth_is_unique_and_matches_observed_behavior():
    assert SCENARIOS["vuln_django_sqli"]["detect_ground_truth"] == ["T1190"]
    assert SCENARIOS["vuln_tomcat_deploy"]["detect_ground_truth"] == [
        "T1190",
        "T1505.003",
        "T1059.004",
    ]
    for name in ("vuln_drupal_rce", "vuln_solr_rce", "vuln_elasticsearch_rce", "vuln_thinkphp_rce"):
        assert "T1059" in SCENARIOS[name]["detect_ground_truth"]
    assert SCENARIOS["vuln_spring_actuator"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_gitlab_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_dubbo_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_shiro_deserial"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_jackson_deserial"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_activemq_deserial"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_laravel_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_wordpress_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
