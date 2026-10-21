"""Offline orchestration acceptance rig using a fake OpenAI Pipeline API."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(_ROOT), str(_ROOT / "tests" / "unit")]

from orchestration_fake_pipeline import (  # noqa: E402
    FakePipeline,
    SignalResponse,
    finish_response,
    text_response,
)

from portal.modules.orchestration.ledger import ResumeMismatchError  # noqa: E402
from portal.modules.orchestration.service import ArmService  # noqa: E402
from portal.modules.orchestration.worker import Engine  # noqa: E402

_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def run_rig(workdir: Path) -> list[dict[str, str]]:
    tasks = workdir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    results = []
    results.append(_scenario("happy_path", lambda: _happy(tasks / "happy", "happy")))
    results.append(_scenario("red_flag_retry", lambda: _red_flag(tasks / "red", "red")))
    results.append(_scenario("budget_exhaustion", lambda: _budget(tasks / "budget", "budget")))
    results.append(_scenario("wandering_bite", lambda: _wander(tasks / "wander", "wander")))
    results.append(
        _scenario("pipeline_failure", lambda: _engine_failure(tasks / "engine", "engine"))
    )
    results.append(_scenario("sigterm_resume", lambda: _resume(tasks / "resume", "resume")))
    results.append(
        _scenario("identity_mismatch", lambda: _mismatch(tasks / "mismatch", "mismatch"))
    )
    results.append(
        _scenario(
            "blocked_branch_independent_pass", lambda: _branches(tasks / "branches", "branches")
        )
    )
    receipt = {
        "head": _head_sha(),
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
        "workdir": str(workdir.resolve()),
    }
    (workdir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return results


def _scenario(name: str, run: Callable[[], str]) -> dict[str, str]:
    try:
        evidence = run()
        return {"scenario": name, "status": "PASS", "evidence": evidence}
    except Exception as exc:
        return {"scenario": name, "status": "FAIL", "evidence": f"{type(exc).__name__}: {exc}"}


def _run_task(
    root: Path, task_id: str, responses: list[tuple[str, Any]], bites: list[dict[str, Any]]
) -> tuple[dict[str, Any], FakePipeline]:
    pipeline = FakePipeline()
    for seat, response in responses:
        pipeline.add(seat, response)
    (root / "config").mkdir(parents=True, exist_ok=True)
    config = root / "config" / "orchestration_arm.yaml"
    config.write_text("residency_mode: swap\n", encoding="utf-8")
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    service = ArmService(root, engines, build_sha="offline-head", residency_config=config)
    task = service.submit(
        {"task_id": task_id, "goal": "Offline rig scenario", "bites": bites}, root
    )
    receipt = json.loads((task / "receipt.json").read_text(encoding="utf-8"))
    pipeline.close()
    return receipt, pipeline


def _happy(root: Path, task_id: str) -> str:
    receipt, pipeline = _run_task(
        root, task_id, [("fast", finish_response({"answer": "right"}))], [_bite("b1")]
    )
    assert receipt["status"] == "PASS" and pipeline.requests[0]["model"] == "auto-daily::fast"
    return "one auto-daily::fast request passed through the fake Pipeline port"


def _red_flag(root: Path, task_id: str) -> str:
    receipt, _ = _run_task(
        root,
        task_id,
        [
            ("fast", finish_response("I cannot help with this request.")),
            ("fast", finish_response("right")),
        ],
        [_bite("b1", text=True)],
    )
    assert receipt["status"] == "PASS" and receipt["results"][0]["attempts"] == 2
    return "refusal red flag discarded; second Fast attempt passed"


def _budget(root: Path, task_id: str) -> str:
    responses = [
        (seat, finish_response({"answer": "right"}, tokens=50))
        for seat in ("fast", "fast", "fast", "deep")
    ]
    receipt, _ = _run_task(root, task_id, responses, [_bite("b1", tokens=8)])
    assert receipt["status"] == "BLOCKED"
    return "output-token cap blocked the bite after the failure ladder"


def _wander(root: Path, task_id: str) -> str:
    responses = [(seat, text_response("working")) for seat in ("fast", "fast", "fast", "deep")]
    receipt, _ = _run_task(root, task_id, responses, [_bite("b1")])
    assert receipt["status"] == "BLOCKED"
    return "missing finish call blocked the bite"


def _engine_failure(root: Path, task_id: str) -> str:
    receipt, pipeline = _run_task(
        root,
        task_id,
        [("fast", "HTTP_500"), ("fast", finish_response({"answer": "right"}))],
        [_bite("b1")],
    )
    assert receipt["status"] == "PASS" and len(pipeline.requests) == 2
    return "HTTP 500 mid-bite retried through the Pipeline and passed"


def _resume(root: Path, task_id: str) -> str:
    pipeline = FakePipeline()
    pipeline.add("fast", SignalResponse(finish_response({"answer": "right"})))
    pipeline.add("fast", finish_response({"answer": "right"}))
    root.mkdir(parents=True, exist_ok=True)
    config = root / "orchestration_arm.yaml"
    config.write_text("residency_mode: swap\n", encoding="utf-8")
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    runner = ArmService(root, engines, build_sha="offline-head", residency_config=config)
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        try:
            runner.submit({"task_id": task_id, "goal": "resume", "bites": [_bite("b1")]}, root)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("fake server did not interrupt the first request")
    finally:
        signal.signal(signal.SIGTERM, previous)
    runner.resume(task_id)
    receipt = json.loads((root / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    pipeline.close()
    return "SIGTERM left a running bite; resume requeued it and passed"


def _mismatch(root: Path, task_id: str) -> str:
    pipeline = FakePipeline()
    pipeline.add("fast", finish_response({"answer": "right"}))
    config = root / "orchestration_arm.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("residency_mode: swap\n", encoding="utf-8")
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    root.mkdir(parents=True, exist_ok=True)
    ArmService(root, engines, build_sha="head-a", residency_config=config).submit(
        {"task_id": task_id, "goal": "mismatch", "bites": [_bite("b1")]}, root
    )
    try:
        ArmService(root, engines, build_sha="head-b", residency_config=config).resume(task_id)
    except ResumeMismatchError as exc:
        assert "build SHA" in str(exc)
    else:
        raise AssertionError("changed build SHA was accepted")
    pipeline.close()
    return "resume refused the changed build SHA"


def _branches(root: Path, task_id: str) -> str:
    responses = [
        (seat, finish_response({"answer": "wrong"})) for seat in ("fast", "fast", "fast", "deep")
    ]
    responses.append(("fast", finish_response({"answer": "right"})))
    receipt, _ = _run_task(root, task_id, responses, [_bite("bad"), _bite("independent")])
    statuses = {result["bite_id"]: result["status"] for result in receipt["results"]}
    assert statuses == {"bad": "BLOCKED", "independent": "PASS"}
    return "failed bite blocked while independent branch passed"


def _bite(bite_id: str, *, text: bool = False, tokens: int = 256) -> dict[str, Any]:
    output = (
        {"path": f"bites/{bite_id}/output.txt", "file_type": "text"}
        if text
        else {
            "path": f"bites/{bite_id}/output.json",
            "schema": _SCHEMA,
        }
    )
    accept = (
        [{"type": "contains", "value": "right"}]
        if text
        else [{"type": "equals", "path": "$.answer", "value": "right"}]
    )
    return {
        "bite_id": bite_id,
        "goal": "produce the expected value",
        "discipline": "offline-rig",
        "inputs": [],
        "depends_on": [],
        "tools": [],
        "output": output,
        "accept": accept,
        "risk": "low",
        "budget": {"turns": 2, "minutes": 1, "output_tokens": tokens},
        "model": "fast",
    }


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=None)
    args = parser.parse_args()
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="portal5-arm-rig-"))
    workdir.mkdir(parents=True, exist_ok=True)
    results = run_rig(workdir)
    print(json.dumps({"receipt": str(workdir / "receipt.json"), "results": results}, indent=2))
    return 0 if all(row["status"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
