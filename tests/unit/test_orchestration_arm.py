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

import httpx
import pytest
import yaml
from fastapi import HTTPException

from portal.modules.coding.tools import code_sandbox_mcp as sandbox_mcp
from portal.modules.orchestration import tools as orchestration_tools
from portal.modules.orchestration.contracts import parse_plan
from portal.modules.orchestration.ledger import ArmLedger, ResumeMismatchError
from portal.modules.orchestration.planner import instantiate_plan_template, validate_execution_plan
from portal.modules.orchestration.queue import OvernightQueue, QueueGate, QueueLedger
from portal.modules.orchestration.service import (
    ArmService,
    StubNoticeSink,
    load_residency_mode,
    module_is_enabled,
)
from portal.modules.orchestration.tools import (
    FILE_READ_LIMIT,
    FILE_WRITE_LIMIT,
    PYTEST_TIMEOUT_SECONDS,
    TASK_BYTES_LIMIT,
    TASK_FILE_LIMIT,
    TaskToolExecutor,
)
from portal.modules.orchestration.worker import Engine, run_bite
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
    repo = Path(__file__).resolve().parents[2]
    settings = yaml.safe_load((repo / "config" / "orchestration_arm.yaml").read_text())
    settings["disciplines"]["offline-test"] = {
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
            "auto-daily::fast",
            fast_digest,
            pipeline.url,
            auth.PIPELINE_API_KEY,
            "omlx",
            "fake-fast",
        ),
        "deep": Engine(
            "auto-daily::deep",
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


def test_detection_engineering_template_validates_and_runs_offline(
    tmp_path: Path, fake_pipeline: FakePipeline
) -> None:
    repo = Path(__file__).resolve().parents[2]
    arm_config = yaml.safe_load((repo / "config/orchestration_arm.yaml").read_text())
    detection = arm_config["disciplines"]["detection-engineering"]
    assert detection["seating_status"] == "unseated"
    assert "seated_models" not in detection
    assert "detection-engineering" not in arm_config["calibration"]["rates_by_discipline"]
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
            "auto-daily::fast",
            "fast-digest",
            fake_pipeline.url,
            auth.PIPELINE_API_KEY,
            "omlx",
            "fake-fast",
        ),
        "deep": Engine(
            "auto-daily::deep",
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

    with pytest.raises(ValueError, match="WFE rates for detection-engineering"):
        arm.submit(task_plan.as_dict(), tmp_path)
    arm.arm_config["calibration"]["minimum_pass_probability"] = None
    task_dir = arm.submit(task_plan.as_dict(), tmp_path, unattended=False)

    receipt = json.loads((task_dir / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert len(receipt["results"]) == 4
    assert notices.approval.call_count == 1
    assert [
        request["portal_bite_tools"]
        for request in fake_pipeline.requests
        if "portal_bite_tools" in request
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
        "auto-daily::fast",
        "auto-daily::fast",
        "auto-daily::deep",
        "auto-daily::deep",
        "auto-daily::deep",
        "auto-daily::fast",
        "auto-daily::deep",
    ]


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
    assert fake_pipeline.requests[0]["model"] == "auto-daily::fast"


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
            "auto-daily::fast",
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
    followup = fake_pipeline.requests[1]["messages"]
    assert followup[-1]["role"] == "tool"
    assert followup[-1]["name"] == "file_read"
    assert followup[-1]["content"] == "source contents"


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
            "auto-daily::fast",
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
    assert "/workspace" not in command
    assert "PYTHONPATH" not in command
    assert "os.environ" not in sandbox_mcp._PYTEST_RUNNER
    assert "os.setuid(65534)" in sandbox_mcp._PYTEST_RUNNER


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
    task_bite = bite(inputs=["source.txt"])
    task_dir = service(tmp_path, fake_pipeline).submit(plan("input-read", task_bite), tmp_path)
    request = fake_pipeline.requests[0]
    messages = request["messages"]
    source = json.loads(messages[1]["content"])["inputs"]["source.txt"]
    assert source["path"].startswith("inputs/")
    assert (task_dir / "data" / source["path"]).read_text(
        encoding="utf-8"
    ) == "complete source text"
    assert "complete source text" not in json.dumps(messages)


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
    assert all(request["model"] == "auto-daily::fast" for request in fake_pipeline.requests)


def test_residency_config_defaults_to_swap_and_reads_co_resident(tmp_path: Path) -> None:
    assert load_residency_mode(tmp_path / "missing.yaml") == "swap"
    config = tmp_path / "arm.yaml"
    config.write_text("residency_mode: co-resident\n", encoding="utf-8")
    assert load_residency_mode(config) == "co-resident"


def test_module_switch_is_off_by_default_in_repo_config() -> None:
    assert not module_is_enabled(Path("config/portal.yaml"))


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
    assert [request["model"] for request in fake_pipeline.requests] == ["auto-daily::fast"]
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
    assert [request["model"] for request in fake_pipeline.requests] == ["auto-daily::fast"]

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
