from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "config" / "lab_purple_sweep.yaml"
CANONICAL_SOURCETYPES = {
    "access_combined",
    "apache:error",
    "aws:cloudtrail",
    "kube:apiserver:audit",
    "nginx:plus:access",
    "redis:log",
    "solr:log",
    "syslog",
    "tomcat:access:log",
}
RED_STAGES = ["recon", "exploit_probe", "post_probe_indicator"]
MUTATING_REQUEST = re.compile(r"^(?:PUT|PATCH|POST|DELETE)\b", re.IGNORECASE)


def _assert_identity_and_source(target: dict) -> None:
    assert isinstance(target.get("id"), str) and target["id"]
    assert isinstance(target.get("source"), str) and target["source"]
    assert isinstance(target.get("technology_family"), str)
    assert "cve" in target
    if target["cve"] is not None:
        assert re.fullmatch(r"CVE-\d{4}-\d{4,}", target["cve"])
    assert target.get("vulhub_path") or target.get("repo_url")
    if target["source"] == "vulhub":
        assert target.get("vulhub_path")
    else:
        assert target.get("repo_url", "").startswith("https://")


def _assert_techniques_and_sourcetypes(target: dict) -> None:
    techniques = target.get("mitre_techniques")
    assert isinstance(techniques, list) and techniques
    assert all(re.fullmatch(r"T\d{4}(?:\.\d{3})?", item) for item in techniques)
    sourcetypes = target.get("canonical_sourcetypes")
    assert isinstance(sourcetypes, list) and sourcetypes
    assert set(sourcetypes) <= CANONICAL_SOURCETYPES
    assert not any(
        any(
            marker in sourcetype.lower()
            for marker in ("hb:", "attack", "label", "scenario", "purple")
        )
        for sourcetype in sourcetypes
    )


def _assert_benign_profile(target: dict) -> None:
    benign = target.get("benign_profile")
    assert isinstance(benign, dict)
    assert isinstance(benign.get("user_agents"), list) and benign["user_agents"]
    requests = benign.get("requests")
    assert isinstance(requests, list) and len(requests) >= 3
    protocol = benign.get("protocol", "http")
    if protocol == "http":
        assert all(item.get("method") in {"GET", "HEAD"} for item in requests)
        assert all(item.get("path", "").startswith("/") for item in requests)
    elif protocol == "redis":
        assert all(item.get("operation") in {"PING", "INFO server", "DBSIZE"} for item in requests)
    elif protocol == "mysql":
        assert all(
            item.get("operation") in {"SELECT 1", "SHOW DATABASES", "SELECT VERSION()"}
            for item in requests
        )
    elif protocol == "aws_api":
        assert all(item.get("method") == "AWS_READ" for item in requests)
    else:
        raise AssertionError(f"unsupported benign profile protocol: {protocol}")


def _assert_safe_red_sequence(target: dict) -> None:
    sequence = target.get("red_sequence")
    assert isinstance(sequence, list) and len(sequence) == len(RED_STAGES)
    assert [item.get("stage") for item in sequence] == RED_STAGES
    assert all(item.get("effect") == "read_only" for item in sequence)
    assert all(isinstance(item.get("request"), str) and item["request"] for item in sequence)
    assert not any(MUTATING_REQUEST.match(item["request"]) for item in sequence)


def _assert_target_schema(target: dict) -> None:
    _assert_identity_and_source(target)
    _assert_techniques_and_sourcetypes(target)
    _assert_benign_profile(target)
    _assert_safe_red_sequence(target)
    index_name = target["index_name"]
    assert index_name.startswith("hb_lab_")
    assert "botsv2" not in index_name.lower()


def test_lab_purple_sweep_catalog_schema_and_coverage() -> None:
    catalog = yaml.safe_load(CATALOG.read_text())
    assert isinstance(catalog, dict)
    assert catalog.get("schema_version") == 1
    targets = catalog.get("targets")
    assert isinstance(targets, list)
    assert len(targets) >= 20
    target_ids = [target.get("id") for target in targets]
    index_names = [target.get("index_name") for target in targets]
    families = {target.get("technology_family") for target in targets}
    assert len(target_ids) == len(set(target_ids))
    assert len(index_names) == len(set(index_names))
    assert len(families) >= 5
    for target in targets:
        _assert_target_schema(target)
