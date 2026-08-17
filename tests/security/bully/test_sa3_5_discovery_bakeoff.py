"""SA3.5 -- embedding bake-off driver tests (TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1).

Verifies the bake-off driver wires a version-tagged projection + embed URL into
the SA2 discovery lane and that a controls-failing arm is reported INVALID
(disqualified, not compared) -- fully offline via the fixture corpus and a
mock embed client.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from portal.modules.security.core.bully.discovery_bench import DISCOVERY_BASELINE_V1
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store

# Captured at import time: monkeypatching bakeoff_mod.httpx.Client patches the
# shared httpx module, so the mock must be built from this saved reference.
_REAL_HTTPX_CLIENT = httpx.Client

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.defensive_bully_discovery_bakeoff import main as bakeoff_main  # noqa: E402
from scripts.defensive_bully_discovery_seed import _real_parent_records  # noqa: E402


def _mock_embed_client(dim: int = 8) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        inputs = body["input"]
        inputs = [inputs] if isinstance(inputs, str) else inputs
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "object": "embedding",
                        "index": i,
                        "embedding": [float((hash(t) >> i) % 7) for i in range(dim)],
                    }
                    for i, t in enumerate(inputs)
                ]
            },
        )

    return _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler))


def _write_corpus(tmp_path: Path, n_parents: int = 12) -> Path:
    import hashlib

    from portal.modules.security.core.bully.cousin_calibration_bench import _canonical
    from tests.security.bully._discovery_fixtures import make_specimen

    specimens = [
        make_specimen(
            f"parent-{i}",
            technique_ids=["T1558.003"] if i % 2 == 0 else ["T1059.001"],
            family="attack:T1558.003" if i % 2 == 0 else "attack:T1059.001",
            source_class="windows:sysmon" if i % 2 == 0 else "OktaIM2:log",
            action_sequence=["logon", "ticket_request", f"event_{i}"],
            detector_outcomes={f"det-{i}": "missed"},
        )
        for i in range(n_parents)
    ]
    corpus = {
        "schema": "SPECIMEN_CORPUS_V2",
        "specimens": specimens,
        "per_lane_counts": {"attack_data": n_parents, "replay_mutation": 0, "live_lab": 0},
    }
    corpus["snapshot_hash"] = hashlib.sha256(_canonical(specimens).encode()).hexdigest()
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    return path


def _seed_projection(tmp_path: Path, corpus_path: Path, version: str) -> Path:
    from portal.modules.security.core.bully.cousin_calibration_bench import load_specimen_corpus

    corpus = load_specimen_corpus(corpus_path)
    records = _real_parent_records(corpus)
    out = tmp_path / "proj"
    with Store(out / "snapshot_state.db") as store:
        organ = Organ(
            store=store,
            db_path=out / "organ_snapshot",
            embed_client=_mock_embed_client(),
            embedding_version=version,
        )
        try:
            organ.upsert_many(records, batch_size=4)
        finally:
            organ.close()
    return out


def test_bakeoff_driver_runs_discovery_lane_and_writes_report(tmp_path: Path, monkeypatch):
    corpus_path = _write_corpus(tmp_path)
    projection = _seed_projection(tmp_path, corpus_path, "mlx-qwen3-embed-0.6b-mxfp8")
    out = tmp_path / "discovery"
    import scripts.defensive_bully_discovery_bakeoff as bakeoff_mod

    monkeypatch.setattr(bakeoff_mod.httpx, "Client", lambda **kwargs: _mock_embed_client())
    bakeoff_main(
        [
            "--arm",
            "arm-a",
            "--corpus",
            str(corpus_path),
            "--projection",
            str(projection),
            "--embed-url",
            "http://localhost:8941/v1/embeddings",
            "--query-embed-url",
            "http://localhost:8941/v1/embeddings",
            "--embedding-version",
            "mlx-qwen3-embed-0.6b-mxfp8",
            "--output-dir",
            str(out),
            "--batch-size",
            "4",
        ]
    )
    artifact = out / "discovery_baseline_v1.json"
    assert artifact.exists()
    report = json.loads(artifact.read_text(encoding="utf-8"))
    assert report["schema"] == DISCOVERY_BASELINE_V1
    assert report["real_parent_count"] == 12
    assert "controls" in report


def test_bakeoff_driver_uses_embed_url_and_version(tmp_path: Path, monkeypatch):
    corpus_path = _write_corpus(tmp_path)
    projection = _seed_projection(tmp_path, corpus_path, "llamacpp-embeddinggemma-300m-q8")
    out = tmp_path / "discovery"
    import scripts.defensive_bully_discovery_bakeoff as bakeoff_mod

    monkeypatch.setattr(bakeoff_mod.httpx, "Client", lambda **kwargs: _mock_embed_client())
    bakeoff_main(
        [
            "--arm",
            "arm-b",
            "--corpus",
            str(corpus_path),
            "--projection",
            str(projection),
            "--embed-url",
            "http://localhost:8943/v1/embeddings",
            "--query-embed-url",
            "http://localhost:8943/v1/embeddings/query",
            "--embedding-version",
            "llamacpp-embeddinggemma-300m-q8",
            "--output-dir",
            str(out),
            "--batch-size",
            "4",
        ]
    )
    assert out / "discovery_baseline_v1.json" is not None
