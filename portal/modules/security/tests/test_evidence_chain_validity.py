"""Validity invariants for the red→evidence→blue chain."""

from __future__ import annotations

import json
from unittest.mock import patch

from portal.modules.security.core._config import BenchConfig


def test_replay_never_ships_counterfactual_transcript(tmp_path, monkeypatch):
    from portal.modules.security.core.siem import capture_store

    monkeypatch.setattr(capture_store, "CAPTURE_DIR", tmp_path)
    path = capture_store.save_capture(
        scenario="evidence-plane-test",
        target_host="10.0.0.10",
        kind="web",
        since_epoch=1000.0,
        telemetry={"web:access": ["GET /observed HTTP/1.1 200"]},
        telemetry_origins={"web:access": "observed_target_log"},
        counterfactual_telemetry={"transcript:command": ['{"command":"curl /answer-key-payload"}']},
        episode_id="ep-plane-test",
    )

    shipped: list[tuple[str, list[str]]] = []

    def _ship(events, *, sourcetype, **kwargs):
        shipped.append((sourcetype, events))
        return {"ok": True}

    with (
        patch("portal.modules.security.core.siem.hec_ship.ship_batch", _ship),
        patch(
            "portal.modules.security.core.siem.index_wait.wait_indexed",
            return_value=True,
        ),
    ):
        result = capture_store.replay_capture(path)

    assert result["ok"] is True
    assert shipped == [("web:access", ["GET /observed HTTP/1.1 200"])]


def test_legacy_unscoped_capture_is_not_replayable(tmp_path):
    from portal.modules.security.core.siem.capture_store import replay_capture

    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "scenario": "legacy",
                "target_host": "10.0.0.10",
                "telemetry": {"ids:alert": ["perfect reconstructed signal"]},
            }
        )
    )
    result = replay_capture(path)
    assert result["ok"] is False
    assert result["error"] == "LEGACY_CAPTURE_UNSCOPED"


def test_hec_indexes_origin_and_episode_fields():
    from portal.modules.security.core.siem.hec_ship import ship

    result = ship(
        "GET / HTTP/1.1",
        sourcetype="web:access",
        host="10.0.0.10",
        dry_run=True,
        evidence_origin="observed_target_log",
        episode_id="ep-hec-test",
    )
    assert result["envelope"]["fields"] == {
        "evidence_origin": "observed_target_log",
        "episode_id": "ep-hec-test",
    }


def test_episode_query_recovers_origin_from_hec_source(monkeypatch):
    from portal.modules.security.core.siem.spl_backend import SplunkBackend

    backend = SplunkBackend()
    monkeypatch.setattr(
        backend,
        "_run_search",
        lambda *args: [
            {
                "raw": "packet",
                "fields": {
                    "source": "portal5:observed_packet",
                    "episode_id": "ep-source-test",
                },
            }
        ],
    )
    result = backend.query_episode({}, episode_id="ep-source-test")
    assert result["origins"] == ["observed_packet"]


def test_freeform_query_cannot_escape_episode_scope(monkeypatch):
    from portal.modules.security.core.siem.spl_backend import SplunkBackend

    backend = SplunkBackend()
    called = False

    def _search(*args):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(backend, "_run_search", _search)
    result = backend.query_freeform(
        'sourcetype="network:packet" | append [search index=*]',
        {},
        episode_id="ep-scope-test",
    )
    assert result["rows"] == []
    assert "rejected" in result["error"]
    assert called is False


def test_bad_blue_query_is_a_grounded_miss_not_na(monkeypatch):
    from portal.modules.security.core import blue

    monkeypatch.setattr(
        blue,
        "_run_unknown_defense",
        lambda *args: {
            "match_grade": "NONE",
            "matched_technique": "",
            "similarity_detail": "",
            "anomaly_flagged": False,
            "anomaly_score": 0.0,
            "anomaly_status": "no-baseline",
            "investigation": None,
        },
    )
    result = blue._score_purple(
        {
            "model": "red",
            "mode": "lab-exec",
            "lab_success": True,
            "order_accuracy": 1.0,
            "episode_id": "ep-grounded-miss",
        },
        {
            "model": "blue",
            "mode": "discovery",
            "score": {"detected": [], "f1": 0.0},
            "containments": [],
            "telemetry_origins": {},
            "episode_inventory_origins": ["observed_packet"],
            "episode_id": "ep-grounded-miss",
        },
        {
            "name": "grounded-miss",
            "detect_ground_truth": ["T1190"],
            "persistence_technique": "",
            "target_host": "10.0.0.10",
        },
    )
    assert result["coverage_grounded"] is True
    assert result["detection_coverage"] == 0.0
    assert result["capability_verdict"] == "FAILED"


def test_each_red_model_gets_an_isolated_blue_episode(monkeypatch):
    from portal.modules.security.core import blue, chain

    seen_blue: list[tuple[str, str]] = []

    monkeypatch.setattr(
        chain,
        "_run_chain_test",
        lambda model, cfg, **kwargs: {
            "model": model,
            "mode": "theory",
            "lab_success": None,
            "order_accuracy": 0.5,
            "tools_called_args": [],
        },
    )

    def _blue(model, scenario, **kwargs):
        seen_blue.append((model, kwargs["episode_id"]))
        return {
            "model": model,
            "reported": [],
            "containments": [],
            "telemetry_source": {},
            "telemetry_origins": {},
            "telemetry_raw": {},
            "episode_id": kwargs["episode_id"],
            "synthetic_fallback": False,
            "score": {"detected": [], "f1": 0.0},
            "error": None,
        }

    monkeypatch.setattr(blue, "_run_blue_chain_test", _blue)
    monkeypatch.setattr(
        blue,
        "_run_unknown_defense",
        lambda *args: {
            "match_grade": "NONE",
            "matched_technique": "",
            "similarity_detail": "",
            "anomaly_flagged": False,
            "anomaly_score": 0.0,
            "anomaly_status": "no-baseline",
            "investigation": None,
        },
    )

    scenario = {
        "name": "isolation-test",
        "detect_ground_truth": ["T1190"],
        "persistence_technique": "",
        "target_host": "10.0.0.10",
    }
    results = blue.run_purple_tests(
        ["red-a", "red-b"],
        ["blue-a", "blue-b"],
        scenario,
        BenchConfig(),
    )

    assert len(results) == 4
    red_a_ids = {r["episode"]["episode_id"] for r in results if r["red_model"] == "red-a"}
    red_b_ids = {r["episode"]["episode_id"] for r in results if r["red_model"] == "red-b"}
    assert len(red_a_ids) == len(red_b_ids) == 1
    assert red_a_ids.isdisjoint(red_b_ids)
    assert {episode_id for _, episode_id in seen_blue} == red_a_ids | red_b_ids
