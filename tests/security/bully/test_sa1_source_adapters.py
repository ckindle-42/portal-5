from __future__ import annotations

from portal.modules.security.core.bully import signatures, source_adapters
from scripts.build_specimen_corpus import _telemetry_view

_ENGINE_DIMENSIONS = (
    "action_sequence",
    "event_graph",
    "parameter_families",
    "context_topology",
    "artifacts",
    "attack_mappings",
    "telemetry_shape",
    "detector_outcomes",
)


def test_endpoint_adapter_preserves_existing_dimension_shape():
    view = source_adapters.adapt(
        [{"EventCode": 4688, "Image": "cmd.exe"}],
        {
            "sourcetype": "windows:security",
            "techniques": ["T1059"],
            "origin": "imported_observed",
            "trust_tier": "imported_observed",
        },
    )
    assert view["action_sequence"][:2] == ["event-0:4688", "field:EventCode"]
    assert view["context_topology"] == {"source_classes": ["windows:security"]}
    assert view["telemetry_shape"]["sourcetypes"] == ["windows:security"]
    assert view["origin"] == "imported_observed"


def test_adapter_refactor_is_result_identical_for_existing_and_mixed_sources():
    telemetry = {
        "linux:auditd": [{"type": "EXECVE", "exe": "/usr/bin/id"}],
        "windows:security": [{"EventCode": 4688, "Image": "cmd.exe"}],
    }
    view = _telemetry_view(telemetry, techniques=("T1059",))
    actions = [
        "event-0:EXECVE",
        "field:type",
        "field:exe",
        "event-1:4688",
        "field:EventCode",
        "field:Image",
    ]
    legacy = {
        "action_sequence": actions,
        "event_graph": {"ordered": actions},
        "parameter_families": {"event_volume_band": 2},
        "context_topology": {"source_classes": ["linux:auditd", "windows:security"]},
        "artifacts": {"observed_fields": ["EventCode", "Image", "exe", "type"]},
        "attack_mappings": [{"technique_id": "T1059"}],
        "telemetry_shape": {
            "sourcetypes": ["linux:auditd", "windows:security"],
            "event_count": 2,
        },
        "detector_outcomes": {},
    }
    assert {key: view[key] for key in _ENGINE_DIMENSIONS} == legacy


def test_identity_adapter_uses_auth_semantics_and_cross_class_family():
    view = source_adapters.adapt(
        [
            {
                "eventType": "user.authentication.auth_via_mfa",
                "actor": {"alternateId": "analyst@example.com"},
                "client": {"ipAddress": "192.0.2.10"},
                "outcome": {"result": "FAILURE"},
            }
        ],
        {"sourcetype": "OktaIM2:log", "techniques": ["T1621"]},
    )
    assert view["action_sequence"][0] == ("identity-0:user.authentication.auth_via_mfa")
    assert view["context_topology"]["users"] == ["analyst@example.com"]
    assert view["context_topology"]["family"] == "attack:T1621"


def test_fallback_leaves_missing_dimensions_absent_and_lowers_completeness():
    sparse = source_adapters.adapt(
        ["vendor advisory IOC 203.0.113.4"],
        {"sourcetype": "threat-intel:advisory", "techniques": ["T1190"]},
    )
    full = source_adapters.adapt(
        [{"EventCode": 1, "Image": "powershell.exe"}],
        {"sourcetype": "windows:sysmon", "techniques": ["T1059.001"]},
    )
    sparse_signature = signatures.build_signature({"episode_id": "sparse"}, sparse)
    full_signature = signatures.build_signature({"episode_id": "full"}, full)
    assert "action_sequence" not in sparse
    assert sparse_signature.completeness < full_signature.completeness
