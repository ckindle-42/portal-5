from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.bully.class_onboarding import (
    run_cross_class_acceptance,
    run_detection_qa,
)
from portal.modules.security.core.bully.cousin_calibration_bench import (
    corpus_parent_reference_record,
)
from portal.modules.security.core.bully.source_adapters import adapt
from portal.modules.security.core.siem.spl_detections import (
    spl_for_source,
    technique_signature_full,
    validated_detection_sourcetypes,
)
from scripts import corpus_ingest
from scripts.build_specimen_corpus import _eligible_catalog


def test_admission_capability_is_derived_from_exact_source_detections():
    expected = {
        "windows:security",
        "linux:auditd",
        "web:access",
        "docker:daemon",
        "windows:sysmon",
        "windows:powershell",
        "windows:system",
        "OktaIM2:log",
    }
    assert expected <= validated_detection_sourcetypes()
    assert validated_detection_sourcetypes() == corpus_ingest.INGESTED_SOURCETYPES
    assert spl_for_source("T1059", "OktaIM2:log") is None
    assert spl_for_source("T1621", "OktaIM2:log")


def test_new_class_signatures_expose_source_discriminator_vocabulary():
    powershell = technique_signature_full("T1059.001")
    assert {item["source"] for item in powershell["spl_variants"]} == {
        "windows:sysmon",
        "windows:powershell",
    }
    assert "Reflection.Assembly" in powershell["distinguishing_features"]["discriminator_tokens"]


def test_new_detection_qa_has_positive_and_quiet_benign_evidence():
    fixtures = {
        ("T1059.001", "windows:sysmon"): (
            "EventCode=1 Image=C:\\Windows\\powershell.exe",
            "EventCode=1 Image=C:\\Windows\\notepad.exe",
        ),
        ("T1059.001", "windows:powershell"): (
            "EventCode=4104 ScriptBlockText=[Reflection.Assembly]::Load($bytes)",
            "EventCode=4104 ScriptBlockText=Get-Date",
        ),
        ("T1543.003", "windows:system"): (
            "EventCode=7045 ImagePath=RemComSvc.exe",
            "EventCode=7045 ImagePath=C:\\Windows\\System32\\spoolsv.exe",
        ),
        ("T1621", "OktaIM2:log"): (
            "user.authentication.auth_via_mfa outcome.result=FAILURE count=4",
            "user.authentication.auth_via_mfa outcome.result=SUCCESS count=1",
        ),
    }
    positive_markers = {
        ("T1059.001", "windows:sysmon"): "powershell.exe",
        ("T1059.001", "windows:powershell"): "Reflection.Assembly",
        ("T1543.003", "windows:system"): "RemComSvc.exe",
        ("T1621", "OktaIM2:log"): "outcome.result=FAILURE",
    }
    for key, (positive, benign) in fixtures.items():
        spl = spl_for_source(*key)
        assert spl and positive_markers[key].lower() in positive.lower()
        assert positive_markers[key].lower() in spl.lower().replace('"', "")
        assert positive_markers[key].lower() not in benign.lower()


def test_detection_qa_requires_live_positive_and_quiet_benign():
    parent = _parent(
        "system-positive",
        "windows:system",
        "T1543.003",
        {"EventCode": 7045, "ImagePath": "RemComSvc.exe"},
    )
    parent["engine_view"]["telemetry_view"]["detector_outcomes"] = {"opaque-detector": "fired"}
    report = run_detection_qa(
        {"specimens": [parent]},
        source_techniques={"windows:system": "T1543.003"},
    )
    assert report["passed"] is True
    assert report["classes"]["windows:system"]["known_positive_live_fires"] == 1


def test_class_filter_builds_one_cohort_without_changing_capability_gate(tmp_path: Path):
    sysmon = tmp_path / "sysmon.log"
    sysmon.write_text("EventCode=1 Image=powershell.exe\n", encoding="utf-8")
    security = tmp_path / "security.log"
    security.write_text("EventCode=4688 NewProcessName=cmd.exe\n", encoding="utf-8")
    catalog = [
        corpus_ingest.ManifestDataset(
            path=sysmon,
            sourcetype="XmlWinEventLog",
            source="XmlWinEventLog:Microsoft-Windows-Sysmon/Operational",
            dataset_epoch=0.0,
            techniques=("T1059.001",),
            mapped_sourcetype="windows:sysmon",
        ),
        corpus_ingest.ManifestDataset(
            path=security,
            sourcetype="XmlWinEventLog",
            source="XmlWinEventLog:Security",
            dataset_epoch=0.0,
            techniques=("T1059",),
            mapped_sourcetype="windows:security",
        ),
    ]
    eligible, admitted = _eligible_catalog(
        catalog, 0, include_sourcetypes=frozenset({"windows:sysmon"})
    )
    assert eligible == admitted == [catalog[0]]


class _MixedSnapshot:
    def __init__(self, records: list[dict]):
        self.records = records

    def knn(self, query: str, k: int, filters=None):
        records = self.records
        if filters:
            records = [
                record
                for record in records
                if all(record.get(key) == value for key, value in filters.items())
            ]
        return [
            (record, 0.0 if query == record["semantic_query"] else 0.2) for record in records[:k]
        ]

    def stats(self):
        return {"row_count": len(self.records)}


def _parent(specimen_id: str, source: str, technique: str, event: dict) -> dict:
    view = adapt([event], {"sourcetype": source, "techniques": [technique]})
    return {
        "specimen_id": specimen_id,
        "source_lane": "attack_data",
        "source_class": source,
        "engine_view": {
            "episode_view": {"episode_id": specimen_id, "target_host": "fixture"},
            "telemetry_view": view,
            "trust_tier": "imported_observed",
        },
        "evidence_ref": f"{specimen_id}.json",
    }


def test_cross_class_x1_through_x5_are_evidence_backed(tmp_path: Path):
    parents = [
        _parent("sysmon", "windows:sysmon", "T1059.001", {"EventCode": 1}),
        _parent("powershell", "windows:powershell", "T1059.001", {"EventCode": 4104}),
        _parent(
            "okta",
            "OktaIM2:log",
            "T1621",
            {"eventType": "user.authentication.auth_via_mfa"},
        ),
    ]
    records = [corpus_parent_reference_record(parent) for parent in parents]
    output = tmp_path / "cross.json"
    report = run_cross_class_acceptance(
        _MixedSnapshot(records), corpus={"specimens": parents}, output_path=output
    )
    assert report["passed"] is True
    assert all(report["checks"][name]["passed"] for name in ("X1", "X2", "X3", "X4", "X5"))
    assert output.exists()
