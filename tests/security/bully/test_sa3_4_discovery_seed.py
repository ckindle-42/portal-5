"""SA3.4 -- full-corpus re-index per embedding arm (version-tagged).

Tests the seeding driver (`scripts/defensive_bully_discovery_seed.py`) offline:
a mock embed client serves deterministic vectors, and the driver must land every
real parent into a fresh, version-tagged projection with a recorded wall-clock.
Non-overlapping/version-tagged indexes are asserted via the projection's
`embedding_version` stats and the seed report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.defensive_bully_discovery_seed import (  # noqa: E402
    SEED_REPORT_SCHEMA,
    _real_parent_records,
    seed_projection,
)


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

    return httpx.Client(transport=httpx.MockTransport(handler))


def _write_corpus(tmp_path: Path, n_parents: int = 20) -> Path:
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


def test_real_parent_records_only_attack_data(tmp_path: Path):
    import hashlib

    from portal.modules.security.core.bully.cousin_calibration_bench import _canonical
    from tests.security.bully._discovery_fixtures import make_specimen

    corpus = {
        "schema": "SPECIMEN_CORPUS_V2",
        "specimens": [
            make_specimen(
                "p1",
                technique_ids=["T1001"],
                family="f1",
                source_class="c1",
                action_sequence=["a", "b"],
            ),
            {
                "specimen_id": "forge",
                "source_lane": "replay_mutation",
                "source_class": "c1",
                "engine_view": {"episode_view": {}, "telemetry_view": {}},
            },
        ],
    }
    corpus["snapshot_hash"] = hashlib.sha256(_canonical(corpus["specimens"]).encode()).hexdigest()
    records = _real_parent_records(corpus)
    assert len(records) == 1
    assert records[0]["record_id"] == "p1"


def test_seed_projection_indexes_all_parents_with_version_tag(tmp_path: Path):
    corpus_path = _write_corpus(tmp_path, n_parents=20)
    output = tmp_path / "arm-a-projection"
    report = seed_projection(
        corpus_path=corpus_path,
        output_dir=output,
        embed_url="http://localhost:8941/v1/embeddings",
        query_embed_url=None,
        embedding_version="mlx-qwen3-embed-0.6b-mxfp8",
        batch_size=8,
        embed_client=_mock_embed_client(),
    )
    assert report["schema"] == SEED_REPORT_SCHEMA
    assert report["parent_count"] == 20
    assert report["seeded_ids"] == 20
    assert report["embedding_version"] == "mlx-qwen3-embed-0.6b-mxfp8"
    assert report["wall_s"] > 0

    # projection is version-tagged and holds all 20 rows
    with Store(output / "snapshot_state.db") as store:
        organ = Organ(
            store=store,
            db_path=output / "organ_snapshot",
            embed_client=_mock_embed_client(),
            embedding_version="mlx-qwen3-embed-0.6b-mxfp8",
        )
        try:
            assert organ.stats()["row_count"] == 20
            assert organ.stats()["embedding_version"] == "mlx-qwen3-embed-0.6b-mxfp8"
        finally:
            organ.close()


def test_seed_projection_writes_seed_report(tmp_path: Path):
    corpus_path = _write_corpus(tmp_path, n_parents=5)
    output = tmp_path / "proj"
    report = seed_projection(
        corpus_path=corpus_path,
        output_dir=output,
        embed_url="http://localhost:8941/v1/embeddings",
        query_embed_url=None,
        embedding_version="v-test",
        batch_size=4,
        embed_client=_mock_embed_client(),
    )
    report_path = output / "seed_report.json"
    assert report_path.exists()
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded == report
    assert loaded["items_per_sec"] is not None and loaded["items_per_sec"] > 0


def test_two_arms_produce_non_overlapping_version_tagged_projections(tmp_path: Path):
    """A4: competing indexes must never mix -- each arm gets its own
    version-tagged projection."""
    corpus_path = _write_corpus(tmp_path, n_parents=12)
    out_a = tmp_path / "arm-a"
    out_b = tmp_path / "arm-b"
    seed_projection(
        corpus_path=corpus_path,
        output_dir=out_a,
        embed_url="http://localhost:8941/v1/embeddings",
        query_embed_url=None,
        embedding_version="mlx-qwen3-embed-0.6b-mxfp8",
        batch_size=4,
        embed_client=_mock_embed_client(),
    )
    seed_projection(
        corpus_path=corpus_path,
        output_dir=out_b,
        embed_url="http://localhost:8943/v1/embeddings",
        query_embed_url="http://localhost:8943/v1/embeddings/query",
        embedding_version="llamacpp-embeddinggemma-300m-q8",
        batch_size=4,
        embed_client=_mock_embed_client(),
    )
    for output, version in (
        (out_a, "mlx-qwen3-embed-0.6b-mxfp8"),
        (out_b, "llamacpp-embeddinggemma-300m-q8"),
    ):
        with Store(output / "snapshot_state.db") as store:
            organ = Organ(
                store=store,
                db_path=output / "organ_snapshot",
                embed_client=_mock_embed_client(),
                embedding_version=version,
            )
            try:
                assert organ.stats()["embedding_version"] == version
            finally:
                organ.close()
