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


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
    receipt = {
        "requests": 1,
        "model_seconds": 2.0,
        "selection": {"policy": "stage1_rank", "candidates": 1, "judged": 1, "cut": 0},
    }
    progress_update(kwargs["out"], "judge", receipt)
    return [{"p_yes": 0.91}], receipt


def _capture_judge(captured: dict[str, Any]):
    def run(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        captured.update(kwargs)
        return _judge_stage(**kwargs)

    return run


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
        "job_seconds": 1260.0,
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
    assert captured[5]["job_seconds"] == 1260.0


def test_r2_job_persists_stage_progress_cost_and_analyst_views(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    monkeypatch.setattr(product_jobs, "preflight", lambda _client, _model: None)
    seen: list[str] = []
    configured: dict[str, Any] = {}
    judge_options: dict[str, Any] = {}
    rerank_options: dict[str, Any] = {}
    embedder = SimpleNamespace(close=lambda: None, set_job_deadline=lambda _deadline: None)
    store = tmp_path / "knowledge.duckdb"
    for name, run in (
        ("cards", _cards_stage),
        ("behaviours", _behaviours_stage),
        ("notables", _notables_stage(configured)),
        ("judge", _capture_judge(judge_options)),
        ("relate", _relate_stage),
    ):
        monkeypatch.setattr(product_jobs, f"{name}_stage", _tracked(name, run, seen))

    def _product_order(rows: Any, **kwargs: Any) -> tuple[list[int], dict[str, Any]]:
        rerank_options.update(kwargs)
        seen.append("rerank")
        return [0], {
            "content_keys": ["product:n1"],
            "weight": 1.0,
            "weight_basis": "p_yes_signal_without_product_label_keys",
            "council": {
                "source": "live",
                "model_seconds": 0.5,
                "budget_basis": {
                    "source": "measured_rate",
                    "probe_calls": 1,
                    "seconds_per_call": 22.8922,
                    "deadline_seconds": kwargs["deadline"],
                    "derived_budget": 1,
                },
            },
        }

    monkeypatch.setattr(product_jobs, "product_order", _product_order)
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
    assert seen == ["cards", "behaviours", "notables", "judge", "rerank", "relate"]
    assert SIMILAR_GENERATOR in configured["enabled"]
    assert configured["knowledge_store"] == store
    assert configured["knowledge_families"] == ("santos", "russell")
    assert judge_options["deadline_seconds"] == pytest.approx(480.0, abs=0.01)
    assert rerank_options["deadline"] == pytest.approx(120.0, abs=0.01)
    assert job["cost"]["model_requests"] == 5
    assert job["cost"]["model_seconds"] >= 0.5
    assert job["cost"]["embedding_requests"] == 3
    assert job["progress"]["stages"]["notables"]
    assert job["progress"]["stages"]["relate"]["coverage_complete"] is True
    assert job["progress"]["stages"]["rerank"]["council"]["budget_basis"][
        "seconds_per_call"
    ] == pytest.approx(22.8922)
    assert job["judge_selection"] == {
        "policy": "stage1_rank",
        "candidates": 1,
        "judged": 1,
        "cut": 0,
    }
    assert [entry["stage"] for entry in job["stage_plan"]] == [
        "cards",
        "behaviours",
        "notables",
        "judge",
        "rerank",
        "relate",
    ]
    assert job["stage_plan"][4]["council_budget"]["derived_budget"] == 1
    lead = product_jobs.leads_view(job_id=job_id)["leads"][0]
    assert lead["similar_known_item"] == {
        "family": "santos",
        "label": "T1059",
    }
    assert lead["judge_score"] == 0.91
    assert lead["evidence"][0]["query"] == "search index=ix"
    assert product_jobs.sources_view(job_id=job_id)["cards"][0]["understood"] is True
    assert product_jobs.case_view(job_id=job_id)["evidence"][0]["event_id"] == "1:2"
    status = product_jobs.status(job_id=job_id)
    assert status["stage_plan"] == job["stage_plan"]
    assert status["judge_selection"]["cut"] == 0


def test_cards_budget_uses_measured_allowance_and_records_fake_clock_elapsed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(product_jobs.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    effort = HuntBudget(dict(product_jobs.R2_DEFAULT_BUDGETS))
    effort.started = clock.now
    job_id = "hunt-r2-card-budget"
    product_jobs._write(job_id, {"job_id": job_id, "status": "RUNNING"})
    seen: dict[str, float] = {}

    def cards() -> None:
        seen["budget_seconds"] = effort.remaining()
        clock.advance(58.0)

    state = {"stage_plan": []}
    product_jobs._execute_stages(
        (("cards", cards),), job_id, state, threading.RLock(), tmp_path, effort
    )

    plan = state["stage_plan"][0]
    assert seen["budget_seconds"] == 60.0
    assert plan["estimate_s"] == 60.0
    assert plan["elapsed_s"] == 58.0
    assert plan["complete"] is True


def test_cards_deadline_with_zero_leads_finishes_partial(tmp_path: Path, monkeypatch: Any) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(product_jobs.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    monkeypatch.setattr(product_jobs, "preflight", lambda _client, _model: None)
    real_budget = product_jobs.HuntBudget

    def fake_budget(limits: dict[str, float]) -> HuntBudget:
        effort = real_budget(limits)
        effort.started = clock.now
        return effort

    monkeypatch.setattr(product_jobs, "HuntBudget", fake_budget)

    def cards(**kwargs: Any) -> dict[str, Any]:
        budget = kwargs["client"].budget_seconds
        clock.advance(budget + 1.0)
        return progress_update(
            kwargs["out"],
            "cards",
            {"cards": 43, "understood": 25, "backpressure": {"budget_seconds": budget}},
        )

    def notables(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        (kwargs["out"] / product_jobs.NOTABLES_FILE).write_text("")
        receipt = {"total": 0}
        progress_update(kwargs["out"], "notables", receipt)
        return [], receipt

    def empty_judge(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        receipt = {"requests": 0, "selection": {"candidates": 0, "judged": 0, "cut": 0}}
        progress_update(kwargs["out"], "judge", receipt)
        return [], receipt

    def empty_relate(**kwargs: Any) -> dict[str, Any]:
        receipt = {"seeds": 0, "coverage_complete": False}
        (kwargs["out"] / product_jobs.RELATE_FILE).write_text(
            json.dumps({"receipt": receipt, "notables": [], "cases": []})
        )
        return receipt

    monkeypatch.setattr(product_jobs, "cards_stage", cards)
    monkeypatch.setattr(product_jobs, "behaviours_stage", _behaviours_stage)
    monkeypatch.setattr(product_jobs, "notables_stage", notables)
    monkeypatch.setattr(product_jobs, "judge_stage", empty_judge)
    monkeypatch.setattr(product_jobs, "relate_stage", empty_relate)
    job_id = "hunt-r2-cards-cut"
    product_jobs._write(
        job_id, {"job_id": job_id, "index": "ix", "started": 1000.0, "status": "QUEUED"}
    )

    product_jobs._run(
        job_id,
        object(),  # type: ignore[arg-type]
        "ix",
        100.0,
        200.0,
        dict(product_jobs.R2_DEFAULT_BUDGETS),
        (object(), "hunt-reasoning"),  # type: ignore[arg-type]
        None,
        None,
        None,
    )

    state = product_jobs.status(job_id=job_id)
    leads = product_jobs.leads_view(job_id=job_id)
    assert leads["total_leads"] == 0
    assert state["status"] == "PARTIAL"
    assert state["partial_reason"] == "cards: cards_stage_deadline_exceeded"
    assert state["stage_plan"][0]["elapsed_s"] == 61.0
    assert state["stage_plan"][0]["complete"] is False
    assert state["stage_plan"][0]["exhausted_reason"] == "cards_stage_deadline_exceeded"


def test_stage_plan_preserves_relation_time_and_cuts_judging_first() -> None:
    plan = product_jobs._stage_plan("judge", 180.0)

    assert plan["budget_s"] == 0.0
    assert plan["reserved_for_later"] == {"rerank": 120.0, "relate": 120.0}
    council = product_jobs._stage_plan("rerank", 180.0)
    assert council["budget_s"] == 60.0
    assert council["reserved_for_later"] == {"relate": 120.0}
    full = product_jobs._stage_plan("cards", 1247.0)
    assert full["budget_s"] == 60.0
    assert full["reserved_for_later"]["judge"] == 517.0
    short = product_jobs._stage_plan("cards", 707.0)
    assert short["budget_s"] == 37.0
    assert short["reserved_for_later"] == {
        "behaviours": 80.0,
        "notables": 350.0,
        "judge": 0.0,
        "rerank": 120.0,
        "relate": 120.0,
    }


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


def test_stage_deadline_bounds_a_request_without_replacing_the_job_deadline() -> None:
    effort = HuntBudget(dict(DEFAULT_BUDGETS))
    effort.set_stage_deadline("judge", 60.0)
    seen: dict[str, Any] = {}
    client = SimpleNamespace(complete=lambda **request: seen.update(request) or {"ok": True})

    product_jobs.HuntJobClient(client, effort).complete(model="hunt-reasoning")
    snapshot = effort.snapshot()

    assert seen["_timeout_seconds"] <= 60.0
    assert snapshot["remaining_s"] > 600.0
    assert 0.0 < snapshot["stage_remaining_s"] <= 60.0
    effort.set_stage_deadline("judge", 0.0)
    assert effort.expired_reason() == "judge_stage_deadline_exceeded"


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


def test_leads_view_caps_default_payload_and_keeps_similarity_text_trace(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    out = tmp_path / "hunt-r2-lead-size"
    out.mkdir()
    rows = []
    for number in range(10):
        rows.append(
            {
                "notable_id": f"n{number}",
                "generator": "similar_to_known",
                "source_id": "x" * 2000,
                "what": "candidate behaviour " + "c" * 2000,
                "measure": {"name": "similarity", "value": 0.99},
                "nearest_known": [
                    {
                        "family": "santos",
                        "label": "known behaviour " + "r" * 2000,
                        "label_kind": "known_bad",
                        "similarity": 0.997,
                        "statement": "reference behaviour " + "s" * 2000,
                        "query": "search index=known " + "q" * 2000,
                    }
                ],
                "p_yes": 0.9,
                "evidence": [
                    {
                        "line": "e" * 2000,
                        "query": "search index=run " + "z" * 2000,
                    }
                ],
            }
        )
    (out / product_jobs.NOTABLES_FILE).write_text("".join(json.dumps(row) + "\n" for row in rows))
    product_jobs._write(
        "hunt-r2-lead-size",
        {
            "job_id": "hunt-r2-lead-size",
            "index": "ix",
            "started": 1.0,
            "run_dir": str(out),
        },
    )

    result = product_jobs.leads_view(job_id="hunt-r2-lead-size")

    assert 1 <= result["returned_leads"] <= 3
    assert result["total_leads"] == 10
    assert result["truncated"] is True
    assert len(json.dumps(result)) < 6000
    assert result["leads"][0]["similarity_text"]["candidate"].startswith("candidate behaviour")
    assert result["leads"][0]["similarity_text"]["reference"].startswith("reference behaviour")
    assert result["leads"][0]["similar_known_item"]["family"] == "santos"


def test_leads_view_uses_product_rerank_and_council_receipt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    out = tmp_path / "hunt-r2-reranked"
    out.mkdir()
    rows = [
        {"notable_id": f"n{i}", "content_key": f"k{i}", "p_yes": score, "what": f"n{i}"}
        for i, score in enumerate((0.1, 0.9, 0.5))
    ]
    (out / product_jobs.NOTABLES_FILE).write_text("".join(json.dumps(row) + "\n" for row in rows))
    (out / "rerank.json").write_text(json.dumps({"order": [1, 2, 0]}))
    (out / "rerank_council_calls.jsonl").write_text(
        json.dumps({"content_key": "k1", "decision": "SUPPORT"})
        + "\n"
        + json.dumps({"content_key": "k2", "decision": "REJECT"})
        + "\n"
    )
    product_jobs._write(
        "hunt-r2-reranked",
        {
            "job_id": "hunt-r2-reranked",
            "index": "hb_kyoushi_s1",
            "started": 1.0,
            "run_dir": str(out),
        },
    )

    result = product_jobs.leads_view(job_id="hunt-r2-reranked")

    assert [lead["notable_id"] for lead in result["leads"]] == ["n1", "n2", "n0"]
    assert result["leads"][0]["council"]["decision"] == "SUPPORT"
    assert result["leads"][1]["council"]["decision"] == "REJECT"
    assert result["leads"][2]["council"] is None
