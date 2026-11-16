from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from portal.modules.security.core.hunt import product_jobs
from portal.modules.security.core.hunt.executor import (
    DEFAULT_BUDGETS,
    HuntBudget,
    HuntBudgetExceededError,
)
from portal.modules.security.core.hunt.notables.receipt import progress_update
from portal.modules.security.core.hunt.notables.similar import SIMILAR_GENERATOR
from portal.modules.security.tools import review_mcp


def _cards_stage(**kwargs: Any) -> dict[str, Any]:
    out = kwargs["out"]
    (out / "sources.json").write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "c1",
                        "source_id": "ix:auth",
                        "kind": "alert",
                        "understood": True,
                    }
                ]
            }
        )
    )
    return progress_update(out, "cards", {"model_requests": 2, "model_seconds": 1.0})


def _behaviours_stage(**kwargs: Any) -> tuple[list[Any], dict[str, Any]]:
    return [], progress_update(kwargs["out"], "behaviours", {"events_read": 4})


def _notables_stage(captured: dict[str, Any]):
    def run(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        captured.update(kwargs)
        out = kwargs["out"]
        row = {
            "notable_id": "n1",
            "generator": "similar_to_known",
            "source_id": "ix:auth",
            "measure": {"name": "similarity", "value": 0.9},
            "nearest_known": {"family": "santos", "label": "T1059"},
            "p_yes": 0.91,
            "evidence": [{"query": "search index=ix", "line": "user=bob"}],
        }
        (out / "notables.jsonl").write_text(json.dumps(row) + "\n")
        receipt = {SIMILAR_GENERATOR: {"embedding": {"requests": 3, "seconds": 2.0}}}
        return [row], progress_update(out, "notables", receipt)

    return run


def _judge_stage(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return [], progress_update(kwargs["out"], "judge", {"requests": 1, "model_seconds": 2.0})


def _relate_stage(**kwargs: Any) -> dict[str, Any]:
    (kwargs["out"] / "relate.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case1",
                        "anchor_entity": "bob",
                        "evidence": [{"event_id": "1:2", "raw": "user=bob"}],
                        "links": [],
                    }
                ],
                "receipt": {"seeds": 1, "coverage_complete": True},
            }
        )
    )
    return {"cases": 1}


def _tracked(name: str, run: Any, seen: list[str]):
    def call(**kwargs: Any) -> Any:
        seen.append(name)
        return run(**kwargs)

    return call


def test_hunt_start_routes_to_the_r2_job_runner(monkeypatch: Any) -> None:
    search = object()
    started: dict[str, Any] = {}

    def start(*args: Any, **kwargs: Any) -> str:
        started["args"] = args
        started["kwargs"] = kwargs
        return "hunt-r2-test"

    monkeypatch.setattr(review_mcp, "_hunt_search", lambda: search)
    monkeypatch.setattr(review_mcp, "r2_hunt_jobs", SimpleNamespace(start=start))
    monkeypatch.setattr(
        review_mcp.hunt_jobs,
        "start",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy hunt used")),
    )

    result = review_mcp.hunt_start(index="hb_kyoushi_s1", start=100.0, end=200.0)

    assert started["args"][:4] == (search, "hb_kyoushi_s1", 100.0, 200.0)
    assert started["args"][4] == {
        "query_seconds": 30.0,
        "job_seconds": 720.0,
        "requests": 2000,
        "cells": 10000,
        "events": 5000,
    }
    assert result["job_id"] == "hunt-r2-test"


def test_start_persists_queued_job_and_dispatches_background_worker(
    tmp_path: Path, monkeypatch: Any
) -> None:
    store = tmp_path / "knowledge.duckdb"
    store.touch()
    embedder = SimpleNamespace(close=lambda: None, set_job_deadline=lambda _deadline: None)
    launched = threading.Event()
    captured: list[Any] = []
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    monkeypatch.setenv("PORTAL_HUNT_KNOWLEDGE_STORE", str(store))
    monkeypatch.setenv("PORTAL_HUNT_KNOWLEDGE_FAMILIES", "santos,russell")
    monkeypatch.setattr(product_jobs, "model_from_env", lambda: (object(), "hunt-reasoning"))
    monkeypatch.setattr(product_jobs, "embedding_from_env", lambda: embedder)

    def run(*args: Any) -> None:
        captured.extend(args)
        launched.set()

    monkeypatch.setattr(product_jobs, "_run", run)
    job_id = product_jobs.start(object(), "hb_kyoushi_s1", 100.0, 200.0)  # type: ignore[arg-type]

    assert launched.wait(2.0)
    assert product_jobs.load(job_id)["status"] == "QUEUED"
    assert captured[7] == store
    assert captured[8] == ("santos", "russell")
    assert captured[9] is embedder


def test_r2_job_persists_stage_progress_cost_and_analyst_views(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    monkeypatch.setattr(product_jobs, "preflight", lambda _client, _model: None)
    seen: list[str] = []
    configured: dict[str, Any] = {}
    embedder = SimpleNamespace(close=lambda: None, set_job_deadline=lambda _deadline: None)
    store = tmp_path / "knowledge.duckdb"
    for name, run in (
        ("cards", _cards_stage),
        ("behaviours", _behaviours_stage),
        ("notables", _notables_stage(configured)),
        ("judge", _judge_stage),
        ("relate", _relate_stage),
    ):
        monkeypatch.setattr(product_jobs, f"{name}_stage", _tracked(name, run, seen))
    job_id = "hunt-r2-test-run"
    product_jobs._write(
        job_id,
        {"job_id": job_id, "index": "ix", "started": 1.0, "status": "QUEUED"},
    )

    product_jobs._run(
        job_id,
        object(),  # type: ignore[arg-type]
        "ix",
        100.0,
        200.0,
        dict(DEFAULT_BUDGETS),
        (object(), "hunt-reasoning"),  # type: ignore[arg-type]
        store,
        ("santos", "russell"),
        embedder,  # type: ignore[arg-type]
    )

    job = product_jobs.load(job_id)
    assert job is not None
    assert job["status"] == "COMPLETE"
    assert seen == ["cards", "behaviours", "notables", "judge", "relate"]
    assert SIMILAR_GENERATOR in configured["enabled"]
    assert configured["knowledge_store"] == store
    assert configured["knowledge_families"] == ("santos", "russell")
    assert job["cost"]["model_requests"] == 4
    assert job["cost"]["embedding_requests"] == 3
    assert job["progress"]["stages"]["notables"]
    assert job["progress"]["stages"]["relate"]["coverage_complete"] is True
    lead = product_jobs.leads_view(job_id=job_id)["leads"][0]
    assert lead["similar_known_item"] == {
        "family": "santos",
        "label": "T1059",
    }
    assert lead["judge_score"] == 0.91
    assert lead["evidence"][0]["query"] == "search index=ix"
    assert product_jobs.sources_view(job_id=job_id)["cards"][0]["understood"] is True
    assert product_jobs.case_view(job_id=job_id)["evidence"][0]["event_id"] == "1:2"


def test_pipeline_requests_use_the_remaining_hunt_deadline(monkeypatch: Any) -> None:
    effort = HuntBudget(dict(DEFAULT_BUDGETS))
    monkeypatch.setattr(effort, "remaining", lambda: 0.25)
    seen: dict[str, Any] = {}
    client = SimpleNamespace(complete=lambda **request: seen.update(request) or {"ok": True})

    result = product_jobs.HuntJobClient(client, effort).complete(model="hunt-reasoning")

    assert result == {"ok": True}
    assert seen["_timeout_seconds"] == 0.25
    monkeypatch.setattr(effort, "remaining", lambda: 0.0)
    with pytest.raises(HuntBudgetExceededError):
        product_jobs.HuntJobClient(client, effort).complete(model="hunt-reasoning")


def test_hunt_timeout_is_not_sent_as_a_pipeline_completion_field() -> None:
    import httpx

    from portal.modules.security.core.hunt.judge import OpenAICompatibleClient

    bodies: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []})

    client = OpenAICompatibleClient(
        "http://pipeline.test/v1/chat/completions", transport=httpx.MockTransport(respond)
    )
    client.complete(model="hunt-reasoning", _timeout_seconds=0.25)

    assert bodies == [{"tool_choice": "none", "model": "hunt-reasoning"}]


def test_embedding_requests_stop_at_the_shared_hunt_deadline() -> None:
    import httpx

    from portal.modules.security.core.hunt.notables.embedding import (
        EmbeddingError,
        PipelineEmbeddingClient,
    )

    calls: list[httpx.Request] = []
    client = PipelineEmbeddingClient(
        url="http://pipeline.test",
        model="embedder",
        api_key="test",
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={})
        ),
        clock=lambda: 100.0,
    )
    client.set_job_deadline(lambda: 99.0)

    with pytest.raises(EmbeddingError, match="hunt job deadline"):
        client.embed(["statement"])

    assert calls == []
    client.close()
