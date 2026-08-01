"""Combined red-corpus coverage stays provenance- and mode-aware."""

from __future__ import annotations

import json

from portal.modules.security.core import corpus_coverage as coverage


def _valid_capture(tmp_path, scenario: str):
    pcap = tmp_path / f"{scenario}.pcap"
    pcap.write_bytes(b"pcap")
    capture = tmp_path / f"{scenario}_capture.json"
    capture.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": scenario,
                "target_host": "10.10.11.9",
                "episode_id": "ep-valid",
                "telemetry": {
                    "web:access": [
                        "GET /victim.cgi User-Agent: () { :;}",
                        "uid=0(root) gid=0(root) groups=0(root)",
                    ]
                },
                "validity": {"checked": True, "valid": True, "coverage": 1.0},
                "pcap_path": str(pcap),
            }
        )
    )
    return capture


def test_external_techniques_never_substitute_for_live_scenario_proof(tmp_path, monkeypatch):
    capture = _valid_capture(tmp_path, "vuln_shellshock_rce")
    monkeypatch.setattr(
        coverage,
        "list_captures",
        lambda scenario=None: [capture] if scenario == "vuln_shellshock_rce" else [],
    )

    report = coverage.build_coverage_report(
        external_techniques={"T1558.003", "T1003.003"},
        external_validation="live-probed",
    )

    assert report["scenario_coverage"]["live_valid"] == 1
    assert report["scenario_coverage"]["valid_scenarios"] == ["vuln_shellshock_rce"]
    assert report["technique_coverage"]["provenance"]["T1558.003"] == ["public_labeled"]
    assert report["ready_for_detection_design"] is True


def test_declared_external_inventory_cannot_pass_live_validation_gate(tmp_path, monkeypatch):
    capture = _valid_capture(tmp_path, "vuln_shellshock_rce")
    monkeypatch.setattr(
        coverage,
        "list_captures",
        lambda scenario=None: [capture] if scenario == "vuln_shellshock_rce" else [],
    )
    report = coverage.build_coverage_report(external_validation="declared")
    assert report["gates"]["external_corpus_live_probed"] is False
    assert report["ready_for_blue_purple_validation"] is False


def test_empty_external_probe_cannot_pass_readiness_gate(tmp_path, monkeypatch):
    capture = _valid_capture(tmp_path, "vuln_shellshock_rce")
    monkeypatch.setattr(
        coverage,
        "list_captures",
        lambda scenario=None: [capture] if scenario == "vuln_shellshock_rce" else [],
    )
    report = coverage.build_coverage_report(
        external_techniques=set(), external_validation="live-probed"
    )
    assert report["gates"]["external_labeled_techniques_present"] is False
    assert report["ready_for_detection_design"] is False


def test_hollow_newest_capture_does_not_hide_older_valid_capture(tmp_path, monkeypatch):
    valid = _valid_capture(tmp_path, "vuln_shellshock_rce")
    hollow = tmp_path / "vuln_shellshock_rce_newer.json"
    hollow.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": "vuln_shellshock_rce",
                "episode_id": "ep-hollow",
                "telemetry": {"web:access": ["request only"]},
                "validity": {"checked": True, "valid": False, "coverage": 0.0},
            }
        )
    )
    monkeypatch.setattr(
        coverage,
        "list_captures",
        lambda scenario=None: [hollow, valid] if scenario == "vuln_shellshock_rce" else [],
    )
    report = coverage.build_coverage_report(
        external_techniques=set(), external_validation="live-probed"
    )
    status = report["scenario_coverage"]["details"]["vuln_shellshock_rce"]
    assert status["newest_issues"]
    assert status["valid_capture"] == str(valid)


def test_source_contract_keeps_theory_out_of_capture_modes():
    contract = coverage.load_source_contract()
    assert contract["answer_key_visibility"] == "scorer_only"
    assert all(source["data_mode"] != "theory" for source in contract["sources"].values())
    assert contract["gates"]["allow_external_scenario_substitution"] is False


def test_agentic_blue_loader_uses_valid_capture_not_newest_hollow(tmp_path, monkeypatch):
    from portal.modules.security.core import agentic_blue_eval
    from portal.modules.security.core.exec_chain import SCENARIOS

    monkeypatch.setitem(SCENARIOS["vuln_shellshock_rce"], "target_host", "10.10.11.50")

    valid = _valid_capture(tmp_path, "vuln_shellshock_rce")
    valid.rename(tmp_path / "vuln_shellshock_rce_older.json")
    hollow = tmp_path / "vuln_shellshock_rce_newer.json"
    hollow.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": "vuln_shellshock_rce",
                "episode_id": "ep-hollow",
                "telemetry": {"web:access": ["request only"]},
                "validity": {"checked": True, "valid": False},
            }
        )
    )
    # mtime, not filename, determines newest.
    hollow.touch()
    monkeypatch.setattr(agentic_blue_eval, "_CAPTURE_DIR", tmp_path)
    episode = agentic_blue_eval.load_episode("vuln_shellshock_rce")
    assert episode is not None
    assert episode.scenario == "captured_episode"
    assert episode.target_host == "10.10.11.50"
    assert episode.techniques == ["T1190", "T1059"]


def test_report_identifies_catalog_as_lab_exercises(tmp_path, monkeypatch):
    capture = _valid_capture(tmp_path, "vuln_shellshock_rce")
    monkeypatch.setattr(
        coverage,
        "list_captures",
        lambda scenario=None: [capture] if scenario == "vuln_shellshock_rce" else [],
    )
    report = coverage.build_coverage_report(
        external_techniques={"T1190"}, external_validation="live-probed"
    )
    assert report["scenario_coverage"]["data_mode"] == "lab-exercise"


def test_theory_and_unbacked_scenarios_do_not_inflate_lab_denominator(tmp_path, monkeypatch):
    monkeypatch.setattr(coverage, "list_captures", lambda scenario=None: [])
    report = coverage.build_coverage_report(
        external_techniques={"T1190"}, external_validation="live-probed"
    )
    scenarios = report["scenario_coverage"]
    assert scenarios["catalog_total"] == 93
    assert scenarios["total"] == 72
    assert len(scenarios["excluded_from_lab_replay"]) == 21
    assert "cloud_breach" in scenarios["excluded_from_lab_replay"]
    assert "web_graphql_introspect" in scenarios["excluded_from_lab_replay"]
    assert "vuln_confluence_rce" in scenarios["excluded_from_lab_replay"]
    assert "web_to_root" not in scenarios["excluded_from_lab_replay"]
