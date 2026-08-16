"""P7.3 scaled corpus and real response-axis contracts."""

from __future__ import annotations

import json
from pathlib import Path

from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger
from scripts.build_specimen_corpus import SPECIMEN_CORPUS_V2, build_corpus_v2


def _write_attack_data_fixture(root: Path) -> None:
    admitted = root / "datasets" / "attack_techniques" / "T1558.003" / "fixture"
    admitted.mkdir(parents=True)
    (admitted / "windows.log").write_text(
        "EventCode=4769 TicketEncryptionType=0x17 Account=svc\n", encoding="utf-8"
    )
    (admitted / "data.yml").write_text(
        """date: '2026-01-01'
mitre_technique: [T1558.003]
datasets:
  - path: /datasets/attack_techniques/T1558.003/fixture/windows.log
    sourcetype: XmlWinEventLog
    source: XmlWinEventLog:Security
""",
        encoding="utf-8",
    )


def _write_live_fixture(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": "external-live-cousin",
                "target_host": "authorized-lab",
                "episode_id": "specimen-live-v2",
                "specimen_parent_id": "specimen-parent-live-v2",
                "telemetry": {"web:access": ["GET /first HTTP/1.1 200"]},
                "validity": {"checked": True, "valid": True, "coverage": 1.0},
                "mutation_operators": [
                    {
                        "operator": "VARY_PARAMETER",
                        "params": {"placeholder": "x", "value": "y"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class _RealQueryFixture:
    def __init__(self) -> None:
        self.episodes: list[str] = []

    def query_episode(self, window, *, episode_id, host=None, limit=500):
        self.episodes.append(episode_id)
        return {
            "rows": [{"fields": {}, "raw": "TicketEncryptionType=0x17"}],
            "telemetry": "TicketEncryptionType=0x17",
            "source": "observed",
            "backend": "fixture-siem",
            "error": None,
            "detector_outcomes": {"production-kerberoast-rule": "fired"},
        }

    def query_freeform(self, spl, window, *, episode_id, host=None):
        return {
            "rows": [{"fields": {}, "raw": "TicketEncryptionType=0x17"}],
            "telemetry": "TicketEncryptionType=0x17",
            "source": "observed",
            "backend": "fixture-siem",
            "error": None,
        }


def test_v2_populates_real_opaque_outcomes_and_preserves_truth_wall(tmp_path):
    attack_data = tmp_path / "attack_data"
    _write_attack_data_fixture(attack_data)
    live = tmp_path / "live.json"
    _write_live_fixture(live)
    backend = _RealQueryFixture()
    corpus = build_corpus_v2(
        attack_data_root=attack_data,
        output_dir=tmp_path / "corpus",
        ledger_root=tmp_path / "ledger",
        live_lab_captures=(live,),
        ship=False,
        detector_backend=backend,
    )

    assert corpus["schema"] == SPECIMEN_CORPUS_V2
    assert corpus["execution_mode"] == "live_indexed"
    assert len(backend.episodes) == len(corpus["specimens"])
    assert corpus["response_observation_counts"]["fired"] == len(corpus["specimens"])
    for specimen in corpus["specimens"]:
        assert specimen["execution_mode"] == "live_indexed"
        view = specimen["engine_view"]["telemetry_view"]
        assert view["detector_outcomes"]
        assert set(view["detector_outcomes"].values()) <= {"fired", "partial", "missed"}
        assert all(key.startswith("detector-") for key in view["detector_outcomes"])
        assert view["attack_mappings"] == []

    engine_payload = json.dumps(
        [specimen["engine_view"] for specimen in corpus["specimens"]], sort_keys=True
    )
    assert "T1558.003" not in engine_payload
    assert "specimen_parent_id" not in engine_payload
    assert SpecimenLedger(tmp_path / "ledger").records()


class _EmptyDetectionFixture:
    def query_episode(self, window, *, episode_id, host=None, limit=500):
        return {
            "rows": [{"fields": {}, "raw": "EventCode=1 Image=benign.exe"}],
            "telemetry": "EventCode=1 Image=benign.exe",
            "source": "observed",
            "backend": "fixture-siem",
            "error": None,
        }

    def query_freeform(self, spl, window, *, episode_id, host=None):
        return {
            "rows": [],
            "telemetry": "",
            "source": "empty",
            "backend": "fixture-siem",
            "error": None,
        }


def test_real_empty_detection_result_is_an_honest_miss(tmp_path):
    attack_data = tmp_path / "attack_data"
    _write_attack_data_fixture(attack_data)
    corpus = build_corpus_v2(
        attack_data_root=attack_data,
        output_dir=tmp_path / "corpus",
        ledger_root=tmp_path / "ledger",
        ship=False,
        detector_backend=_EmptyDetectionFixture(),
    )
    assert corpus["response_observation_counts"] == {
        "fired": 0,
        "partial": 0,
        "missed": len(corpus["specimens"]),
        "indeterminate": 0,
    }
    assert all(
        set(specimen["engine_view"]["telemetry_view"]["detector_outcomes"].values()) == {"missed"}
        for specimen in corpus["specimens"]
    )
