"""Provenance-aware coverage gate for red data used by blue/purple validation.

Live Portal captures prove scenarios.  Public labeled corpora broaden technique
coverage.  The two are deliberately combined only at the technique layer and
remain separate in every report so external data cannot hide a broken lab path.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .corpus_replay_bench import CURATED_TECHNIQUES
from .exec_chain import SCENARIOS
from .siem.capture_store import (
    CAPTURE_DIR,
    capture_ground_truth_status,
    capture_replay_issues,
    capture_replay_warnings,
    list_captures,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = _PROJECT_ROOT / "config" / "security_corpus.yaml"


def load_source_contract(path: Path = CONFIG_PATH) -> dict[str, Any]:
    contract = yaml.safe_load(path.read_text())
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("security corpus contract must use schema_version 1")
    if contract.get("answer_key_visibility") != "scorer_only":
        raise ValueError("security corpus answer keys must be scorer_only")
    return contract


def _load_capture(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _latest_live_status(scenario: str, *, require_pcap: bool) -> dict[str, Any]:
    """Return newest capture status plus the newest independently valid artifact."""
    captures = list_captures(scenario)
    newest_path = str(captures[0]) if captures else None
    newest_issues: list[str] = ["MISSING_CAPTURE"]
    valid_path: str | None = None
    techniques: list[str] = []
    warnings: list[str] = []
    for index, path in enumerate(captures):
        data = _load_capture(path)
        issues = (
            ["MALFORMED_CAPTURE"]
            if data is None
            else capture_replay_issues(data, require_pcap=require_pcap)
        )
        if index == 0:
            newest_issues = issues
        if not issues and data is not None:
            valid_path = str(path)
            techniques = list(capture_ground_truth_status(data).get("found") or [])
            warnings = capture_replay_warnings(data)
            break
    return {
        "newest_capture": newest_path,
        "newest_issues": newest_issues,
        "valid_capture": valid_path,
        "techniques": techniques,
        "warnings": warnings,
    }


def build_coverage_report(
    *,
    external_techniques: set[str] | None = None,
    external_validation: str = "declared",
    contract_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    """Build the combined report without conflating scenario and technique proof.

    ``external_validation`` is ``live-probed`` only when the caller queried the
    lab SIEM in this run.  The committed curated set remains useful offline, but
    it cannot satisfy the readiness gate after a lab reset.
    """
    contract = load_source_contract(contract_path)
    source_cfg = contract["sources"]
    require_pcap = bool(source_cfg["portal_live"].get("require_pcap"))
    excluded = dict(contract.get("scenario_scope", {}).get("excluded_from_lab_replay") or {})
    unknown_exclusions = sorted(set(excluded) - set(SCENARIOS))
    if unknown_exclusions:
        raise ValueError(f"unknown excluded security scenarios: {unknown_exclusions}")
    scoped_scenarios = {
        name: scenario for name, scenario in SCENARIOS.items() if name not in excluded
    }

    scenario_status: dict[str, dict[str, Any]] = {}
    live_techniques: set[str] = set()
    for name in sorted(scoped_scenarios):
        status = _latest_live_status(name, require_pcap=require_pcap)
        scenario_status[name] = status
        if status["valid_capture"]:
            live_techniques.update(status["techniques"])

    declared_external = set(CURATED_TECHNIQUES)
    external = set(external_techniques) if external_techniques is not None else declared_external
    target_techniques = {
        technique
        for scenario in scoped_scenarios.values()
        for technique in scenario.get("detect_ground_truth") or []
    }
    combined = live_techniques | external

    provenance: dict[str, list[str]] = defaultdict(list)
    for technique in sorted(live_techniques):
        provenance[technique].append("portal_live")
    for technique in sorted(external):
        provenance[technique].append("public_labeled")

    valid_scenarios = [
        name for name, status in scenario_status.items() if status["valid_capture"] is not None
    ]
    gates = {
        "answer_keys_hidden": contract["answer_key_visibility"] == "scorer_only",
        "source_stratified": bool(contract["gates"]["require_source_stratified_results"]),
        "live_scenario_proof_present": bool(valid_scenarios),
        "external_corpus_live_probed": external_validation == "live-probed",
        "external_labeled_techniques_present": bool(external),
        "external_never_substitutes_for_scenario_proof": not bool(
            contract["gates"]["allow_external_scenario_substitution"]
        ),
    }
    ready = all(gates.values())

    return {
        "schema_version": 1,
        "answer_key_visibility": contract["answer_key_visibility"],
        "external_validation": external_validation,
        "scenario_coverage": {
            "data_mode": "lab-exercise",
            "catalog_total": len(SCENARIOS),
            "total": len(scoped_scenarios),
            "excluded_from_lab_replay": excluded,
            "live_valid": len(valid_scenarios),
            "live_invalid_or_missing": len(scoped_scenarios) - len(valid_scenarios),
            "valid_scenarios": valid_scenarios,
            "details": scenario_status,
            "note": "External data is never counted as scenario-level live proof.",
        },
        "technique_coverage": {
            "target": len(target_techniques),
            "live": len(live_techniques & target_techniques),
            "external": len(external & target_techniques),
            "combined": len(combined & target_techniques),
            "covered": sorted(combined & target_techniques),
            "gaps": sorted(target_techniques - combined),
            "extra_external": sorted(external - target_techniques),
            "provenance": dict(sorted(provenance.items())),
        },
        "gates": gates,
        "ready_for_blue_purple_validation": ready,
        "ready_for_detection_design": ready,
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


__all__ = [
    "CAPTURE_DIR",
    "CONFIG_PATH",
    "build_coverage_report",
    "load_source_contract",
    "write_report",
]
