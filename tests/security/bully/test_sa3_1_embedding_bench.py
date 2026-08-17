"""SA3.1 -- embedding-backend throughput harness (TASK_BULLY_SA3_EMBEDDING_BAKEOFF_V1).

Backend-agnostic benchmark for whatever OpenAI-compatible /v1/embeddings
service is listening on :8917. Tests here use an httpx MockTransport double
so the harness logic is verified fully offline; the live runs are recorded by
the operator (or the bake-off driver) against the real servers.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from portal.modules.security.core.bully import embedding_bench
from portal.modules.security.core.bully.embedding_bench import (
    BackendReport,
    BatchMeasurement,
    fixed_sample,
    measure_backend,
    measure_cold_start,
    real_corpus_embed_texts,
)


def _fake_client(dim: int = 4) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        inputs = payload["input"]
        inputs = [inputs] if isinstance(inputs, str) else inputs
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": i, "embedding": [float(i + 1)] * dim}
                    for i in range(len(inputs))
                ],
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fixed_sample_is_deterministic_and_length_sorted():
    texts = ["b" * 50, "a" * 10, "c" * 5, "d" * 200, "e" * 1]
    sample = fixed_sample(texts, limit=3)
    assert sample == ["e" * 1, "c" * 5, "a" * 10]


def test_measure_backend_reports_per_batch_stats():
    client = _fake_client()
    texts = [f"behavior token set {i}" for i in range(32)]
    report = measure_backend(
        client,
        embed_url="http://localhost:8917/v1/embeddings",
        texts=texts,
        batch_sizes=(8,),
        repeats=2,
        model_label="test-backend",
    )
    assert isinstance(report, BackendReport)
    assert report.items_sampled == 32
    assert len(report.batches) == 1
    batch = report.batches[0]
    assert isinstance(batch, BatchMeasurement)
    assert batch.batch_size == 8
    assert batch.items == 64
    assert batch.batches == 8
    assert batch.items_per_sec is not None and batch.items_per_sec > 0
    assert batch.p50_ms is not None and batch.p50_ms >= 0
    assert batch.p95_ms is not None
    assert report.to_dict()["embed_url"] == "http://localhost:8917/v1/embeddings"


def test_measure_backend_handles_all_default_batch_sizes():
    client = _fake_client()
    texts = [f"t{i}" for i in range(32)]
    report = measure_backend(client, embed_url="http://x/v1/embeddings", texts=texts, repeats=1)
    assert report.batch_sizes == (8, 32, 64, 128)
    assert len(report.batches) == 4


def test_measure_cold_start_waits_for_health_then_times_first_embed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [1.0, 2.0, 3.0, 4.0]}],
                "model": "test",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cold = measure_cold_start(
        client,
        health_url="http://localhost:8917/health",
        embed_url="http://localhost:8917/v1/embeddings",
    )
    assert cold >= 0
    assert isinstance(cold, float)


def test_report_json_round_trip(tmp_path: Path):
    client = _fake_client()
    report = measure_backend(
        client,
        embed_url="http://localhost:8917/v1/embeddings",
        texts=["a", "b", "c"],
        batch_sizes=(8,),
        repeats=1,
        model_label="test",
        cold_start_s=1.5,
        resident_memory_mb=2048.0,
    )
    out = tmp_path / "report.json"
    embedding_bench.write_report(report, out)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["items_sampled"] == 3
    assert loaded["cold_start_s"] == 1.5
    assert loaded["resident_memory_mb"] == 2048.0


def _write_corpus(tmp_path: Path, corpus: dict) -> Path:
    import hashlib

    from portal.modules.security.core.bully.cousin_calibration_bench import _canonical

    corpus = dict(corpus)
    corpus["snapshot_hash"] = hashlib.sha256(_canonical(corpus["specimens"]).encode()).hexdigest()
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    return path


def test_real_corpus_embed_texts_uses_canonical_record_text(tmp_path: Path):
    import portal.modules.security.core.bully.organ as organ_mod
    from portal.modules.security.core.bully.cousin_calibration_bench import (
        corpus_parent_reference_record,
    )
    from tests.security.bully._discovery_fixtures import build_corpus

    corpus = build_corpus()
    path = _write_corpus(tmp_path, corpus)

    texts = real_corpus_embed_texts(path)
    expected = {
        organ_mod._canonical_record_text(corpus_parent_reference_record(s))
        for s in corpus["specimens"]
        if s["source_lane"] == "attack_data"
    }
    assert set(texts) == expected
    assert texts == sorted(dict.fromkeys(texts), key=len)


def test_real_corpus_embed_texts_excludes_forge_and_live_lab(tmp_path: Path):
    from tests.security.bully._discovery_fixtures import build_corpus

    corpus = build_corpus()
    corpus["specimens"].append(
        {
            "specimen_id": "forge-child",
            "source_lane": "replay_mutation",
            "source_class": "windows:sysmon",
            "engine_view": corpus["specimens"][0]["engine_view"],
        }
    )
    corpus["specimens"].append(
        {
            "specimen_id": "live-lab-row",
            "source_lane": "live_lab",
            "source_class": "windows:sysmon",
            "engine_view": corpus["specimens"][0]["engine_view"],
        }
    )
    path = _write_corpus(tmp_path, corpus)
    texts = real_corpus_embed_texts(path)
    assert len(texts) == 8  # all real parents, forge + live_lab excluded


def test_pid_for_port_parses_lsof_output(monkeypatch):
    class _Proc:
        stdout = "1458\n"

    monkeypatch.setattr(embedding_bench.subprocess, "run", lambda *a, **k: _Proc())
    assert embedding_bench.pid_for_port(8917) == 1458


def test_pid_for_port_none_when_no_listener(monkeypatch):
    class _Proc:
        stdout = ""

    monkeypatch.setattr(embedding_bench.subprocess, "run", lambda *a, **k: _Proc())
    assert embedding_bench.pid_for_port(8917) is None


def test_resident_memory_mb_converts_kib(monkeypatch):
    class _Proc:
        stdout = "  1528800\n"

    monkeypatch.setattr(embedding_bench.subprocess, "run", lambda *a, **k: _Proc())
    assert embedding_bench.resident_memory_mb(1458) == 1492.97
