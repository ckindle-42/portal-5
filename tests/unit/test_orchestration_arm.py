"""Offline orchestration arm tests through a fake Pipeline API."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import sqlite3
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml
from fastapi import HTTPException

from portal.modules.coding.tools import code_sandbox_mcp as sandbox_mcp
from portal.modules.orchestration import service as service_module
from portal.modules.orchestration import shadow as shadow_module
from portal.modules.orchestration import tools as orchestration_tools
from portal.modules.orchestration.contracts import parse_plan
from portal.modules.orchestration.ledger import ArmLedger, ResumeMismatchError
from portal.modules.orchestration.planner import instantiate_plan_template, validate_execution_plan
from portal.modules.orchestration.queue import OvernightQueue, QueueGate, QueueLedger
from portal.modules.orchestration.service import (
    ArmService,
    StubNoticeSink,
    load_arm_config,
    load_residency_mode,
    module_is_enabled,
    seated_model_tags,
)
from portal.modules.orchestration.tools import (
    FILE_READ_LIMIT,
    FILE_WRITE_LIMIT,
    PYTEST_TIMEOUT_SECONDS,
    TASK_BYTES_LIMIT,
    TASK_FILE_LIMIT,
    TaskToolExecutor,
)
from portal.modules.orchestration.worker import Engine, PipelineError, WorkerResult, run_bite
from portal.platform.inference.router import auth
from portal.platform.inference.router.eval_gate import apply_bite_tool_scope

_fake_spec = spec_from_file_location(
    "_orchestration_fake_pipeline", Path(__file__).with_name("orchestration_fake_pipeline.py")
)
if _fake_spec is None or _fake_spec.loader is None:
    raise ImportError("could not load fake Pipeline API")
_fake_module = module_from_spec(_fake_spec)
sys.modules[_fake_spec.name] = _fake_module
_fake_spec.loader.exec_module(_fake_module)
DelayedResponse = _fake_module.DelayedResponse
FakePipeline = _fake_module.FakePipeline
SignalResponse = _fake_module.SignalResponse
finish_response = _fake_module.finish_response
text_response = _fake_module.text_response
tool_response = _fake_module.tool_response

_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

SEAT_TAGS = seated_model_tags(
    load_arm_config(Path(__file__).resolve().parents[2] / "config" / "orchestration_arm.yaml")
)


def bite(
    bite_id: str = "b1",
    *,
    expected: str = "right",
    tools: list[str] | None = None,
    inputs: list[str] | None = None,
    depends_on: list[str] | None = None,
    turns: int = 2,
    output_tokens: int = 256,
    model: str = "fast",
    review: str | None = None,
    review_reason: str | None = None,
    write_paths: list[str] | None = None,
    context_tokens: int = 8192,
) -> dict[str, Any]:
    return {
        "bite_id": bite_id,
        "goal": f"Produce the answer for {bite_id}.",
        "discipline": "offline-test",
        "inputs": inputs or [],
        **({"write_paths": write_paths or ["new.txt"]} if "file_write" in (tools or []) else {}),
        "depends_on": depends_on or [],
        "tools": tools or [],
        "output": {"path": f"bites/{bite_id}/output.json", "schema": _SCHEMA},
        "accept": [{"type": "equals", "path": "$.answer", "value": expected}],
        **({"review": review} if review else {}),
        **({"review_reason": review_reason} if review_reason else {}),
        "risk": "low",
        "budget": {
            "turns": turns,
            "minutes": 1,
            "output_tokens": output_tokens,
            "context_tokens": context_tokens,
        },
        "model": model,
        "procedure": "Use the declared checks, then finish.",
    }


def parallel_tool_response(*calls: tuple[str, str]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call-{index}",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                        for index, (name, arguments) in enumerate(calls, start=1)
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"completion_tokens": 4},
    }


def plan(task_id: str, *bites: dict[str, Any]) -> dict[str, Any]:
    return {"task_id": task_id, "goal": "Run the offline scenario.", "bites": list(bites)}


def service(
    tmp_path: Path,
    pipeline: FakePipeline,
    *,
    build_sha: str = "head-a",
    fast_digest: str = "fast-digest-a",
    deep_digest: str = "deep-digest-a",
    notices: StubNoticeSink | None = None,
) -> ArmService:
    config = tmp_path / "orchestration_arm.yaml"
    repo = Path(__file__).resolve().parents[2]
    settings = yaml.safe_load((repo / "config" / "orchestration_arm.yaml").read_text())
    settings["disciplines"]["offline-test"] = {
        "persona": "auto-coding",
        "tool_allowlist": ["file_read", "file_write", "pytest_run", "wiki_search"],
        "read_tools": ["file_read", "wiki_search"],
        "action_tools": ["file_write", "pytest_run"],
    }
    settings["calibration"]["minimum_pass_probability"] = 0.01
    settings["calibration"]["rates_by_discipline"] = {
        "offline-test": {
            "fast": {"pass_probability": 1.0, "mean_seconds": 1},
            "deep": {"pass_probability": 1.0, "mean_seconds": 1},
        }
    }
    config.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    engines = {
        "fast": Engine(
            SEAT_TAGS["fast"],
            fast_digest,
            pipeline.url,
            auth.PIPELINE_API_KEY,
            "omlx",
            "fake-fast",
        ),
        "deep": Engine(
            SEAT_TAGS["deep"],
            deep_digest,
            pipeline.url,
            auth.PIPELINE_API_KEY,
            "omlx",
            "fake-deep",
        ),
    }
    return ArmService(
        tmp_path / "tasks", engines, build_sha=build_sha, residency_config=config, notices=notices
    )


@pytest.mark.parametrize("shadow_outcome", ["pass", "disagree", "error", "timeout"])
def test_read_shadow_records_comparison_without_changing_gate(
    tmp_path: Path,
    fake_pipeline: FakePipeline,
    monkeypatch: pytest.MonkeyPatch,
    shadow_outcome: str,
) -> None:
    (tmp_path / "source.txt").write_text("source input\n", encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    arm = service(tmp_path, fake_pipeline)
    arm.arm_config["disciplines"]["offline-test"]["shadow_seats"] = {
        "read": {
            "model": "portal5/spark-x2.6:q4_K_M-ctx64k",
            "timeout_seconds": 5,
        }
    }

    def fake_shadow_run(*_args: Any, **_kwargs: Any) -> WorkerResult:
        if shadow_outcome == "error":
            raise RuntimeError("shadow engine failed")
        if shadow_outcome == "timeout":
            raise TimeoutError("shadow timeout")
        answer = "wrong" if shadow_outcome == "disagree" else "right"
        return WorkerResult(True, {"answer": answer}, 5, 0.1, "finished", (), ())

    def fake_popen(args: list[str], **_kwargs: Any) -> Mock:
        job_path = Path(json.loads(Path(args[-1]).read_text(encoding="utf-8"))[0])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        assert job["comparison"]["shadow_model"].endswith("spark-x2.6:q4_K_M-ctx64k")
        record = shadow_module.run_shadow(job, Mock(), Mock())  # type: ignore[arg-type]
        assert (
            Path(job["task_dir"]) / "bites/b1/attempts/01/shadow/data/inputs/source.txt"
        ).read_text() == "source input\n"
        shadow_module.append_comparison(Path(job["task_dir"]), record)
        return Mock()

    monkeypatch.setattr(shadow_module, "run_bite", fake_shadow_run)
    monkeypatch.setattr(service_module.subprocess, "Popen", fake_popen)
    task_dir = arm.submit(
        plan("shadow-read", bite(tools=["file_read"], inputs=["source.txt"])), tmp_path
    )
    receipt = json.loads((task_dir / "receipt.json").read_text(encoding="utf-8"))
    record = json.loads((task_dir / "shadow_comparisons.jsonl").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert record["incumbent_verdict"] is True
    assert record["kind"] == "read"
    assert isinstance(record["incumbent_latency_seconds"], float)
    assert isinstance(record["shadow_latency_seconds"], float)
    if shadow_outcome == "pass":
        assert record["shadow_verdict"] is True
        assert record["agree"] is True
        assert record["error"] is None
    elif shadow_outcome == "disagree":
        assert record["shadow_verdict"] is False
        assert record["agree"] is False
        assert record["error"] is None
    else:
        assert record["shadow_verdict"] is None
        assert record["agree"] is None
        assert (
            "shadow engine failed" if shadow_outcome == "error" else "shadow timeout"
        ) in record["error"]


def test_read_shadow_runs_once_for_a_bite_that_retries(
    tmp_path: Path,
    fake_pipeline: FakePipeline,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "source.txt").write_text("source input\n", encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "wrong"}))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    arm = service(tmp_path, fake_pipeline)
    arm.arm_config["disciplines"]["offline-test"]["shadow_seats"] = {
        "read": {"model": "portal5/spark-x2.6:q4_K_M-ctx64k", "timeout_seconds": 5}
    }

    def fake_shadow_run(*_args: Any, **_kwargs: Any) -> WorkerResult:
        return WorkerResult(True, {"answer": "right"}, 5, 0.1, "finished", (), ())

    def fake_popen(args: list[str], **_kwargs: Any) -> Mock:
        for job_path in json.loads(Path(args[-1]).read_text(encoding="utf-8")):
            job = json.loads(Path(job_path).read_text(encoding="utf-8"))
            shadow_module.append_comparison(
                Path(job["task_dir"]), shadow_module.run_shadow(job, Mock(), Mock())
            )
        return Mock()

    monkeypatch.setattr(shadow_module, "run_bite", fake_shadow_run)
    monkeypatch.setattr(service_module.subprocess, "Popen", fake_popen)
    task_dir = arm.submit(
        plan("shadow-retry", bite(tools=["file_read"], inputs=["source.txt"])), tmp_path
    )
    receipt = json.loads((task_dir / "receipt.json").read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (task_dir / "shadow_comparisons.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 2
    assert len(records) == 1
    assert records[0]["attempt"] == "02"
    assert records[0]["incumbent_verdict"] is True


def test_shadow_summary_counts_false_accept_and_false_fail(tmp_path: Path) -> None:
    task = tmp_path / "task-one"
    task.mkdir()
    for incumbent, candidate in ((True, True), (False, True), (True, False), (True, None)):
        shadow_module.append_comparison(
            task,
            {
                "incumbent_verdict": incumbent,
                "shadow_verdict": candidate,
                "agree": candidate == incumbent if candidate is not None else None,
                "error": "timeout" if candidate is None else None,
            },
        )
    assert shadow_module.summarize_comparisons(task) == {
        "total": 4,
        "compared": 3,
        "agree_percent": pytest.approx(100 / 3),
        "false_accept": 1,
        "false_fail": 1,
        "waited": 0,
        "errors": 1,
    }
    other = tmp_path / "task-two"
    other.mkdir()
    shadow_module.append_comparison(
        other,
        {"incumbent_verdict": True, "shadow_verdict": True, "agree": True, "error": None},
    )
    assert shadow_module.summarize_all(tmp_path) == {
        "total": 5,
        "compared": 4,
        "agree_percent": pytest.approx(50.0),
        "false_accept": 1,
        "false_fail": 1,
        "waited": 0,
        "errors": 1,
    }


def test_shadow_summary_separates_waited_from_errors(tmp_path: Path) -> None:
    task = tmp_path / "task-wait"
    task.mkdir()
    shadow_module.append_comparison(
        task,
        {
            "incumbent_verdict": True,
            "shadow_verdict": True,
            "agree": True,
            "error": None,
            "waited": True,
        },
    )
    shadow_module.append_comparison(
        task,
        {
            "incumbent_verdict": True,
            "shadow_verdict": None,
            "agree": None,
            "error": None,
            "waited": True,
        },
    )
    shadow_module.append_comparison(
        task,
        {
            "incumbent_verdict": True,
            "shadow_verdict": None,
            "agree": None,
            "error": "model failed",
            "waited": True,
        },
    )
    assert shadow_module.summarize_comparisons(task) == {
        "total": 3,
        "compared": 1,
        "agree_percent": 100.0,
        "false_accept": 0,
        "false_fail": 0,
        "waited": 3,
        "errors": 1,
    }


class _ScriptedEngine:
    """Load-plan and chat script. A missing later plan repeats the last one."""

    def __init__(self, plans: list[Any], chats: list[Any]) -> None:
        self._plans = list(plans)
        self._chats = list(chats)
        self._last_plan: Any = {"busy": False, "fits": True}
        self.plan_calls = 0
        self.chat_calls = 0
        self.model_tag = "shadow-model"

    def load_plan(self, _timeout: float) -> dict[str, Any]:
        self.plan_calls += 1
        item = self._plans.pop(0) if self._plans else self._last_plan
        if isinstance(item, Exception):
            raise item
        self._last_plan = item
        return item

    def chat(self, _body: dict[str, Any], _timeout: float, _on_event: Any) -> dict[str, Any]:
        self.chat_calls += 1
        item = self._chats.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _patch_shadow_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    state = {"now": 0.0}
    slept: list[float] = []

    def monotonic() -> float:
        return state["now"]

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(shadow_module.time, "monotonic", monotonic)
    monkeypatch.setattr(shadow_module.time, "sleep", sleep)
    return slept


def _shadow_job(tmp_path: Path, *, wait_seconds: float = 30) -> dict[str, Any]:
    task_dir = tmp_path / "task"
    source = task_dir / "source-data"
    source.mkdir(parents=True)
    parsed = parse_plan(plan("shadow-wait", bite())).bites[0]
    return {
        "bite": parsed.as_dict(),
        "inputs": {},
        "comparison": {
            "task_id": "shadow-wait",
            "bite_id": parsed.bite_id,
            "attempt": "01",
            "incumbent_latency_seconds": 1.0,
            "incumbent_verdict": True,
            "shadow_model": "portal5/spark-x2.6:q4_K_M-ctx64k",
        },
        "timeout_seconds": 90,
        "config": {
            "shadow_slot_wait_seconds": wait_seconds,
            "review": {
                "high_risk": {
                    "risk_levels": ["high"],
                    "tools": ["file_write"],
                    "write_scopes": ["outside_task"],
                }
            },
        },
        "task_dir": str(task_dir),
        "source_data": str(source),
    }


def test_shadow_waits_out_busy_load_plan_then_compares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept = _patch_shadow_clock(monkeypatch)
    busy = {"busy": True, "fits": True}
    free = {"busy": False, "fits": True}
    engine = _ScriptedEngine([busy, busy, busy, free], [finish_response({"answer": "right"})])
    record = shadow_module.run_shadow(_shadow_job(tmp_path), engine, Mock())  # type: ignore[arg-type]
    assert record["error"] is None
    assert record["shadow_verdict"] is True
    assert record["agree"] is True
    assert record["waited"] is True
    assert record["wait_seconds"] == pytest.approx(7.0)
    assert slept == [1.0, 2.0, 4.0]
    assert engine.chat_calls == 1
    assert engine.plan_calls >= 4


def test_shadow_honours_retry_after_on_429(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slept = _patch_shadow_clock(monkeypatch)
    free = {"busy": False, "fits": True}
    limited = PipelineError(
        "HTTPStatusError: 429 Too Many Requests", status_code=429, retry_after=2.5
    )
    engine = _ScriptedEngine([free], [limited, finish_response({"answer": "right"})])
    record = shadow_module.run_shadow(_shadow_job(tmp_path), engine, Mock())  # type: ignore[arg-type]
    assert record["error"] is None
    assert record["shadow_verdict"] is True
    assert record["waited"] is True
    assert slept == [2.5]
    assert engine.chat_calls == 2


def test_shadow_load_plan_429_waits_for_retry_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept = _patch_shadow_clock(monkeypatch)
    limited = PipelineError(
        "load-plan failed: HTTPStatusError: 429 Too Many Requests",
        status_code=429,
        retry_after=4,
    )
    engine = _ScriptedEngine(
        [limited, {"busy": False, "fits": True}], [finish_response({"answer": "right"})]
    )
    record = shadow_module.run_shadow(_shadow_job(tmp_path), engine, Mock())  # type: ignore[arg-type]
    assert record["error"] is None
    assert record["shadow_verdict"] is True
    assert record["waited"] is True
    assert slept == [4.0]


def test_shadow_wait_cap_is_not_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_shadow_clock(monkeypatch)
    engine = _ScriptedEngine([{"busy": True, "fits": True}], [])
    record = shadow_module.run_shadow(_shadow_job(tmp_path, wait_seconds=3), engine, Mock())  # type: ignore[arg-type]
    assert record["error"] is None
    assert record["shadow_verdict"] is None
    assert record["agree"] is None
    assert record["waited"] is True
    assert engine.chat_calls == 0


def test_shadow_model_error_after_admission_is_an_error(tmp_path: Path) -> None:
    engine = _ScriptedEngine([{"busy": False, "fits": True}], [PipelineError("model exploded")])
    record = shadow_module.run_shadow(_shadow_job(tmp_path), engine, Mock())  # type: ignore[arg-type]
    assert record["waited"] is False
    assert "model exploded" in str(record["error"])


def test_load_plan_429_keeps_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "http://pipeline/admin/load-plan")
    response = httpx.Response(429, headers={"Retry-After": "7"}, request=request)

    def post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return response

    monkeypatch.setattr(httpx, "post", post)
    engine = Engine(
        "seat",
        "digest",
        "http://pipeline",
        load_plan_model="portal5/spark-x2.6:q4_K_M-ctx64k",
    )
    with pytest.raises(PipelineError) as caught:
        engine.load_plan(5)
    assert caught.value.status_code == 429
    assert caught.value.retry_after == 7.0
    assert str(caught.value).startswith("load-plan failed: HTTPStatusError:")


def test_job_memory_plan_and_reclaim_use_pipeline_admin_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    responses = [
        httpx.Response(
            200,
            json={"idle_ollama_gib": 4, "freeable_omlx_gib": 3},
            request=httpx.Request("POST", "http://pipeline/admin/load-plan"),
        ),
        httpx.Response(
            200,
            json={"unloads": [{"engine": "omlx", "model": "idle", "status": "unloaded"}]},
            request=httpx.Request("POST", "http://pipeline/admin/reclaim-idle"),
        ),
    ]

    def post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append((url, kwargs["json"]))
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", post)
    engine = Engine("seat", "digest", "http://pipeline/v1", api_key="key")

    plan = engine.memory_plan(5)
    unloads = engine.reclaim_idle_memory(5, timeout=15)

    assert plan["idle_ollama_gib"] + plan["freeable_omlx_gib"] == 7
    assert unloads == [{"engine": "omlx", "model": "idle", "status": "unloaded"}]
    assert calls == [
        ("http://pipeline/admin/load-plan", {"models": []}),
        ("http://pipeline/admin/reclaim-idle", {"need_gib": 5}),
    ]


def test_arm_config_rejects_non_positive_shadow_wait(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((repo / "config" / "orchestration_arm.yaml").read_text())
    config["shadow_slot_wait_seconds"] = 0
    path = tmp_path / "orchestration_arm.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="shadow_slot_wait_seconds"):
        load_arm_config(path)


@pytest.mark.parametrize(
    "shadow",
    [
        {"browse": {"model": "portal5/spark-x2.6:q4_K_M-ctx64k", "timeout_seconds": 5}},
        {"read": {"model": "spark-x2.6:q4_K_M-ctx64k", "timeout_seconds": 5}},
        {"read": {"model": "portal5/spark-x2.6:q4_K_M-ctx64k", "timeout_seconds": 0}},
    ],
)
def test_arm_config_rejects_invalid_shadow_seat(tmp_path: Path, shadow: dict[str, Any]) -> None:
    repo = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((repo / "config" / "orchestration_arm.yaml").read_text())
    config["disciplines"]["test_fixing"]["shadow_seats"] = shadow
    path = tmp_path / "orchestration_arm.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="shadow_seats"):
        load_arm_config(path)


def test_shadow_kind_uses_discipline_read_tools() -> None:
    discipline = {"read_tools": ["file_read", "wiki_search"]}
    read_bite = parse_plan(plan("kind", bite(tools=["file_read", "wiki_search"]))).bites[0]
    file_read_bite = parse_plan(plan("kind", bite(tools=["file_read"]))).bites[0]
    check_bite = parse_plan(plan("kind", bite(tools=[]))).bites[0]
    write_bite = parse_plan(
        plan("kind", bite(tools=["file_write"], write_paths=["new.txt"]))
    ).bites[0]
    assert ArmService._shadow_kind(read_bite, discipline) == "read"
    assert ArmService._shadow_kind(file_read_bite, {}) == "read"
    assert ArmService._shadow_kind(check_bite, discipline) == "check"
    assert ArmService._shadow_kind(write_bite, discipline) is None


def test_shadow_client_pins_spark_with_card_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class EmptyResponse:
        def __enter__(self) -> EmptyResponse:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self) -> list[str]:
            return []

    def fake_stream(_method: str, url: str, **kwargs: Any) -> EmptyResponse:
        seen["url"] = url
        seen["body"] = kwargs["json"]
        return EmptyResponse()

    monkeypatch.setattr(httpx, "stream", fake_stream)
    model = "portal5/spark-x2.6:q4_K_M-ctx64k"
    engine = shadow_module.ShadowEngine(
        "auto-daily::gemma-fast", "shadow", "http://pipeline", model_override=model
    )
    engine.chat({"model": engine.model_tag}, 5, lambda _event: None)
    assert parse_qs(urlsplit(seen["url"]).query)["model"] == [model]
    assert seen["body"] == {
        "model": "auto-daily::gemma-fast",
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": -1,
        "min_p": 0.0,
    }


@pytest.fixture
def fake_pipeline():
    server = FakePipeline()
    try:
        yield server
    finally:
        server.close()


def test_happy_path_uses_one_pipeline_port_and_guarded_model_seat(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_dir = service(tmp_path, fake_pipeline).submit(plan("happy", bite()), tmp_path)
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 1
    assert {row["state"] for row in _events(task_dir)} >= {
        "pending",
        "ready",
        "running",
        "checking",
        "passed",
    }
    assert all(row["build_sha"] == "head-a" for row in _events(task_dir))
    assert len(fake_pipeline.requests) == 1
    request = fake_pipeline.requests[0]
    assert request["model"] == SEAT_TAGS["fast"]
    assert request["portal_bite_persona"] == "auto-coding"
    assert request["portal_bite_tools"] == ["finish"]
    assert request["tools"][-1]["function"]["name"] == "finish"
    finish_parameters = request["tools"][-1]["function"]["parameters"]
    assert finish_parameters["required"] == ["output"]
    assert "output_path" not in finish_parameters["properties"]
    assert (task_dir / "data/bites/b1/output.json").is_file()
    assert fake_pipeline.admin_requests == [{"models": [{"engine": "omlx", "model": "fake-fast"}]}]


def test_detection_engineering_template_validates_and_runs_offline(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    repo = Path(__file__).resolve().parents[2]
    arm_config = yaml.safe_load((repo / "config/orchestration_arm.yaml").read_text())
    detection = arm_config["disciplines"]["detection-engineering"]
    assert detection["seating_status"] == "seated"
    assert detection["seated_models"]["fast"] == "auto-daily::gemma-fast"
    assert "detection-engineering" in arm_config["calibration"]["rates_by_discipline"]
    arm_config["calibration"]["minimum_pass_probability"] = 0.01
    config_path = tmp_path / "orchestration_arm.yaml"
    config_path.write_text(yaml.safe_dump(arm_config, sort_keys=False), encoding="utf-8")
    reference = tmp_path / "reference.spl"
    reference.write_text("index=portal5_lab EventCode=4769\n", encoding="utf-8")
    task_plan = instantiate_plan_template(
        arm_config,
        template_key="author_and_validate_detection",
        discipline_key="detection-engineering",
        task_id="detection-offline",
        parameters={
            "reference_file": reference.name,
            "technique": "T1110.001",
            "expected_behavior": "finds repeated authentication failures",
        },
        source_dir=tmp_path,
    )
    assert task_plan.bites[0].reads_untrusted
    assert task_plan.bites[0].tools == (
        "file_read",
        "mitre_technique_lookup",
        "mitre_data_sources_for_technique",
        "spl_search_library",
    )
    assert task_plan.bites[1].tools == ("file_write", "spl_validate_syntax")

    fake_pipeline.add("fast", finish_response("Finding: T1110.001; authentication telemetry"))
    fake_pipeline.add("fast", finish_response("PASS: exact SPL passed syntax validation"))
    for reason in ("artifact is valid", "mapping is complete", "scope is safe"):
        fake_pipeline.add(
            "deep",
            text_response(json.dumps({"decision": "approve", "reason": reason})),
        )
    fake_pipeline.add("fast", finish_response("PASS: detection and operational notes assembled"))
    fake_pipeline.add("deep", finish_response("PASS: final detection and evidence reviewed"))
    engines = {
        "fast": Engine(
            SEAT_TAGS["fast"],
            "fast-digest",
            fake_pipeline.url,
            auth.PIPELINE_API_KEY,
            "omlx",
            "fake-fast",
        ),
        "deep": Engine(
            SEAT_TAGS["deep"],
            "deep-digest",
            fake_pipeline.url,
            auth.PIPELINE_API_KEY,
            "omlx",
            "fake-deep",
        ),
    }
    notices = Mock(spec=StubNoticeSink)
    notices.approval.return_value = True
    arm = ArmService(
        tmp_path / "tasks",
        engines,
        build_sha="detection-offline-build",
        residency_config=config_path,
        notices=notices,
    )

    # Seated 2026-10-28: detection-engineering now carries WFE rates, so the unattended
    # missing-rates refusal no longer applies; the attended offline run below is unchanged.
    arm.arm_config["calibration"]["minimum_pass_probability"] = None
    task_dir = arm.submit(task_plan.as_dict(), tmp_path, unattended=False)

    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert len(receipt["results"]) == 4
    assert notices.approval.call_count == 1
    assert [
        request["portal_bite_tools"]
        for request in fake_pipeline.requests
        # Review votes are tool-less bite requests ([]); this lists the task bites' scopes.
        if request.get("portal_bite_tools")
    ] == [
        [
            "file_read",
            "mitre_technique_lookup",
            "mitre_data_sources_for_technique",
            "spl_search_library",
            "finish",
        ],
        ["file_write", "spl_validate_syntax", "finish"],
        ["finish"],
        ["finish"],
    ]
    assert [request["model"] for request in fake_pipeline.requests] == [
        SEAT_TAGS["fast"],
        SEAT_TAGS["fast"],
        SEAT_TAGS["deep"],
        SEAT_TAGS["deep"],
        SEAT_TAGS["deep"],
        SEAT_TAGS["fast"],
        SEAT_TAGS["deep"],
    ]
    assert all(
        request["portal_bite_persona"] == "splunkdetectionauthor"
        for request in fake_pipeline.requests
    )


def test_bite_tools_are_sent_as_a_strict_pipeline_allowlist(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    service(tmp_path, fake_pipeline).submit(plan("scope", bite(tools=["wiki_search"])), tmp_path)
    assert fake_pipeline.requests[0]["portal_bite_tools"] == ["wiki_search", "finish"]
    assert [tool["function"]["name"] for tool in fake_pipeline.requests[0]["tools"]] == [
        "wiki_search",
        "finish",
    ]
    assert fake_pipeline.requests[0]["model"] == SEAT_TAGS["fast"]


def test_client_file_tools_loop_back_to_the_model_and_keep_reading_bites_read_only(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "client-loop"
    task_dir.mkdir()
    (task_dir / "data").mkdir()
    (task_dir / "data/source.txt").write_text("source contents", encoding="utf-8")
    fake_pipeline.add("fast", tool_response("file_read", '{"path":"source.txt"}'))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = parse_plan(
        plan("client-loop", bite(tools=["file_read"], inputs=["source.txt"]))
    ).bites[0]
    result = run_bite(
        task_dir,
        task_bite,
        Engine(
            SEAT_TAGS["fast"],
            "test-digest",
            fake_pipeline.url,
            auth.PIPELINE_API_KEY,
        ),
        input_paths={"source.txt": Path("source.txt")},
        attempt_dir=task_dir / "attempt",
    )

    assert result.finished
    assert [request["portal_bite_max_hops"] for request in fake_pipeline.requests] == [2, 1]
    assert all(
        [tool["function"]["name"] for tool in request["tools"]] == ["file_read", "finish"]
        for request in fake_pipeline.requests
    )
    assert all("chat_template_kwargs" not in request for request in fake_pipeline.requests)
    assert all(
        "Keep reasoning enabled" not in request["messages"][0]["content"]
        for request in fake_pipeline.requests
    )
    followup = fake_pipeline.requests[1]["messages"]
    assert followup[-1]["role"] == "tool"
    assert followup[-1]["name"] == "file_read"
    assert followup[-1]["content"] == "source contents"


def test_action_bite_prompt_contains_read_only_snapshots_without_file_read(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "action-snapshot"
    (task_dir / "data").mkdir(parents=True)
    (task_dir / "data/source.py").write_text("def clamp(value): return value\n", encoding="utf-8")
    (task_dir / "data/test_source.py").write_text("assert clamp(2) == 2\n", encoding="utf-8")
    (task_dir / "data/staged.py").write_text("original = 'keep this context'\n", encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = parse_plan(
        plan(
            "action-snapshot",
            bite(
                tools=["file_write", "pytest_run"],
                inputs=["source.py", "test_source.py"],
                write_paths=["source.py", "staged.py"],
            ),
        )
    ).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={
            "source.py": Path("source.py"),
            "test_source.py": Path("test_source.py"),
        },
        attempt_dir=task_dir / "attempt",
    )

    assert result.finished
    request = fake_pipeline.requests[0]
    assert request["portal_bite_tools"] == ["file_write", "pytest_run", "finish"]
    assert "read-only snapshots" in request["messages"][0]["content"]
    assert "no file_read tool" in request["messages"][0]["content"]
    user_content = request["messages"][1]["content"]
    assert "def clamp(value): return value" in user_content
    assert "assert clamp(2) == 2" in user_content
    assert "original = 'keep this context'" in user_content
    assert "staged copy: source.py" in user_content


def test_action_bite_snapshot_truncates_to_its_context_budget(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "action-snapshot-truncated"
    (task_dir / "data").mkdir(parents=True)
    content = "value = 1\n" + ("# extra source material\n" * 2_000)
    (task_dir / "data/source.py").write_text(content, encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = parse_plan(
        plan(
            "action-snapshot-truncated",
            bite(
                tools=["file_write"],
                inputs=["source.py"],
                write_paths=["source.py"],
                context_tokens=2048,
                output_tokens=128,
            ),
        )
    ).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={"source.py": Path("source.py")},
        attempt_dir=task_dir / "attempt",
    )

    assert result.finished
    request = fake_pipeline.requests[0]
    user_content = request["messages"][1]["content"]
    assert "value = 1" in user_content
    assert "[TRUNCATED: input snapshot clipped to fit the bite context budget]" in user_content
    prompt_bytes = sum(
        len(message["content"].encode("utf-8")) for message in request["messages"]
    ) + len(json.dumps(request["tools"]).encode("utf-8"))
    assert prompt_bytes <= (2048 - 128 - 512) * 3


def test_finish_ignores_model_output_path_and_records_the_worker_path(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "finish-output-path"
    wrong_path = "bites/b1/defect_report.txt"
    fake_pipeline.add("fast", finish_response({"answer": "right"}, path=wrong_path))
    task_bite = parse_plan(plan("finish-output-path", bite())).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={},
        attempt_dir=task_dir / "attempt",
    )

    output_file = task_dir / "data" / task_bite.output_path
    assert result.finished
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"answer": "right"}
    assert not list(task_dir.rglob("defect_report.txt"))
    records = [
        json.loads(line)
        for line in (task_dir / "attempt" / "transcript.jsonl").read_text().splitlines()
    ]
    finish_record = next(row for row in records if row["kind"] == "result")
    assert finish_record["worker_output_path"] == task_bite.output_path
    assert finish_record["ignored_model_output_path"] == wrong_path


def test_client_tool_loop_honors_the_hop_limit_before_executing_a_last_hop_action(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "hop-limit"
    task_dir.mkdir()
    fake_pipeline.add("fast", tool_response("file_write", '{"path":"new.txt","content":"x"}'))
    raw_bite = bite(tools=["file_write"])
    raw_bite["budget"]["turns"] = 1
    task_bite = parse_plan(plan("hop-limit", raw_bite)).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(
            SEAT_TAGS["fast"],
            "test-digest",
            fake_pipeline.url,
            auth.PIPELINE_API_KEY,
        ),
        input_paths={},
        attempt_dir=task_dir / "attempt",
    )

    assert result.loop_outcome == "hop_limit_exhausted"
    assert result.red_flags == ("hop_limit_exhausted",)
    assert not (task_dir / "data/new.txt").exists()
    assert fake_pipeline.requests[0]["portal_bite_max_hops"] == 1


def test_parallel_file_reads_execute_in_order_and_continue_to_finish(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "parallel-reads"
    (task_dir / "data").mkdir(parents=True)
    (task_dir / "data/first.txt").write_text("first contents", encoding="utf-8")
    (task_dir / "data/second.txt").write_text("second contents", encoding="utf-8")
    fake_pipeline.add(
        "fast",
        parallel_tool_response(
            ("file_read", '{"path":"first.txt"}'),
            ("file_read", '{"path":"second.txt"}'),
        ),
    )
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = parse_plan(
        plan(
            "parallel-reads",
            bite(tools=["file_read"], inputs=["first.txt", "second.txt"], turns=3),
        )
    ).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={"first.txt": Path("first.txt"), "second.txt": Path("second.txt")},
        attempt_dir=task_dir / "attempt",
    )

    assert result.finished
    assert [item["output"] for item in result.tool_results] == [
        "first contents",
        "second contents",
    ]
    assert [request["portal_bite_max_hops"] for request in fake_pipeline.requests] == [3, 1]
    exchange = fake_pipeline.requests[1]["messages"][-3:]
    assert [call["id"] for call in exchange[0]["tool_calls"]] == ["call-1", "call-2"]
    assert [message["tool_call_id"] for message in exchange[1:]] == ["call-1", "call-2"]


def test_parallel_batch_mixing_finish_defers_it_and_executes_the_tools(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "mixed-defer"
    (task_dir / "data").mkdir(parents=True)
    (task_dir / "data/source.txt").write_text("source contents", encoding="utf-8")
    fake_pipeline.add(
        "fast",
        parallel_tool_response(
            ("file_read", '{"path":"source.txt"}'),
            ("finish", '{"output":{"answer":"decided before the results"}}'),
        ),
    )
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = parse_plan(
        plan(
            "mixed-defer",
            bite(tools=["file_read"], inputs=["source.txt"], turns=3),
        )
    ).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={"source.txt": Path("source.txt")},
        attempt_dir=task_dir / "attempt",
    )
    records = [
        json.loads(line)
        for line in (task_dir / "attempt" / "transcript.jsonl").read_text().splitlines()
    ]

    assert result.finished and result.output == {"answer": "right"}
    assert result.red_flags == ()
    assert [item["name"] for item in result.tool_results] == ["file_read"]
    assert [call["function"]["name"] for call in result.tool_calls] == ["file_read", "finish"]
    deferred = [row for row in records if row["kind"] == "finish_deferred"]
    assert [row["call"]["function"]["name"] for row in deferred] == ["finish"]
    assert "decided before the results" in deferred[0]["call"]["function"]["arguments"]
    # The dropped finish costs no hop: the follow-up request keeps one spare.
    assert [request["portal_bite_max_hops"] for request in fake_pipeline.requests] == [3, 2]
    followup = fake_pipeline.requests[1]["messages"][-3:]
    assert [call["function"]["name"] for call in followup[0]["tool_calls"]] == ["file_read"]
    assert followup[1]["role"] == "tool" and followup[1]["content"] == "source contents"
    assert followup[2]["role"] == "user" and "finish" in followup[2]["content"]


def test_parallel_batch_with_unoffered_tool_keeps_red_flags(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "mixed-unoffered"
    (task_dir / "data").mkdir(parents=True)
    (task_dir / "data/source.txt").write_text("source contents", encoding="utf-8")
    fake_pipeline.add(
        "fast",
        parallel_tool_response(
            ("shell_exec", '{"command":"rm -rf /"}'),
            ("finish", '{"output":{"answer":"right"}}'),
        ),
    )
    task_bite = parse_plan(
        plan("mixed-unoffered", bite(tools=["file_read"], inputs=["source.txt"]))
    ).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={"source.txt": Path("source.txt")},
        attempt_dir=task_dir / "attempt",
    )
    records = [
        json.loads(line)
        for line in (task_dir / "attempt" / "transcript.jsonl").read_text().splitlines()
    ]

    assert not result.finished
    assert "multiple_tool_calls" in result.red_flags
    assert "missing_finish_output" in result.red_flags
    assert result.tool_results == ()
    assert not [row for row in records if row["kind"] == "finish_deferred"]
    assert len(fake_pipeline.requests) == 1


def test_parallel_batch_over_hop_budget_is_rejected_before_tool_execution(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_dir = tmp_path / "parallel-hop-limit"
    (task_dir / "data").mkdir(parents=True)
    (task_dir / "data/first.txt").write_text("first", encoding="utf-8")
    (task_dir / "data/second.txt").write_text("second", encoding="utf-8")
    fake_pipeline.add(
        "fast",
        parallel_tool_response(
            ("file_read", '{"path":"first.txt"}'),
            ("file_read", '{"path":"second.txt"}'),
        ),
    )
    task_bite = parse_plan(
        plan(
            "parallel-hop-limit",
            bite(tools=["file_read"], inputs=["first.txt", "second.txt"], turns=2),
        )
    ).bites[0]

    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={"first.txt": Path("first.txt"), "second.txt": Path("second.txt")},
        attempt_dir=task_dir / "attempt",
    )

    assert result.loop_outcome == "hop_limit_exhausted"
    assert result.red_flags == ("hop_limit_exhausted",)
    assert result.tool_results == ()


def test_fake_pipeline_drops_server_side_tools_without_client_schemas() -> None:
    finish_schema = {"type": "function", "function": {"name": "finish"}}
    read_schema = {"type": "function", "function": {"name": "file_read"}}
    missing_schema = {
        "portal_bite_tools": ["file_read", "finish"],
        "tools": [finish_schema],
    }
    client_schemas = {
        "portal_bite_tools": ["file_read", "finish"],
        "tools": [read_schema, finish_schema],
    }

    pipeline = FakePipeline(pipeline_tools=set())
    try:
        assert pipeline._tools_offered(missing_schema) == ["finish"]
        assert pipeline._tools_offered(client_schemas) == ["file_read", "finish"]
    finally:
        pipeline.close()


def test_task_tools_confine_paths_and_enforce_size_limits(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    (task_dir / "escape").symlink_to(outside)
    tools = TaskToolExecutor(task_dir, ("file_read", "file_write"), writable_paths=("safe.txt",))

    assert tools.dispatch("file_read", {"path": "../outside.txt"}).startswith("ERROR:")
    assert tools.dispatch("file_read", {"path": str(outside)}).startswith("ERROR:")
    assert tools.dispatch("file_read", {"path": "escape"}).startswith("ERROR:")
    assert tools.dispatch(
        "file_write", {"path": "../outside.txt", "content": "changed"}
    ).startswith("ERROR:")
    assert tools.dispatch(
        "file_write", {"path": "large.txt", "content": "x" * (FILE_WRITE_LIMIT + 1)}
    ).startswith("ERROR:")
    (task_dir / "large-read.txt").write_bytes(b"x" * (FILE_READ_LIMIT + 1))
    assert tools.dispatch("file_read", {"path": "large-read.txt"}).startswith("ERROR:")
    assert outside.read_text(encoding="utf-8") == "private"


@pytest.mark.parametrize("operation", ["read", "write"])
def test_task_tools_resist_parent_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    task_dir = tmp_path / "task"
    safe_dir = task_dir / "safe"
    outside_dir = tmp_path / "outside"
    safe_dir.mkdir(parents=True)
    outside_dir.mkdir()
    (safe_dir / "target.txt").write_text("inside", encoding="utf-8")
    (outside_dir / "target.txt").write_text("outside", encoding="utf-8")
    tools = TaskToolExecutor(
        task_dir,
        ("file_read", "file_write"),
        readable_paths=("safe/target.txt",),
        writable_paths=("safe/target.txt",),
    )
    real_open = os.open
    swapped = False

    def racing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        is_final_write = bool(flags & os.O_WRONLY)
        if path == "target.txt" and not swapped and (operation == "read" or is_final_write):
            safe_dir.rename(task_dir / "contained")
            safe_dir.symlink_to(outside_dir, target_is_directory=True)
            swapped = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", racing_open)

    if operation == "read":
        assert tools.file_read("safe/target.txt") == "inside"
    else:
        assert tools.file_write("safe/target.txt", "changed") == "wrote 7 chars to safe/target.txt"
        assert (task_dir / "contained/target.txt").read_text(encoding="utf-8") == "changed"
    assert swapped
    assert (outside_dir / "target.txt").read_text(encoding="utf-8") == "outside"


def test_task_tools_cannot_write_control_plane_files(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "data"
    data_dir.mkdir(parents=True)
    control_plan = task_dir / "plan.json"
    control_plan.write_text('{"trusted": true}\n', encoding="utf-8")
    tools = TaskToolExecutor(data_dir, ("file_write",), writable_paths=("plan.json",))

    assert tools.file_write("plan.json", "model data") == "wrote 10 chars to plan.json"
    assert control_plan.read_text(encoding="utf-8") == '{"trusted": true}\n'
    assert (data_dir / "plan.json").read_text(encoding="utf-8") == "model data"


def test_task_tools_enforce_a_cumulative_data_quota(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "padding.bin").write_bytes(b"x" * TASK_BYTES_LIMIT)
    tools = TaskToolExecutor(task_dir, ("file_write",), writable_paths=("safe.txt",))

    assert "task data exceeds" in tools.file_write("safe.txt", "x")
    assert not (task_dir / "safe.txt").exists()


def test_task_tools_enforce_a_cumulative_file_quota(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    for index in range(TASK_FILE_LIMIT):
        (task_dir / f"existing-{index}.txt").touch()
    tools = TaskToolExecutor(task_dir, ("file_write",), writable_paths=("safe.txt",))

    with pytest.raises(ValueError, match="file limit"):
        tools.file_write("safe.txt", "x")
    assert not (task_dir / "safe.txt").exists()


def test_pytest_copyback_uses_the_exact_write_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "module.py").write_text("value = 1\n", encoding="utf-8")

    def fake_request(_url: str, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "exit_code": 0,
            "stdout": "1 passed\n",
            "stderr": "",
            "files": {"test_module.py": base64.b64encode(b"tampered\n").decode("ascii")},
        }

    monkeypatch.setattr(orchestration_tools, "_sandbox_request", fake_request)
    tools = TaskToolExecutor(
        task_dir,
        ("pytest_run",),
        readable_paths=("module.py",),
        writable_paths=("module.py",),
    )

    result = tools.pytest_run()

    assert "copy-back rejected" in result
    assert not (task_dir / "test_module.py").exists()


def test_orchestration_pytest_uses_the_locked_down_dind_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    class Process:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b'{"exit_code":0,"stdout":"1 passed","stderr":"","files":{}}', b""

    async def fake_exec(*command: str, **_kwargs: Any) -> Process:
        captured.extend(command)
        return Process()

    monkeypatch.setattr(sandbox_mcp, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sandbox_mcp.asyncio, "create_subprocess_exec", fake_exec)
    payload = {
        "files": {"test_sample.py": base64.b64encode(b"def test_ok(): pass\n").decode()},
        "selectors": ["test_sample.py"],
        "write_paths": [],
        "timeout": 10,
    }

    result = asyncio.run(sandbox_mcp._run_orchestration_pytest(payload))

    command = " ".join(captured)
    assert result["exit_code"] == 0
    assert "--network none" in command
    assert "--memory 256m" in command
    assert "--cpus 0.5" in command
    assert "--pids-limit 64" in command
    assert "--read-only" in captured
    assert captured[captured.index("--user") + 1] == "65534:65534"
    assert captured[captured.index("--cap-drop") + 1] == "ALL"
    assert "--cap-add" not in captured
    assert "/workspace" not in command
    assert "PYTHONPATH" not in command
    assert "os.environ" not in sandbox_mcp._PYTEST_RUNNER
    assert "os.chown" not in sandbox_mcp._PYTEST_RUNNER
    assert "preexec_fn" not in sandbox_mcp._PYTEST_RUNNER
    assert "os.getuid() != 65534" in sandbox_mcp._PYTEST_RUNNER


def test_orchestration_pytest_timeout_removes_the_whole_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[tuple[str, ...]] = []

    class TimedOut:
        returncode = None
        calls = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError
            return b"", b""

        def kill(self) -> None:
            return None

    class Cleanup:
        async def wait(self) -> int:
            return 0

    async def fake_exec(*command: str, **_kwargs: Any) -> Any:
        commands.append(command)
        return TimedOut() if len(commands) == 1 else Cleanup()

    monkeypatch.setattr(sandbox_mcp, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sandbox_mcp.asyncio, "create_subprocess_exec", fake_exec)
    payload = {"files": {}, "selectors": [], "write_paths": [], "timeout": 1}

    result = asyncio.run(sandbox_mcp._run_orchestration_pytest(payload))

    assert result["timed_out"] is True
    assert commands[1][:3] == ("docker", "rm", "-f")


def test_pytest_run_is_limited_to_local_tests_and_uses_container_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = tmp_path / "pytest-task"
    task_dir.mkdir()
    (task_dir / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (task_dir / "undeclared-secret.txt").write_text("not for this bite\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    def fake_run(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        return {"exit_code": 0, "stdout": "1 passed\n", "stderr": "", "files": {}}

    monkeypatch.setattr(orchestration_tools, "_sandbox_request", fake_run)
    tools = TaskToolExecutor(task_dir, ("pytest_run",), readable_paths=("test_sample.py",))
    result = tools.dispatch("pytest_run", {"args": "test_sample.py"})

    assert "exit_code=0" in result and "1 passed" in result
    assert captured["url"] == "http://127.0.0.1:8914"
    assert captured["payload"]["timeout"] == PYTEST_TIMEOUT_SECONDS
    assert set(captured["payload"]["files"]) == {"test_sample.py"}
    assert tools.dispatch("pytest_run", {"args": "../outside.py"}).startswith("ERROR:")
    assert tools.dispatch("pytest_run", {"args": "--confcutdir=/"}).startswith("ERROR:")


def test_worker_sends_input_paths_without_packing_file_contents(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    (tmp_path / "source.txt").write_text("complete source text", encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = bite(inputs=["source.txt"], tools=["file_read"])
    task_dir = service(tmp_path, fake_pipeline).submit(plan("input-read", task_bite), tmp_path)
    request = fake_pipeline.requests[0]
    messages = request["messages"]
    source = json.loads(messages[1]["content"])["inputs"]["source.txt"]
    # Source layout survives staging so sibling modules still import each other.
    assert source["path"] == "inputs/source.txt"
    assert (task_dir / "data" / source["path"]).read_text(
        encoding="utf-8"
    ) == "complete source text"
    assert "complete source text" not in json.dumps(messages)


def test_toolless_bite_gets_its_inputs_as_snapshots(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    # A final review has no file tools; without snapshots it cannot see what it reviews.
    (tmp_path / "source.txt").write_text("complete source text", encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    service(tmp_path, fake_pipeline).submit(plan("toolless", bite(inputs=["source.txt"])), tmp_path)
    messages = fake_pipeline.requests[0]["messages"]
    assert "complete source text" in messages[1]["content"]
    assert "do not call one" in messages[0]["content"]


def test_submit_rejects_tools_outside_the_discipline_allowlist(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    with pytest.raises(ValueError, match="tool outside discipline allowlist"):
        service(tmp_path, fake_pipeline).submit(
            plan("raw-tool", bite(tools=["send_message"])), tmp_path
        )
    assert not (tmp_path / "tasks/raw-tool").exists()


def test_submit_rejects_absolute_inputs_outside_the_source_root(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    outside = tmp_path.parent / "arm-outside.txt"
    outside.write_text("host data", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="input path escapes source directory"):
            service(tmp_path, fake_pipeline).submit(
                plan("raw-input", bite(tools=["file_read"], inputs=[str(outside)])),
                tmp_path,
            )
    finally:
        outside.unlink()
    assert not (tmp_path / "tasks/raw-input").exists()


def test_queue_rejects_unvalidated_raw_plan(tmp_path: Path) -> None:
    with (
        QueueLedger(tmp_path / "tasks") as ledger,
        pytest.raises(TypeError, match="policy-validated TaskPlan"),
    ):
        ledger.enqueue(plan("raw-queue", bite()), tmp_path)  # type: ignore[arg-type]


def test_absent_bite_scope_preserves_existing_pipeline_tools() -> None:
    body = {"tools": [{"function": {"name": "client_lookup"}}]}
    tools = ["wiki_search", "document_read"]
    actual, allowed = apply_bite_tool_scope(body, tools)
    assert actual is tools
    assert allowed is None
    assert body == {"tools": [{"function": {"name": "client_lookup"}}]}


def test_bite_scope_intersects_mcp_tools_and_filters_client_tools() -> None:
    body = {
        "portal_bite_tools": ["wiki_search", "finish"],
        "tools": [
            {"function": {"name": "finish"}},
            {"function": {"name": "not_allowed"}},
        ],
    }
    actual, allowed = apply_bite_tool_scope(body, ["wiki_search", "document_read"])
    assert actual == ["wiki_search"]
    assert allowed == {"wiki_search", "finish"}
    assert body == {"tools": [{"function": {"name": "finish"}}]}


def test_malformed_bite_scope_is_rejected() -> None:
    with pytest.raises(HTTPException) as caught:
        apply_bite_tool_scope({"portal_bite_tools": "wiki_search"}, ["wiki_search"])
    assert "portal_bite_tools" in str(caught.value.detail)


def test_refusal_red_flag_is_discarded_then_retried(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", finish_response("I cannot help with this request."))
    fake_pipeline.add("fast", finish_response("right"))
    task_bite = bite()
    task_bite["output"] = {"path": "bites/b1/output.txt", "file_type": "text"}
    task_bite["accept"] = [{"type": "contains", "value": "right"}]
    task_dir = service(tmp_path, fake_pipeline).submit(plan("redflag", task_bite), tmp_path)
    receipt = json.loads((task_dir / "receipt.json").read_text())
    checks = json.loads((task_dir / "bites/b1/attempts/01/checks.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 2
    assert "refusal" in checks["red_flags"]


def test_output_token_budget_blocks_over_cap_output(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    # The pipeline forwards no usage chunk on streams, so the worker estimates
    # tokens from the response's own content — the fake must drive that path.
    for seat in ("fast", "fast", "fast", "deep"):
        fake_pipeline.add(seat, finish_response({"answer": "x" * 512}))
    task_dir = service(tmp_path, fake_pipeline).submit(
        plan("budget", bite(output_tokens=8)), tmp_path
    )
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "BLOCKED"
    assert "output_token_cap" in receipt["results"][0]["failure"]["failures"]
    assert not (task_dir / "data/bites/b1/output.json").exists()


def test_wall_clock_budget_rejects_late_pipeline_output(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    for seat in ("fast", "fast", "fast", "deep"):
        fake_pipeline.add(seat, DelayedResponse(finish_response({"answer": "right"}), 0.08))
    short = bite(turns=1)
    short["budget"]["minutes"] = 0.0005
    task_dir = service(tmp_path, fake_pipeline).submit(plan("wall-clock", short), tmp_path)
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "BLOCKED"
    assert "wall_clock_cap" in receipt["results"][0]["failure"]["failures"]


def test_wandering_bite_without_finish_is_blocked(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    for seat in ("fast", "fast", "fast", "deep"):
        fake_pipeline.add(seat, text_response("still working"))
    task_dir = service(tmp_path, fake_pipeline).submit(plan("wander", bite(turns=2)), tmp_path)
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "BLOCKED"
    assert "missing_finish" in receipt["results"][0]["failure"]["failures"]


def test_pipeline_http_failure_mid_bite_retries_on_fast(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", "HTTP_500")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_dir = service(tmp_path, fake_pipeline).submit(plan("pipeline-failure", bite()), tmp_path)
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 2
    checks = json.loads((task_dir / "bites/b1/attempts/01/checks.json").read_text())
    assert "HTTPStatusError" in checks["failures"][0]


def test_sigterm_leaves_running_bite_for_resume(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", SignalResponse(finish_response({"answer": "wrong"})))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    runner = service(tmp_path, fake_pipeline)
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.submit(plan("resume", bite()), tmp_path)
    finally:
        signal.signal(signal.SIGTERM, previous)
    task_dir = tmp_path / "tasks/resume"
    assert _bite_state(task_dir, "b1") == "running"
    runner.resume("resume")
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 2
    assert any(
        row["state"] == "ready" and json.loads(row["detail_json"]).get("resume")
        for row in _events(task_dir)
    )


def test_resume_retries_failed_bite_when_history_records_a_remaining_attempt(
    tmp_path: Path, fake_pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_pipeline.add("fast", finish_response({"answer": "wrong"}))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    original = ArmLedger.transition

    def stop_before_retry(self, task_bite, state, **kwargs):
        if state == "ready" and (kwargs.get("detail") or {}).get("retry") == 2:
            raise RuntimeError("simulated crash before retry")
        original(self, task_bite, state, **kwargs)

    monkeypatch.setattr(ArmLedger, "transition", stop_before_retry)
    runner = service(tmp_path, fake_pipeline)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.submit(plan("resume-failed-retry", bite()), tmp_path)
    task_dir = tmp_path / "tasks/resume-failed-retry"
    failed = next(row for row in reversed(_events(task_dir)) if row["state"] == "failed")
    assert json.loads(failed["detail_json"])["retry_available"] is True

    monkeypatch.setattr(ArmLedger, "transition", original)
    runner.resume("resume-failed-retry")
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 2


def test_resume_does_not_reopen_failed_bite_after_the_ladder_is_exhausted(
    tmp_path: Path, fake_pipeline: FakePipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    deep_bite = bite(model="deep")
    fake_pipeline.add("deep", finish_response({"answer": "wrong"}))
    original = ArmLedger.transition

    def stop_before_block(self, task_bite, state, **kwargs):
        if state == "blocked":
            raise RuntimeError("simulated crash before block")
        original(self, task_bite, state, **kwargs)

    monkeypatch.setattr(ArmLedger, "transition", stop_before_block)
    runner = service(tmp_path, fake_pipeline)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.submit(plan("resume-failed-final", deep_bite), tmp_path)
    task_dir = tmp_path / "tasks/resume-failed-final"
    failed = next(row for row in reversed(_events(task_dir)) if row["state"] == "failed")
    assert json.loads(failed["detail_json"])["retry_available"] is False

    monkeypatch.setattr(ArmLedger, "transition", original)
    runner.resume("resume-failed-final")
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "BLOCKED"
    assert _bite_state(task_dir, "b1") == "failed"
    assert len(fake_pipeline.requests) == 1


def test_resume_refuses_build_and_model_digest_mismatch(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    service(tmp_path, fake_pipeline).submit(plan("mismatch", bite()), tmp_path)
    with pytest.raises(ResumeMismatchError, match="build SHA"):
        service(tmp_path, fake_pipeline, build_sha="head-b").resume("mismatch")
    with pytest.raises(ResumeMismatchError, match="model digest"):
        service(tmp_path, fake_pipeline, fast_digest="fast-digest-b").resume("mismatch")


def test_plausible_wrong_output_fails_checker_while_independent_branch_passes(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    for seat in ("fast", "fast", "fast", "deep"):
        fake_pipeline.add(seat, finish_response({"answer": "plausible but wrong"}))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    notices = StubNoticeSink()
    task_dir = service(tmp_path, fake_pipeline, notices=notices).submit(
        plan("branches", bite("wrong"), bite("independent")), tmp_path
    )
    receipt = json.loads((task_dir / "receipt.json").read_text())
    statuses = {row["bite_id"]: row["status"] for row in receipt["results"]}
    assert statuses == {"wrong": "BLOCKED", "independent": "PASS"}
    assert notices.notices[0]["bite_id"] == "wrong"
    assert "expected 'right'" in str(receipt["results"][0]["failure"])


def test_one_json_repair_turn_reaches_pipeline_again(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", tool_response("finish", "not JSON"))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_dir = service(tmp_path, fake_pipeline).submit(plan("repair", bite(turns=2)), tmp_path)
    assert json.loads((task_dir / "receipt.json").read_text())["status"] == "PASS"
    transcript = (task_dir / "bites/b1/attempts/01/transcript.jsonl").read_text()
    assert '"kind": "repair_response"' in transcript
    assert len(fake_pipeline.requests) == 2
    assert all(request["model"] == SEAT_TAGS["fast"] for request in fake_pipeline.requests)


def _run_direct_bite(
    tmp_path: Path, fake_pipeline: FakePipeline, name: str, turns: int
) -> tuple[Any, list[dict[str, Any]]]:
    task_dir = tmp_path / name
    task_bite = parse_plan(plan(name, bite(turns=turns))).bites[0]
    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={},
        attempt_dir=task_dir / "attempt",
    )
    records = [
        json.loads(line)
        for line in (task_dir / "attempt" / "transcript.jsonl").read_text().splitlines()
    ]
    return result, records


def test_text_only_reply_gets_one_finish_repair_turn_then_passes(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", text_response("Defect report delivered as plain text."))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    result, records = _run_direct_bite(tmp_path, fake_pipeline, "finish-repair", turns=2)

    assert result.finished and result.output == {"answer": "right"}
    assert result.red_flags == ()
    assert len(fake_pipeline.requests) == 2
    repair = fake_pipeline.requests[1]
    assert repair["portal_bite_max_hops"] == 1
    assert repair["messages"][-2] == {
        "role": "assistant",
        "content": "Defect report delivered as plain text.",
    }
    assert repair["messages"][-1]["role"] == "user"
    assert "finish" in repair["messages"][-1]["content"]
    assert "output" in repair["messages"][-1]["content"]
    kinds = [row["kind"] for row in records]
    assert kinds.count("finish_repair") >= 2
    stages = [row["stage"] for row in records if row["kind"] == "finish_repair"]
    assert stages.count("request") == 1 and stages.count("response") == 1


def test_finish_repair_request_forces_the_finish_tool_choice(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", text_response("Defect report delivered as plain text."))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    result, _records = _run_direct_bite(tmp_path, fake_pipeline, "finish-repair-forced", turns=2)

    assert result.finished and result.red_flags == ()
    assert fake_pipeline.requests[0]["tool_choice"] == "auto"
    repair = fake_pipeline.requests[1]
    assert repair["tool_choice"] == {"type": "function", "function": {"name": "finish"}}


def test_ignored_finish_repair_keeps_todays_red_flags(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", text_response("The answer is right, but as plain text."))
    fake_pipeline.add("fast", text_response("Still no tool call."))
    result, records = _run_direct_bite(tmp_path, fake_pipeline, "finish-repair-ignored", turns=2)

    assert not result.finished
    assert result.red_flags == ("missing_finish", "missing_finish_output")
    assert result.loop_outcome == "wandering"
    assert len(fake_pipeline.requests) == 2
    stages = [row["stage"] for row in records if row["kind"] == "finish_repair"]
    assert stages.count("request") == 1 and stages.count("response") == 1


def test_no_finish_repair_when_the_turn_budget_is_exhausted(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", text_response("Answer as text with no turns left."))
    result, records = _run_direct_bite(tmp_path, fake_pipeline, "finish-repair-capped", turns=1)

    assert not result.finished
    assert result.red_flags == ("missing_finish", "missing_finish_output")
    assert len(fake_pipeline.requests) == 1
    assert not [row for row in records if row["kind"] == "finish_repair"]


def test_no_finish_repair_when_the_token_budget_is_exhausted(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    # The fake forwards no usage chunk, so the worker estimates this reply at
    # ceil(34/4) = 9 tokens — exactly the bite's whole output budget.
    fake_pipeline.add("fast", text_response("Answer as text with no turns left."))
    raw_bite = bite(turns=2, output_tokens=9)
    task_dir = tmp_path / "finish-repair-token-capped"
    task_bite = parse_plan(plan("finish-repair-token-capped", raw_bite)).bites[0]
    result = run_bite(
        task_dir,
        task_bite,
        Engine(SEAT_TAGS["fast"], "test-digest", fake_pipeline.url, auth.PIPELINE_API_KEY),
        input_paths={},
        attempt_dir=task_dir / "attempt",
    )
    records = [
        json.loads(line)
        for line in (task_dir / "attempt" / "transcript.jsonl").read_text().splitlines()
    ]

    assert not result.finished
    assert result.red_flags == ("missing_finish", "missing_finish_output")
    assert len(fake_pipeline.requests) == 1
    assert not [row for row in records if row["kind"] == "finish_repair"]


def test_residency_config_defaults_to_swap_and_reads_co_resident(tmp_path: Path) -> None:
    assert load_residency_mode(tmp_path / "missing.yaml") == "swap"
    config = tmp_path / "arm.yaml"
    config.write_text("residency_mode: co-resident\n", encoding="utf-8")
    assert load_residency_mode(config) == "co-resident"


def test_module_switch_is_on_in_repo_config() -> None:
    # Enabled after the 2026-10-23 end-to-end run (Telegram approval, repair, review) passed.
    assert module_is_enabled(Path("config/portal.yaml"))


def test_overnight_queue_runs_tasks_in_fifo_order_and_records_receipts(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    runner_service = service(tmp_path, fake_pipeline)
    gate = QueueGate(
        runner_service.engines,
        {"yield_lock_dir": str(tmp_path / "locks")},
        pid_file=tmp_path / "memory-pids",
    )
    runner = OvernightQueue(tmp_path / "tasks", runner_service, gate)
    with QueueLedger(tmp_path / "tasks") as ledger:
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-first", bite()), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-second", bite()), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
    first = runner.run_next()
    second = runner.run_next()
    with QueueLedger(tmp_path / "tasks") as ledger:
        rows = ledger.items()
    assert (first.status, first.task_id) == ("DONE", "queue-first")
    assert (second.status, second.task_id) == ("DONE", "queue-second")
    assert [row["state"] for row in rows] == ["done", "done"]
    assert all((tmp_path / "tasks" / row["task_id"] / "receipt.json").is_file() for row in rows)


def test_queue_blocks_one_broken_task_and_still_runs_the_next(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    runner_service = service(tmp_path, fake_pipeline)
    gate = QueueGate(
        runner_service.engines,
        {"yield_lock_dir": str(tmp_path / "locks")},
        pid_file=tmp_path / "memory-pids",
    )
    runner = OvernightQueue(tmp_path / "tasks", runner_service, gate)
    with QueueLedger(tmp_path / "tasks") as ledger:
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-broken", bite()), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-after", bite()), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
    (tmp_path / "tasks" / "queue-broken").mkdir()
    fake_pipeline.add("fast", finish_response({"answer": "right"}))

    broken = runner.run_next()
    after = runner.run_next()

    assert (broken.status, broken.task_id) == ("BLOCKED", "queue-broken")
    assert "FileNotFoundError" in str(broken.reason)
    assert (after.status, after.task_id) == ("DONE", "queue-after")
    with QueueLedger(tmp_path / "tasks") as ledger:
        assert [row["state"] for row in ledger.items()] == ["blocked", "done"]


def test_queue_review_waits_when_a_bench_lock_appears_mid_bite(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    runner_service = service(tmp_path, fake_pipeline)
    gate = QueueGate(
        runner_service.engines,
        {"yield_lock_dir": str(lock_dir)},
        pid_file=tmp_path / "memory-pids",
    )
    runner = OvernightQueue(tmp_path / "tasks", runner_service, gate)
    reviewed = bite(review="deep", review_reason="review must respect the bench lock")
    with QueueLedger(tmp_path / "tasks") as ledger:
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-review-lock", reviewed), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
    # The bench lock appears while the fast bite is in flight, not on a timer.
    fake_pipeline.add(
        "fast",
        DelayedResponse(
            finish_response({"answer": "right"}),
            0.3,
            on_serve=lambda: (lock_dir / "bench.pid").write_text(
                f"{os.getpid()}\n", encoding="utf-8"
            ),
        ),
    )
    fake_pipeline.add("deep", text_response(json.dumps({"decision": "approve", "reason": "ok"})))
    result = runner.run_next()

    task_dir = tmp_path / "tasks" / "queue-review-lock"
    assert result.status == "WAITING"
    assert [request["model"] for request in fake_pipeline.requests] == [SEAT_TAGS["fast"]]
    assert json.loads((task_dir / "receipt.json").read_text())["status"] == "WAITING"
    assert _bite_state(task_dir, "b1") == "ready"


def test_queue_review_capacity_refusal_waits_instead_of_burning_an_attempt(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    runner_service = service(tmp_path, fake_pipeline)
    runner_service.bite_gate = lambda _bite: True
    reviewed = bite(review="deep", review_reason="review seat admission must not spend the ladder")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    fake_pipeline.add_admin_response({"busy": False, "fits": True, "models": []})
    fake_pipeline.add_admin_response({"busy": False, "fits": False, "models": []})
    fake_pipeline.add("deep", text_response(json.dumps({"decision": "approve", "reason": "ok"})))

    waiting = runner_service.submit(plan("queue-review-fit", reviewed), tmp_path)
    receipt = json.loads((waiting / "receipt.json").read_text())

    assert receipt["status"] == "WAITING"
    assert receipt["results"][0]["attempts"] == 1
    assert [request["model"] for request in fake_pipeline.requests] == [SEAT_TAGS["fast"]]

    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    resumed = runner_service.resume("queue-review-fit")
    receipt = json.loads((resumed / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["results"][0]["attempts"] == 2


def test_queue_yield_before_the_request_does_not_count_an_attempt(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    runner_service = service(tmp_path, fake_pipeline)
    gate = QueueGate(
        runner_service.engines,
        {"yield_lock_dir": str(tmp_path / "locks")},
        pid_file=tmp_path / "memory-pids",
    )
    runner = OvernightQueue(tmp_path / "tasks", runner_service, gate)
    with QueueLedger(tmp_path / "tasks") as ledger:
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-yield", bite()), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
    fake_pipeline.add_admin_response({"busy": False, "fits": True, "models": []})
    fake_pipeline.add_admin_response({"busy": True, "fits": True, "models": []})

    first = runner.run_next()
    task_dir = tmp_path / "tasks" / "queue-yield"
    attempts_dir = task_dir / "bites/b1/attempts"

    assert first.status == "WAITING"
    assert _bite_state(task_dir, "b1") == "ready"
    assert json.loads((task_dir / "receipt.json").read_text())["results"][0]["attempts"] == 0
    assert not attempts_dir.exists() or not any(attempts_dir.iterdir())

    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    second = runner.run_next()
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert second.status == "DONE"
    assert receipt["results"][0]["attempts"] == 1
    assert sorted(path.name for path in attempts_dir.iterdir()) == ["01"]
    assert len(fake_pipeline.requests) == 1


def test_queue_ledger_reclaims_a_task_after_its_runner_process_dies(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    task_root = tmp_path / "tasks"
    runner_service = service(tmp_path, fake_pipeline)
    with QueueLedger(task_root) as ledger:
        ledger.enqueue(
            validate_execution_plan(
                plan("queue-recovery", bite()), runner_service.arm_config, tmp_path
            ),
            tmp_path,
        )
        item, active = ledger.claim_next()
        assert item is not None and not active
    with sqlite3.connect(task_root / "queue.sqlite3") as db:
        db.execute(
            "UPDATE queue_task SET runner_pid = 2147483647 WHERE task_id = ?", ("queue-recovery",)
        )
    with QueueLedger(task_root) as ledger:
        recovered, active = ledger.claim_next()
    assert recovered is not None and not active
    assert recovered["task_id"] == "queue-recovery" and recovered["state"] == "running"


def test_queue_gate_yields_for_live_lock_and_pipeline_busy_or_unknown_fit(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    runner_service = service(tmp_path, fake_pipeline)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock = lock_dir / "uat.pid"
    lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
    pid_file = tmp_path / "pids"
    gate = QueueGate(runner_service.engines, {"yield_lock_dir": str(lock_dir)}, pid_file=pid_file)
    task_bite = parse_plan(plan("gate", bite())).bites[0]
    assert not gate.allows(task_bite)
    assert "uat.pid" in str(gate.last_reason)
    assert not fake_pipeline.admin_requests

    lock.unlink()
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert not gate.allows(task_bite)
    assert "memory-safety" in str(gate.last_reason)
    pid_file.unlink()
    fake_pipeline.add_admin_response({"busy": True, "fits": True, "models": []})
    assert not gate.allows(task_bite)
    assert "traffic" in str(gate.last_reason)
    fake_pipeline.add_admin_response({"busy": False, "fits": None, "models": []})
    assert not gate.allows(task_bite)
    assert "no fit" in str(gate.last_reason)
    fake_pipeline.add_admin_response({"fits": True, "models": []})
    assert not gate.allows(task_bite)
    assert "active traffic" in str(gate.last_reason)


def test_fake_pipeline_enforces_production_bearer_auth() -> None:
    key = auth.PIPELINE_API_KEY
    pipeline = FakePipeline()
    try:
        pipeline.add("fast", finish_response({"answer": "right"}))
        request = {
            "url": f"{pipeline.url}/v1/chat/completions",
            "json": {"model": "auto-daily::fast", "messages": []},
            "timeout": 5,
        }
        assert httpx.post(**request).status_code == 401
        assert (
            httpx.post(headers={"Authorization": "Bearer wrong-key"}, **request).status_code == 401
        )
        assert httpx.post(headers={"Authorization": f"Bearer {key}"}, **request).status_code == 200
        with pytest.raises(HTTPException) as missing:
            auth._verify_key(None)
        with pytest.raises(HTTPException) as wrong:
            auth._verify_key("Bearer wrong-key")
        assert missing.value.status_code == wrong.value.status_code == 401
    finally:
        pipeline.close()


def _bite_request() -> dict[str, Any]:
    return {
        "model": "auto-daily::fast",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [
            {"type": "function", "function": {"name": "finish", "parameters": {}}},
            {"type": "function", "function": {"name": "wiki_search", "parameters": {}}},
        ],
        "portal_bite_tools": ["wiki_search", "finish"],
    }


def _schema_names(body: dict[str, Any]) -> list[str]:
    return [
        tool.get("function", {}).get("name", "")
        for tool in body.get("tools") or []
        if isinstance(tool, dict)
    ]


def _post_bite_request(pipeline: FakePipeline, correlation_id: str) -> None:
    response = httpx.post(
        f"{pipeline.url}/v1/chat/completions",
        json=_bite_request(),
        headers={
            "Authorization": f"Bearer {auth.PIPELINE_API_KEY}",
            "X-Correlation-ID": correlation_id,
        },
        timeout=5,
    )
    assert response.status_code == 200


def test_fake_trace_tools_offered_matches_production_bite_gate() -> None:
    pipeline = FakePipeline()
    try:
        pipeline.add("fast", finish_response({"answer": "right"}))
        _post_bite_request(pipeline, "parity-trace")
        owned = sorted({"finish", "wiki_search"} | set(_schema_names(_bite_request())))
        expected, _allowed = apply_bite_tool_scope(_bite_request(), owned)
        assert expected == ["finish", "wiki_search"]
        assert pipeline.traces["parity-trace"]["tools_offered"] == expected
    finally:
        pipeline.close()


def test_fake_registry_missing_the_bite_tool_offers_only_what_it_owns() -> None:
    pipeline = FakePipeline(pipeline_tools={"finish"})
    try:
        pipeline.add("fast", finish_response({"answer": "right"}))
        body = _bite_request()
        # The worker ships only the finish schema; the bite tools live in the
        # pipeline's registry, which this fake declares without wiki_search.
        body["tools"] = [{"type": "function", "function": {"name": "finish", "parameters": {}}}]
        response = httpx.post(
            f"{pipeline.url}/v1/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {auth.PIPELINE_API_KEY}",
                "X-Correlation-ID": "parity-missing-tool",
            },
            timeout=5,
        )
        assert response.status_code == 200
        expected, _allowed = apply_bite_tool_scope(body, ["finish"])
        assert expected == ["finish"]
        assert pipeline.traces["parity-missing-tool"]["tools_offered"] == expected
    finally:
        pipeline.close()


def _events(task_dir: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(task_dir / "ledger.db") as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM transition ORDER BY id")]


def _bite_state(task_dir: Path, bite_id: str) -> str:
    with sqlite3.connect(task_dir / "ledger.db") as db:
        row = db.execute("SELECT state FROM bite WHERE bite_id = ?", (bite_id,)).fetchone()
    return str(row[0])


def test_seated_model_tags_default_follow_config_and_reject_conflicts() -> None:
    def config(*seated: dict[str, str]) -> dict[str, Any]:
        return {"disciplines": {f"d{i}": {"seated_models": s} for i, s in enumerate(seated)}}

    assert seated_model_tags(config()) == {"fast": "auto-daily::fast", "deep": "auto-daily::deep"}
    assert seated_model_tags(config({"fast": "auto-daily::gemma-fast"}))["fast"] == (
        "auto-daily::gemma-fast"
    )
    with pytest.raises(ValueError, match="disagree"):
        seated_model_tags(config({"fast": "auto-daily::fast"}, {"fast": "auto-daily::gemma-fast"}))
    with pytest.raises(ValueError, match="auto-daily"):
        seated_model_tags(config({"fast": "some-raw-model"}))


def test_tools_resolve_listed_input_names_to_staged_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "discount.py").write_text("old\n", encoding="utf-8")
    (tmp_path / "inputs" / "test_discount.py").write_text("def test(): pass\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    def fake_run(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured["selectors"] = payload["selectors"]
        return {"exit_code": 0, "stdout": "1 passed\n", "stderr": "", "files": {}}

    monkeypatch.setattr(orchestration_tools, "_sandbox_request", fake_run)
    tools = TaskToolExecutor(
        tmp_path,
        ("file_read", "file_write", "pytest_run"),
        readable_paths=("inputs/discount.py", "inputs/test_discount.py"),
        writable_paths=("inputs/discount.py",),
        aliases={
            "discount.py": "inputs/discount.py",
            "test_discount.py": "inputs/test_discount.py",
        },
    )

    assert tools.dispatch("file_write", {"path": "discount.py", "content": "new\n"}).startswith(
        "wrote"
    )
    assert (tmp_path / "inputs" / "discount.py").read_text(encoding="utf-8") == "new\n"
    assert tools.dispatch("file_read", {"path": "test_discount.py"}) == "def test(): pass\n"
    assert "exit_code=0" in tools.dispatch("pytest_run", {"args": "test_discount.py::test -q"})
    assert captured["selectors"] == ["inputs/test_discount.py::test", "-q"]
    assert tools.dispatch("file_write", {"path": "test_discount.py", "content": "x"}).startswith(
        "ERROR:"
    )


def test_review_vote_parser_accepts_fenced_json_and_reports_bad_replies() -> None:
    from portal.modules.orchestration.review import _parse_vote

    fenced = '\n\n```json\n{"decision": "approve", "reason": "tests pass"}\n```'
    assert _parse_vote(fenced) == {"decision": "approve", "reason": "tests pass"}
    bad = _parse_vote("⚠️ The model did not produce an answer.")
    assert bad["decision"] == "reject" and "did not produce an answer" in bad["reason"]


def test_review_votes_are_tool_less_bite_requests() -> None:
    from portal.modules.orchestration import review as review_module

    bodies: list[dict[str, Any]] = []

    class StubEngine:
        model_tag = "auto-daily::deep"

        def load_plan(self, _seconds: float) -> dict[str, Any]:
            return {"busy": False, "fits": True}

        def chat(self, body: dict[str, Any], _timeout: float, _on_event: Any) -> dict[str, Any]:
            bodies.append(body)
            vote = '{"decision": "approve", "reason": "ok"}'
            return {"choices": [{"message": {"content": vote}}]}

    result = review_module.review_output(
        StubEngine(),  # type: ignore[arg-type]
        parse_plan(plan("review-scope", bite())).bites[0],
        "PASS",
        vote_count=1,
        minimum_approve_votes=1,
        persona="auto-coding",
    )
    assert result.passed
    # No tools: the deep workspace's server tools let one vote overflow its context.
    assert bodies[0]["portal_bite_tools"] == []
    assert bodies[0]["portal_bite_persona"] == "auto-coding"
