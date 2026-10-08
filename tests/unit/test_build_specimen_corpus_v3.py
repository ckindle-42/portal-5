"""SPECIMEN_CORPUS_V3 adds behavior values from each specimen's own evidence and changes nothing else."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_specimen_corpus_v3 import SPECIMEN_CORPUS_V3, build


def test_v3_adds_values_from_evidence_and_keeps_every_other_field(tmp_path: Path) -> None:
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "s1.json").write_text(
        json.dumps(
            {"telemetry": {"windows:sysmon": ["EventCode=1 Image=C:\\Windows\\certutil.exe"]}}
        )
    )
    view = {"action_sequence": ["event-0:1"], "artifacts": {"observed_fields": ["Image"]}}
    v2 = {
        "schema": "SPECIMEN_CORPUS_V2",
        "snapshot_hash": "abc",
        "specimens": [
            {"specimen_id": "s1", "evidence_ref": "s1.json", "source_lane": "attack_data",
             "engine_view": {"telemetry_view": view}},
            {"specimen_id": "s2", "evidence_ref": "gone.json", "source_lane": "attack_data",
             "engine_view": {"telemetry_view": {}}},
        ],
    }  # fmt: skip
    v3 = build(v2, ev)
    s1 = v3["specimens"][0]["engine_view"]["telemetry_view"]
    assert s1["artifacts"] == {
        "observed_fields": ["Image"],
        "behavior_values": ["image: certutil.exe"],
    }
    assert s1["action_sequence"] == ["event-0:1"]
    assert v2["specimens"][0]["engine_view"]["telemetry_view"]["artifacts"] == {
        "observed_fields": ["Image"]
    }  # V2 untouched
    assert v3["schema"] == SPECIMEN_CORPUS_V3
    assert v3["derived_from"]["specimens_without_evidence"] == ["s2"]
    assert v3["snapshot_hash"] != "abc"
