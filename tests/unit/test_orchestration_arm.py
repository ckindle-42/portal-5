"""Offline orchestration arm tests through a fake Pipeline API."""

from __future__ import annotations

import json
import signal
import sqlite3
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from portal.modules.orchestration.ledger import ArmLedger, ResumeMismatchError
from portal.modules.orchestration.service import (
    ArmService,
    StubNoticeSink,
    load_residency_mode,
    module_is_enabled,
)
from portal.modules.orchestration.worker import Engine
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
) -> dict[str, Any]:
    return {
        "bite_id": bite_id,
        "goal": f"Produce the answer for {bite_id}.",
        "discipline": "offline-test",
        "inputs": inputs or [],
        "depends_on": depends_on or [],
        "tools": tools or [],
        "output": {"path": f"bites/{bite_id}/output.json", "schema": _SCHEMA},
        "accept": [{"type": "equals", "path": "$.answer", "value": expected}],
        "risk": "low",
        "budget": {"turns": turns, "minutes": 1, "output_tokens": output_tokens},
        "model": model,
        "procedure": "Use the declared checks, then finish.",
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
    config.write_text("residency_mode: swap\n", encoding="utf-8")
    engines = {
        "fast": Engine(
            "auto-daily::fast", fast_digest, pipeline.url, "test-key", "omlx", "fake-fast"
        ),
        "deep": Engine(
            "auto-daily::deep", deep_digest, pipeline.url, "test-key", "omlx", "fake-deep"
        ),
    }
    return ArmService(
        tmp_path / "tasks", engines, build_sha=build_sha, residency_config=config, notices=notices
    )


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
    assert request["model"] == "auto-daily::fast"
    assert request["portal_bite_tools"] == ["finish"]
    assert request["tools"][-1]["function"]["name"] == "finish"
    assert fake_pipeline.admin_requests == [{"models": [{"engine": "omlx", "model": "fake-fast"}]}]


def test_bite_tools_are_sent_as_a_strict_pipeline_allowlist(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    service(tmp_path, fake_pipeline).submit(plan("scope", bite(tools=["wiki_search"])), tmp_path)
    assert fake_pipeline.requests[0]["portal_bite_tools"] == ["wiki_search", "finish"]
    assert fake_pipeline.requests[0]["model"] == "auto-daily::fast"


def test_worker_sends_input_paths_without_packing_file_contents(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    (tmp_path / "source.txt").write_text("complete source text", encoding="utf-8")
    fake_pipeline.add("fast", finish_response({"answer": "right"}))
    task_bite = bite(inputs=["source.txt"])
    service(tmp_path, fake_pipeline).submit(plan("input-read", task_bite), tmp_path)
    request = fake_pipeline.requests[0]
    messages = request["messages"]
    source = json.loads(messages[1]["content"])["inputs"]["source.txt"]
    assert source == {"path": str((tmp_path / "source.txt").resolve())}
    assert "complete source text" not in json.dumps(messages)


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
    for seat in ("fast", "fast", "fast", "deep"):
        fake_pipeline.add(seat, finish_response({"answer": "right"}, tokens=50))
    task_dir = service(tmp_path, fake_pipeline).submit(
        plan("budget", bite(output_tokens=8)), tmp_path
    )
    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "BLOCKED"
    assert "output_token_cap" in receipt["results"][0]["failure"]["failures"]
    assert not (task_dir / "bites/b1/output.json").exists()


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
    assert all(request["model"] == "auto-daily::fast" for request in fake_pipeline.requests)


def test_residency_config_defaults_to_swap_and_reads_co_resident(tmp_path: Path) -> None:
    assert load_residency_mode(tmp_path / "missing.yaml") == "swap"
    config = tmp_path / "arm.yaml"
    config.write_text("residency_mode: co-resident\n", encoding="utf-8")
    assert load_residency_mode(config) == "co-resident"


def test_module_switch_is_off_by_default_in_repo_config() -> None:
    assert not module_is_enabled(Path("config/portal.yaml"))


def _events(task_dir: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(task_dir / "ledger.db") as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM transition ORDER BY id")]


def _bite_state(task_dir: Path, bite_id: str) -> str:
    with sqlite3.connect(task_dir / "ledger.db") as db:
        row = db.execute("SELECT state FROM bite WHERE bite_id = ?", (bite_id,)).fetchone()
    return str(row[0])
