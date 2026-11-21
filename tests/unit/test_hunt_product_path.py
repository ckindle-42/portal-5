from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from portal.modules.security.core.hunt import product_jobs
from portal.modules.security.core.hunt.executor import (
    DEFAULT_BUDGETS,
    HuntBudget,
)
from portal.modules.security.core.hunt.notables import run as notables_run
from portal.modules.security.core.hunt.notables.receipt import progress_update
from portal.modules.security.core.hunt.notables.similar import SIMILAR_GENERATOR


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
            "evidence": [{"query": "search index=ix", "line": "user=bob"}],
        }
        (out / "notables.jsonl").write_text(json.dumps(row) + "\n")
        receipt = {SIMILAR_GENERATOR: {"embedding": {"requests": 3, "seconds": 2.0}}}
        return [row], progress_update(out, "notables", receipt)

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


def test_nonterminal_hunt_views_return_compact_progress_instead_of_empty_results(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    job_id = "hunt-r2-running-views"
    run_dir = tmp_path / job_id
    run_dir.mkdir()
    (run_dir / "sources.json").write_text(json.dumps({"cards": [{"source_id": "ix:a"}]}))
    (run_dir / "notables.jsonl").write_text(json.dumps({"notable_id": "n1"}) + "\n")
    (run_dir / "relate.json").write_text(json.dumps({"cases": [{"case_id": "c1"}]}))
    progress = {"current": {"phase": "cards", "done": 2}, "stages": {"cards": {"seen": 2}}}
    product_jobs._write(
        job_id,
        {
            "job_id": job_id,
            "index": "ix",
            "status": "RUNNING",
            "stage": "cards",
            "started": 1.0,
            "progress": progress,
            "run_dir": str(run_dir),
        },
    )

    results = [
        product_jobs.sources_view(job_id=job_id),
        product_jobs.leads_view(job_id=job_id),
        product_jobs.case_view(job_id=job_id, case_no=1),
    ]

    for result in results:
        assert result["status"] == "RUNNING"
        assert result["stage"] == "cards"
        assert result["stages_done"] == "0/5"
        assert result["last_progress"] == "cards"
        assert "progress" not in result
        assert result["next"] == "Check this job again after it advances."
    assert "cards" not in results[0]
    assert "leads" not in results[1]
    assert "case" not in results[2]


def test_opt_in_judge_is_bounded_and_relation_still_uses_stage1_notables(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    monkeypatch.setattr(product_jobs, "preflight", lambda _client, _model: None)
    judge_call: dict[str, Any] = {}
    relate_call: dict[str, Any] = {}
    monkeypatch.setattr(product_jobs, "cards_stage", _cards_stage)
    monkeypatch.setattr(product_jobs, "behaviours_stage", _behaviours_stage)
    monkeypatch.setattr(product_jobs, "notables_stage", _notables_stage({}))

    def annotate(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        judge_call.update(kwargs)
        receipt = {
            "requests": 1,
            "selection": {"policy": "stage1_order_annotation_limit", "judged": 1},
        }
        progress_update(kwargs["out"], "judge", receipt)
        return [], receipt

    def relate(**kwargs: Any) -> dict[str, Any]:
        relate_call.update(kwargs)
        return _relate_stage(**kwargs)

    def no_rerank(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("product ranking must not call rerank or council")

    monkeypatch.setattr(product_jobs, "judge_stage", annotate)
    monkeypatch.setattr(product_jobs, "relate_stage", relate)
    monkeypatch.setattr(product_jobs, "product_order", no_rerank, raising=False)
    job_id = "hunt-r2-judge-opt-in"
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
        judge_enabled=True,
    )

    job = product_jobs.load(job_id)
    assert job is not None
    assert job["status"] == "COMPLETE"
    assert job["judge_enabled"] is True
    assert [item["stage"] for item in job["stage_plan"]] == [
        "cards",
        "behaviours",
        "notables",
        "relate",
        "judge",
    ]
    assert judge_call["max_notables"] == 10
    assert judge_call["explain"] is True
    assert relate_call.get("judged_only", False) is False
    assert not (tmp_path / job_id / product_jobs.RERANK_FILE).exists()


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
    assert seen["budget_seconds"] == 1260.0
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

    state = product_jobs.status(job_id=job_id, detail=True)
    leads = product_jobs.leads_view(job_id=job_id)
    assert leads["total_leads"] == 0
    assert state["status"] == "PARTIAL"
    assert state["partial_reason"] == "cards: cards_stage_deadline_exceeded"
    assert state["stage_plan"][0]["elapsed_s"] == state["stage_plan"][0]["budget_s"] + 1.0
    assert state["stage_plan"][0]["complete"] is False
    assert state["stage_plan"][0]["exhausted_reason"] == "cards_stage_deadline_exceeded"


def test_judge_stage_annotates_only_the_top_ten_without_reordering(
    tmp_path: Path, monkeypatch: Any
) -> None:
    rows = [
        {"notable_id": f"n{index}", "content_key": f"k{index}", "what": f"item {index}"}
        for index in range(12)
    ]
    path = tmp_path / product_jobs.NOTABLES_FILE
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    captured: dict[str, Any] = {}

    def judge_all(notables: list[dict[str, Any]], **kwargs: Any):
        captured["notables"] = notables
        captured.update(kwargs)
        annotated = [
            {**row, "p_yes": 0.7, "judge": {"answer": "yes: short reason"}} for row in notables
        ]
        return annotated, {
            "judged": len(annotated),
            "unasked": 0,
            "requests": len(annotated),
            "unjudged_reasons": {},
        }

    monkeypatch.setattr(notables_run, "judge_all", judge_all)
    _judged, receipt = notables_run.judge_stage(
        out=tmp_path,
        client=object(),  # type: ignore[arg-type]
        model="hunt-reasoning",
        deadline_seconds=60.0,
        max_notables=10,
        explain=True,
    )

    saved = notables_run.read_notables(path)
    assert [row["notable_id"] for row in captured["notables"]] == [f"n{i}" for i in range(10)]
    assert captured["explain"] is True
    assert [row["notable_id"] for row in saved] == [f"n{i}" for i in range(12)]
    assert all(row["p_yes"] == 0.7 for row in saved[:10])
    assert all("p_yes" not in row for row in saved[10:])
    assert all(row["unjudged"] is False for row in saved[:10])
    assert all(row["unjudged"] is True for row in saved[10:])
    assert saved[0]["judge"]["answer"] == "yes: short reason"
    assert receipt["selection"] == {
        "policy": "stage1_order_annotation_limit",
        "candidates": 12,
        "judged": 10,
        "cached": 0,
        "cut": 2,
        "cut_reason": "annotation_limit",
    }


def test_stage_plan_preserves_relation_time_and_spends_released_ranking_time() -> None:
    plan = product_jobs._stage_plan("cards", 180.0)

    assert plan["budget_s"] == 0.0
    assert plan["reserved_for_later"] == {
        "behaviours": 100.0,
        "notables": 350.0,
        "relate": 120.0,
        "judge": 60.0,
    }
    judge_order = ("cards", "behaviours", "notables", "relate", "judge")
    judge = product_jobs._stage_plan("judge", 180.0, stage_order=judge_order)
    assert judge["budget_s"] == 60.0
    assert judge["reserved_for_later"] == {}
    full = product_jobs._stage_plan("cards", 1247.0)
    assert full["budget_s"] == 617.0
    assert full["reserved_for_later"] == {
        "behaviours": 100.0,
        "notables": 350.0,
        "relate": 120.0,
        "judge": 60.0,
    }
    short = product_jobs._stage_plan("cards", 707.0)
    assert short["budget_s"] == 77.0
    assert short["reserved_for_later"] == {
        "behaviours": 100.0,
        "notables": 350.0,
        "relate": 120.0,
        "judge": 60.0,
    }


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


def test_leads_view_caps_default_payload_and_returns_compact_rows(
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
            "status": "COMPLETE",
            "started": 1.0,
            "run_dir": str(out),
        },
    )

    result = product_jobs.leads_view(job_id="hunt-r2-lead-size")

    assert result["returned_leads"] == product_jobs.LEADS_VIEW_DEFAULT
    assert result["total_leads"] == 10
    assert result["omitted_leads"] == 8
    assert result["truncated"] is True
    assert result["next_offset"] == result["returned_leads"]
    assert len(json.dumps(result).encode()) <= 1024
    assert set(result["leads"][0]) == {
        "rank",
        "notable_id",
        "generator",
        "source",
        "why",
        "evidence_query",
        "source_truncated",
        "evidence_query_truncated",
    }
    assert result["leads"][0]["source"] == "x" * 60
    assert result["leads"][0]["evidence_query"] == ("search index=run " + "z" * 2000)[:100]


def test_leads_view_uses_product_rerank_order_in_compact_rows(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(product_jobs, "_ROOT", tmp_path)
    out = tmp_path / "hunt-r2-reranked"
    out.mkdir()
    rows = [
        {
            "notable_id": f"n{i}",
            "content_key": f"k{i}",
            "p_yes": score,
            "generator": "alerts",
            "source_id": f"source-{i}",
            "why": f"reason-{i}",
        }
        for i, score in enumerate((0.1, 0.9, 0.5))
    ]
    (out / product_jobs.NOTABLES_FILE).write_text("".join(json.dumps(row) + "\n" for row in rows))
    (out / "rerank.json").write_text(json.dumps({"order": [1, 2, 0]}))
    product_jobs._write(
        "hunt-r2-reranked",
        {
            "job_id": "hunt-r2-reranked",
            "index": "hb_kyoushi_s1",
            "status": "COMPLETE",
            "started": 1.0,
            "run_dir": str(out),
        },
    )

    result = product_jobs.leads_view(job_id="hunt-r2-reranked")

    assert [lead["source"] for lead in result["leads"]] == ["source-1", "source-2"]
    assert [lead["why"] for lead in result["leads"]] == ["reason-1", "reason-2"]
