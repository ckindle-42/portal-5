from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from portal.modules.security.core.hunt.notables.__main__ import _parser
from portal.modules.security.core.hunt.notables.behaviours import Behaviour
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.embedding import PipelineEmbeddingClient
from portal.modules.security.core.hunt.notables.judge_notables import notable_prompt
from portal.modules.security.core.hunt.notables.knowledge import KnowledgeItem, build_store
from portal.modules.security.core.hunt.notables.pipeline import BackendPinnedClient
from portal.modules.security.core.hunt.notables.similar import (
    SimilarityError,
    _ranked_notables,
    generate_similar,
)


class _Embedder:
    model = "unit-embedding-model"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "execute" in text else [0.0, 1.0] for text in texts]

    def stats(self) -> dict[str, int]:
        return {"requests": 1, "items": 1}


class _ContrastEmbedder(_Embedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "did execute" in text and ("alpha" in text or "alice" in text):
                vectors.append([0.0, 1.0])
            elif "did execute" in text:
                vectors.append([0.6, 0.8])
            else:
                vectors.append([0.8, 0.6])
        return vectors


def _knowledge_items() -> list[KnowledgeItem]:
    items = []
    for family in ("ait_a", "ait_b", "kyoushi"):
        index = family
        for item, label_kind, statement in (
            ("one", "known_bad", "actor alice did execute to shell"),
            ("two", "known_bad", "actor bob did execute to shell"),
            ("three", "known_good", "actor service did read to file"),
            ("four", "known_good", "actor backup did read to file"),
        ):
            items.append(
                KnowledgeItem(
                    statement=statement,
                    label=f"{label_kind}-{item}",
                    label_kind=label_kind,
                    label_basis=("attack_step" if label_kind == "known_bad" else "unlabelled"),
                    family=family,
                    split="build",
                    index=index,
                    source_kind="activity",
                    query=f'search index="{index}" TERM("{item}") | head 5',
                )
            )
    return items


def _behaviour() -> Behaviour:
    return Behaviour(
        source_id="run:activity",
        actor_field="user",
        actor="alice",
        action_field="action",
        action="execute",
        object_field="path",
        object="shell",
        actor_mode="literal",
        action_mode="literal",
        object_mode="literal",
        events=2,
        first_seen=10.0,
        last_seen=20.0,
        hosts=1,
        actors=1,
        example_time=10.0,
        example_query='search index="run" TERM("alice") | head 5',
        example_raw="event line",
        example_earliest=0.0,
        example_latest=60.0,
    )


def _card() -> SourceCard:
    return SourceCard(
        index="run",
        sourcetype="activity",
        kind="activity",
        roles={"actor": ("user",), "action": ("action",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="",
    )


def test_similarity_uses_family_filtered_store_and_returns_labelled_matches(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.duckdb"
    embedder = _Embedder()
    build_store(_knowledge_items(), embedder, store)

    notables, receipt = generate_similar(
        [_behaviour()],
        [_card()],
        store_path=store,
        run_index="kyoushi",
        expected_family="kyoushi",
        allowed_families=("ait_a", "ait_b", "kyoushi"),
        embedder=embedder,  # type: ignore[arg-type]
    )

    assert receipt["scored"] == 1
    assert receipt["excluded_family"] == "kyoushi"
    assert receipt["loaded_families"] == ["ait_a", "ait_b"]
    assert receipt["reliability"]["method"] == "leave_one_family_out"
    assert notables[0].generator == "similar_to_known"
    assert notables[0].measure_name == "known_bad"
    assert notables[0].generator_reliability == 1.0
    assert notables[0].nearest_known[0]["family"] != "kyoushi"
    assert notables[0].nearest_known[0]["label_kind"] in {"known_bad", "known_good"}
    assert notables[0].as_dict()["evidence"][0]["query"].startswith('search index="run"')
    prompt = notable_prompt(notables[0].as_dict())
    assert "generator reliability (measured AUC): 1.000" in prompt
    assert "nearest known items:" in prompt


def test_similarity_accepts_activity_part_when_source_has_measurement_part(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.duckdb"
    embedder = _Embedder()
    build_store(_knowledge_items(), embedder, store)
    measurement = replace(_card(), kind="measurement", roles={})

    notables, receipt = generate_similar(
        [_behaviour()],
        [_card(), measurement],
        store_path=store,
        run_index="kyoushi",
        expected_family="kyoushi",
        allowed_families=("ait_a", "ait_b", "kyoushi"),
        embedder=embedder,  # type: ignore[arg-type]
    )

    assert receipt["scored"] == 1
    assert notables[0].generator == "similar_to_known"


def test_similarity_error_names_source_and_actual_card_kind() -> None:
    measurement = replace(_card(), kind="measurement", roles={})

    with pytest.raises(SimilarityError, match=r"run:activity.*measurement"):
        _ranked_notables(None, [_behaviour()], [measurement], {}, {"score": "known_bad"})  # type: ignore[arg-type]


def test_known_good_is_used_only_when_its_measured_auc_improves(tmp_path: Path) -> None:
    items = []
    for family, actor in (("a", "alpha"), ("b", "beta"), ("kyoushi", "target")):
        for number in (1, 2):
            items.extend(
                [
                    KnowledgeItem(
                        statement=f"actor {actor}-bad-{number} did execute to shell",
                        label=f"attack-{number}",
                        label_kind="known_bad",
                        label_basis="attack_step",
                        family=family,
                        split="build",
                        index=family,
                        source_kind="activity",
                        query=f'search index="{family}" TERM("bad-{number}") | head 5',
                    ),
                    KnowledgeItem(
                        statement=f"actor {actor}-good-{number} did read to file",
                        label=f"routine-{number}",
                        label_kind="known_good",
                        label_basis="unlabelled",
                        family=family,
                        split="build",
                        index=family,
                        source_kind="activity",
                        query=f'search index="{family}" TERM("good-{number}") | head 5',
                    ),
                ]
            )
    embedder = _ContrastEmbedder()
    store = tmp_path / "contrast.duckdb"
    build_store(items, embedder, store)

    _notables, receipt = generate_similar(
        [_behaviour()],
        [_card()],
        store_path=store,
        run_index="kyoushi",
        expected_family="kyoushi",
        allowed_families=("a", "b", "kyoushi"),
        embedder=embedder,  # type: ignore[arg-type]
    )

    reliability = receipt["reliability"]
    assert reliability["known_bad_auc"] == 0.5
    assert reliability["known_bad_minus_good_auc"] == 0.75
    assert reliability["score"] == "known_bad_minus_good"


def test_cli_keeps_the_original_generators_as_default() -> None:
    args = _parser().parse_args(["--index", "run", "--out", "/tmp/hunt"])

    assert args.generators == "alerts,peer_rare,deviation,misfit"


def test_pipeline_embeddings_batch_authenticate_and_retry_back_pressure() -> None:
    calls = 0
    waits: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer secret"
        payload = json.loads(request.content)
        assert payload["model"] == "unit-embedding-model"
        assert len(payload["input"]) <= 64
        if calls == 1:
            return httpx.Response(503, headers={"Retry-After": "3"}, request=request)
        return httpx.Response(
            200,
            json={
                "model": "unit-embedding-model",
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
            },
            request=request,
        )

    client = PipelineEmbeddingClient(
        url="http://pipeline.test",
        model="unit-embedding-model",
        api_key="secret",
        transport=httpx.MockTransport(handle),
        sleep=waits.append,
    )
    try:
        vectors = client.embed(["first", "second"])
        stats = client.stats()
    finally:
        client.close()

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert waits == [3.0]
    assert stats["throttles"] == 1
    assert stats["retries"] == 1
    assert stats["requests"] == 1


def test_pipeline_embeddings_split_inputs_at_64() -> None:
    batch_sizes: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        batch_sizes.append(len(payload["input"]))
        return httpx.Response(
            200,
            json={
                "model": "unit-embedding-model",
                "data": [
                    {"index": index, "embedding": [1.0, 0.0]}
                    for index, _text in enumerate(payload["input"])
                ],
            },
            request=request,
        )

    client = PipelineEmbeddingClient(
        url="http://pipeline.test",
        model="unit-embedding-model",
        api_key="secret",
        transport=httpx.MockTransport(handle),
    )
    try:
        vectors = client.embed([f"statement {index}" for index in range(130)])
    finally:
        client.close()

    assert len(vectors) == 130
    assert sorted(batch_sizes) == [2, 64, 64]


def test_hunt_reasoning_client_pins_the_requested_pipeline_backend() -> None:
    class _Client:
        request: dict[str, Any] | None = None

        def complete(self, **request: Any) -> dict[str, Any]:
            self.request = request
            return {"ok": True}

    inner = _Client()
    client = BackendPinnedClient(inner, "omlx-general")

    assert client.complete(model="hunt-reasoning") == {"ok": True}
    assert inner.request == {"model": "hunt-reasoning", "portal_backend": "omlx-general"}
