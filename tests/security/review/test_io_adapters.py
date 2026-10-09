"""Fake-backed tests for the read, embedding, reference, and service adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from portal.modules.security.core.review import funnel, intake, knowledge, pipeline
from portal.modules.security.core.review.embedding import EmbeddingError, PlatformEmbedder
from portal.modules.security.core.review.reference import (
    load_reference,
    recalibrate,
    save_reference,
    stale,
)
from portal.modules.security.core.review.service import ReviewRequest, run_review
from portal.modules.security.core.review.window import (
    InMemoryWindowSource,
    SourceSpec,
    SplunkWindowSource,
    WindowFetchError,
    _result_objects,
)
from portal.platform.embedding.contract import Role, Task

from ._fakes import HashEmbedder, three_source_window


def _events(count: int = 2) -> str:
    return "".join(
        json.dumps(
            {
                "result": {
                    "_raw": f"raw-{index}",
                    "_time": str(index + 0.5),
                    "host": f"host-{index}",
                    "source": "wineventlog",
                    "EventCode": "4688",
                }
            }
        )
        for index in range(count)
    )


def test_splunk_window_uses_uncapped_exports_and_receipts_counts() -> None:
    calls: list[tuple[str, dict[str, list[str]]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.content.decode())
        search = params["search"][0]
        calls.append((search, params))
        body = '{"result":{"count":"2"}}' if search.startswith("| tstats") else _events()
        return httpx.Response(200, text=body)

    source = SplunkWindowSource(
        url="https://splunk.test:8089",
        user="u",
        password="p",
        partition_seconds=10,
        transport=httpx.MockTransport(handler),
    )
    spec = SourceSpec("botsv3", "XmlWinEventLog:Security")
    result = source.fetch([spec], 0, 2)

    assert result.expected == result.fetched == 2
    assert result.degraded == []
    assert [row["_raw"] for row in result.records_by_source[spec.source_id]] == ["raw-0", "raw-1"]
    assert all(row["_time"] in {0.5, 1.5} for row in result.records_by_source[spec.source_id])
    assert len(calls) == 2
    count_search, count_params = calls[0]
    event_search, event_params = calls[1]
    assert 'tstats count where index="botsv3" sourcetype="XmlWinEventLog:Security"' in count_search
    assert "earliest_time" in count_params and "latest_time" in count_params
    assert 'index="botsv3"' in event_search and "sourcetype=" in event_search
    assert "head" not in event_search.lower() and "limit" not in event_params
    assert event_params["output_mode"] == ["json"]


def test_splunk_count_mismatch_is_degraded_and_label_keys_fail_closed() -> None:
    def mismatch_handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.content.decode())
        body = (
            '{"result":{"count":"3"}}' if params["search"][0].startswith("| tstats") else _events(1)
        )
        return httpx.Response(200, text=body)

    source = SplunkWindowSource(
        url="https://splunk.test:8089",
        transport=httpx.MockTransport(mismatch_handler),
    )
    result = source.fetch([SourceSpec("i", "s")], 0, 1)
    assert result.receipts[0].degraded
    assert result.expected == 3 and result.fetched == 1
    assert "expected 3, fetched 1" in result.degraded[0]

    def label_handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.content.decode())
        if params["search"][0].startswith("| tstats"):
            return httpx.Response(200, text='{"result":{"count":"1"}}')
        return httpx.Response(
            200,
            text='{"result":{"_raw":"event","_time":"0.5","technique":"T1000"}}',
        )

    label_source = SplunkWindowSource(
        url="https://splunk.test:8089",
        transport=httpx.MockTransport(label_handler),
    )
    with pytest.raises(ValueError, match="label key"):
        label_source.fetch([SourceSpec("i", "s")], 0, 1)


def test_splunk_stream_parser_handles_json_objects_split_across_chunks() -> None:
    first = '{"result":{"_raw":"a\\nb","_time":"1"}}'
    second = '{"result":{"_raw":"c","_time":"2"}}'
    joined = first + second
    decoded = _result_objects([joined[:17], joined[17:41], joined[41:]])
    assert [row["_raw"] for row in decoded] == ["a\nb", "c"]


def test_in_memory_window_filters_partitions_and_receipts_mismatch() -> None:
    spec = SourceSpec("i", "s")
    source = InMemoryWindowSource(
        {spec.source_id: [{"_time": 0.5, "_raw": "a"}, {"_time": 2.5, "_raw": "b"}]},
        expected_overrides={(spec.source_id, 0, 2): 3},
        partition_seconds=2,
    )
    result = source.fetch([spec], 0, 4)
    assert [row["_raw"] for row in result.records_by_source[spec.source_id]] == ["a", "b"]
    assert [(item.expected, item.fetched) for item in result.receipts] == [(3, 1), (1, 1)]
    assert len(result.degraded) == 1


def test_platform_embedder_stamps_contract_batches_and_raises_on_errors() -> None:
    posts: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ready"):
            return httpx.Response(
                200,
                json={"ready": True, "identity": {"model": "google/embeddinggemma-2"}},
            )
        body = json.loads(request.content)
        posts.append(body)
        rows = [[1.0, 0.0, 0.0] for _ in body["inputs"]]
        return httpx.Response(200, json={"model": "google/embeddinggemma-2", "embeddings": rows})

    embedder = PlatformEmbedder(
        task=Task.SENTENCE_SIMILARITY,
        dim=3,
        role=Role.DOCUMENT,
        batch_size=2,
        transport=httpx.MockTransport(handler),
    )
    vectors = embedder.embed(["one", "two", "three"])
    assert len(vectors) == 3 and all(len(vector) == 3 for vector in vectors)
    assert len(posts) == 2 and [len(post["inputs"]) for post in posts] == [2, 1]
    assert all(post["task"] == Task.SENTENCE_SIMILARITY.value for post in posts)
    assert all(post["role"] == Role.DOCUMENT.value and post["dim"] == 3 for post in posts)
    assert "dim=3" in embedder.identity and "task=sentence similarity" in embedder.identity

    def bad_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ready"):
            return httpx.Response(
                200,
                json={"ready": True, "identity": {"model": "google/embeddinggemma-2"}},
            )
        return httpx.Response(503)

    bad = PlatformEmbedder(
        task=Task.SENTENCE_SIMILARITY,
        dim=3,
        transport=httpx.MockTransport(bad_handler),
    )
    with pytest.raises(EmbeddingError):
        bad.embed(["no fallback"])


class _RenamedHashEmbedder(HashEmbedder):
    identity = "hash-bow-256-next"


def test_reference_round_trip_and_embedder_recalibration(tmp_path: Path) -> None:
    policy = funnel.FunnelPolicy(0.2, 0.2, levels=("L2_ENTITY",))
    benign = intake.build_window_units(three_source_window(seed=201, n=240))
    old_embedder = HashEmbedder()
    anchors = pipeline.anchors_from_units(
        benign.units[:8], kind="benign_pattern", label="stable", malice="benign", prefix="ref"
    )
    old_index = knowledge.AnchorIndex.build(knowledge.cards_from_anchors(anchors), old_embedder)
    reference = pipeline.build_reference(
        benign,
        policy=policy,
        index=old_index,
        embedder=old_embedder,
        environment_id="env-1",
    )
    path = save_reference(reference, review_dir=tmp_path, name="botsv3")
    loaded = load_reference(review_dir=tmp_path, name="botsv3")
    assert path == tmp_path / "reference" / "botsv3.json"
    assert loaded.basis == reference.basis
    assert loaded.calibrations.ids() == reference.calibrations.ids()

    new_embedder = _RenamedHashEmbedder()
    assert stale(loaded, new_embedder.identity) == ["known_similar|L2_ENTITY"]
    new_index = knowledge.AnchorIndex.build(knowledge.cards_from_anchors(anchors), new_embedder)
    old_unusual = loaded.calibrations.get(funnel.CHANNEL_UNUSUAL, "L2_ENTITY")
    recalibrated = recalibrate(
        loaded,
        benign=benign,
        policy=policy,
        index=new_index,
        embedder=new_embedder,
        environment_id="env-1",
    )
    assert recalibrated.calibrations.get(funnel.CHANNEL_UNUSUAL, "L2_ENTITY") == old_unusual
    similar = recalibrated.calibrations.get(funnel.CHANNEL_SIMILAR, "L2_ENTITY")
    assert similar is not None and similar.embedder_id == new_embedder.identity
    assert stale(recalibrated, new_embedder.identity) == []


def test_service_is_the_window_to_pipeline_path_and_preserves_counts() -> None:
    spec = SourceSpec("memory", "wineventlog")
    records: list[dict[str, object]] = []
    for index in range(80):
        records.append(
            {
                "_time": float(index),
                "_raw": f"event {index}",
                "host": f"host-{index % 8}",
                "EventCode": "4688",
                "Image": "C:\\Windows\\System32\\svchost.exe",
                "CommandLine": "svchost.exe -k netsvcs",
            }
        )
    source = InMemoryWindowSource({spec.source_id: records}, partition_seconds=40)
    training = intake.build_window_units({spec.source_id: records})
    policy = funnel.FunnelPolicy(0.2, 0.2, levels=("L2_ENTITY",))
    reference = pipeline.build_reference(
        training, policy=policy, index=None, embedder=None, environment_id="memory-env"
    )
    config = pipeline.ReviewConfig(policy=policy)
    result = run_review(
        ReviewRequest([spec], 0, 80, "memory-env", config),
        source=source,
        embedder=None,
        index=None,
        reference=reference,
    )
    receipt = next(item for item in result.receipts if item.name == "window.fetch")
    assert (receipt.examined, receipt.resolved) == (80, 80)
    assert result.fingerprint["environment"] == "memory-env"
    assert result.fingerprint["fetched_events"] == "80"


def test_splunk_json_count_errors_fail_instead_of_looking_empty() -> None:
    source = SplunkWindowSource(
        url="https://splunk.test:8089",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="{}")),
    )
    with pytest.raises(WindowFetchError, match="tstats count returned"):
        source.fetch([SourceSpec("i", "s")], 0, 1)
