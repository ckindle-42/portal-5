from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.bully.coverage import (
    coverage_answer,
    coverage_records,
    register_coverage_source,
)
from portal.modules.security.core.bully.data_plane import DataPlane


def test_real_detection_library_is_queryable_and_missing_technique_is_a_blind_spot():
    path = Path("portal/modules/security/core/siem/spl_detections.yaml")
    records = coverage_records(path)
    plane = DataPlane()
    profile = register_coverage_source(plane, path=path)

    assert records
    assert profile.source_id == "detection-coverage"
    assert profile.record_count == len(records)
    assert coverage_answer(plane, technique_id="T1059")["covered"] is True
    missing = coverage_answer(plane, technique_id="T9999")
    assert missing["covered"] is False
    assert "blind spot" in missing["finding"]


def test_coverage_can_be_scoped_to_a_sourcetype():
    path = Path("portal/modules/security/core/siem/spl_detections.yaml")
    plane = DataPlane()
    register_coverage_source(plane, path=path)
    covered = coverage_answer(plane, technique_id="T1059", source="linux:auditd")
    absent = coverage_answer(plane, technique_id="T1059", source="not-a-source")
    assert covered["covered"] is True
    assert absent["covered"] is False
