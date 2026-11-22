"""Offline Portal-seat escalation: fakes at the Engine/dispatcher boundary, no live calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from portal.modules.orchestration import portal_escalate as pe
from portal.modules.orchestration.escalate import LaneChanges, LaneResult, build_escalator
from portal.modules.orchestration.queue import QueueRun

_REAL_DISPATCHER = pe.PortalSeatDispatcher


def _policy(
    target: str | None = None,
    seats: dict[str, Any] | None = None,
    cloud: bool | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {"enabled": True}
    if target is not None:
        block["target"] = target
    if seats is not None:
        block["portal_seats"] = seats
    policy: dict[str, Any] = {"escalation": block}
    if cloud is not None:
        policy["personal_cloud"] = {"enabled": cloud}
    return policy


class _FakeEngine:
    def __init__(
        self, seat: str, reply: str = "## RESULT\nfixed\n", error: Exception | None = None
    ):
        self.seat = seat
        self.reply = reply
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def chat(self, body: dict[str, Any], timeout: float, on_event: Any) -> dict[str, Any]:
        self.calls.append(body)
        if self.error is not None:
            raise self.error
        return {"choices": [{"message": {"content": self.reply}}]}


class _EngineFactory:
    def __init__(self, reply: str = "## RESULT\nfixed\n", error: Exception | None = None):
        self.engines: dict[str, _FakeEngine] = {}
        self.reply = reply
        self.error = error

    def __call__(self, seat: str) -> _FakeEngine:
        if seat not in self.engines:
            self.engines[seat] = _FakeEngine(seat, self.reply, self.error)
        return self.engines[seat]

    def seats_called(self) -> list[str]:
        return [seat for seat, engine in self.engines.items() if engine.calls]


class _CloudSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> LaneResult:
        self.calls.append(kwargs)
        return LaneResult(
            kwargs["role"],
            kwargs["tier"],
            1,
            "cloud lane failed",
            f"lane/{kwargs['role']}",
            None,
            LaneChanges((), (), ()),
        )


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PORTAL_ESCALATION_TARGET", "PIPELINE_URL", "PORTAL_ARM_PIPELINE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PIPELINE_API_KEY", "test-key-123")


@pytest.fixture()
def harness(tmp_path: Path, env: None) -> tuple[Path, Path, dict[str, Any], QueueRun]:
    repo = tmp_path / "repo"
    contracts = repo / "coding_task" / "CONTRACTS"
    contracts.mkdir(parents=True)
    for kind in ("debug", "tests", "security"):
        (contracts / f"{kind}.md").write_text(f"{kind} contract\n", encoding="utf-8")
    tasks = tmp_path / "tasks"
    receipt = tasks / "job-1" / "receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "status": "BLOCKED",
                "reason": "step exited 1",
                "steps": [
                    {
                        "id": "run",
                        "argv": ["python", "x.py"],
                        "state": "failed",
                        "stdout_tail": "boom",
                        "stderr_tail": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    item = {
        "kind": "job",
        "task_id": "job-1",
        "plan_json": json.dumps({"id": "job-1", "purpose": "repair the thing", "steps": []}),
        "source_dir": str(repo),
    }
    return repo, tasks, item, QueueRun("BLOCKED", "job-1", receipt, "step exited 1")


def _hook(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    policy: dict[str, Any],
    factory: _EngineFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, _CloudSpy, list[list[str]]]:
    repo, tasks, _item, _run = harness
    monkeypatch.setattr(
        pe, "PortalSeatDispatcher", lambda seats: _REAL_DISPATCHER(seats, engine_factory=factory)
    )
    hook = build_escalator(tasks, repo, None, policy)
    assert hook is not None
    escalator = hook.escalator
    cloud = _CloudSpy()
    verdicts: list[list[str]] = []
    escalator.dispatcher = cloud
    escalator.verdict_runner = lambda argv: verdicts.append(list(argv)) or 0
    escalator.environment_check = lambda main, source: None
    escalator.log_reader = lambda: ""
    return hook, cloud, verdicts


def test_config_helpers_default_safely(env: None) -> None:
    assert pe.escalation_target({}) == "cloud"
    assert pe.escalation_target(_policy()) == "cloud"
    assert pe.escalation_target(_policy(target="portal")) == "portal"
    assert pe.escalation_target(_policy(target="bogus")) == "cloud"
    assert pe.escalation_target(_policy(target="portal_then_cloud")) == "portal_then_cloud"
    seats = pe.portal_seats_map(_policy())
    assert seats["code"][0] == "auto-coding"
    assert seats["security"][0] == "auto-security"
    assert pe.cloud_fallback_allowed(_policy(target="portal")) is False
    assert pe.cloud_fallback_allowed(_policy(target="portal_then_cloud")) is False
    assert pe.cloud_fallback_allowed(_policy(target="portal_then_cloud", cloud=False)) is False
    assert pe.cloud_fallback_allowed(_policy(target="portal_then_cloud", cloud=True)) is True


def test_env_overrides_target(env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTAL_ESCALATION_TARGET", "portal")
    assert pe.escalation_target(_policy()) == "portal"
    monkeypatch.setenv("PORTAL_ESCALATION_TARGET", "bogus")
    assert pe.escalation_target(_policy(target="portal")) == "cloud"


def test_seat_map_override_and_fallback(env: None) -> None:
    policy = _policy(seats={"code": ["ws-a", "ws-b"], "security": "ws-sec", "bad": [1, ""]})
    seats = pe.portal_seats_map(policy)
    assert seats["code"] == ["ws-a", "ws-b"]
    assert seats["security"] == ["ws-sec"]
    assert "bad" not in seats
    dispatcher = _REAL_DISPATCHER(seats, engine_factory=_EngineFactory())
    assert dispatcher.seat_for("code", 1) == "ws-a"
    assert dispatcher.seat_for("code", 2) == "ws-b"
    assert dispatcher.seat_for("code", 9) == "ws-b"
    assert dispatcher.seat_for("security", 1) == "ws-sec"
    assert dispatcher.seat_for("unknown-kind", 1) == "ws-a"
    assert dispatcher.seat_for("bad", 1) == "ws-a"


def test_dispatcher_success_records_seat_and_answer(env: None, tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text("# repair brief\nfix the boom\n", encoding="utf-8")
    factory = _EngineFactory(reply="## RESULT\nthe fix\n")
    dispatcher = _REAL_DISPATCHER(engine_factory=factory)
    lane = dispatcher.run(
        role="esc-job-1-1", tier="portal", kind="code", brief=brief, repo=tmp_path, attempt=1
    )
    assert lane.exit_code == 0
    assert lane.tier == "portal"
    assert lane.model == "auto-coding"
    assert lane.status == "done"
    assert lane.worktree is None
    assert lane.result_text == "## RESULT\nthe fix\n"
    body = factory.engines["auto-coding"].calls[0]
    assert body["model"] == "auto-coding"
    assert body["stream"] is True
    assert "fix the boom" in body["messages"][-1]["content"]
    assert "test-key-123" not in lane.result_text


@pytest.mark.parametrize("fault", ["raise", "empty"])
def test_dispatcher_faults_are_failed_attempts(env: None, tmp_path: Path, fault: str) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text("brief\n", encoding="utf-8")
    factory = _EngineFactory(
        reply="" if fault == "empty" else "ok",
        error=RuntimeError("connection refused") if fault == "raise" else None,
    )
    dispatcher = _REAL_DISPATCHER(engine_factory=factory)
    lane = dispatcher.run(
        role="esc-job-1-2", tier="portal", kind="security", brief=brief, repo=tmp_path, attempt=2
    )
    assert lane.exit_code == 1
    assert lane.status == "error"
    assert lane.model == "auto-reasoning::deep"
    assert lane.worktree is None
    assert "auto-reasoning::deep" in lane.result_text


def test_dispatcher_wire_url_auth_and_model(
    env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class _Stream:
        def __enter__(self) -> _Stream:
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self) -> Any:
            return iter(['data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]"])

    def fake_stream(method: str, url: str, **kwargs: Any) -> _Stream:
        captured.update({"method": method, "url": url, **kwargs})
        return _Stream()

    monkeypatch.setattr(httpx, "stream", fake_stream)
    brief = tmp_path / "brief.md"
    brief.write_text("brief body\n", encoding="utf-8")
    dispatcher = _REAL_DISPATCHER()
    lane = dispatcher.run(
        role="esc-job-1-1", tier="portal", kind="code", brief=brief, repo=tmp_path
    )
    assert lane.exit_code == 0
    assert lane.result_text == "ok"
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:9099/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key-123"
    assert captured["json"]["model"] == "auto-coding"
    assert "test-key-123" not in json.dumps(captured["json"])
    monkeypatch.setenv("PIPELINE_URL", "http://localhost:9099/v1/")
    dispatcher = _REAL_DISPATCHER()
    dispatcher.run(role="esc-job-1-2", tier="portal", kind="code", brief=brief, repo=tmp_path)
    assert captured["url"] == "http://localhost:9099/v1/chat/completions"


def test_portal_target_routes_by_kind_and_never_touches_cloud(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, tasks, item, run = harness
    factory = _EngineFactory()
    hook, cloud, verdicts = _hook(harness, _policy(target="portal"), factory, monkeypatch)
    assert hook(item, run) == "held"
    assert factory.seats_called() == ["auto-coding"]
    assert cloud.calls == []
    assert verdicts == []
    answer = tasks / "job-1" / "portal-1.md"
    assert answer.is_file()
    assert "## RESULT" in answer.read_text(encoding="utf-8")
    events = hook.escalator.ledger.events("job-1")
    seat_events = [e for e in events if e["event"] == "portal_seat"]
    assert len(seat_events) == 1
    assert json.loads(seat_events[0]["detail_json"])["seat"] == "auto-coding"
    assert events[-1]["event"] == "held"
    receipt = json.loads((tasks / "job-1" / "receipt.json").read_text(encoding="utf-8"))
    assert any(e["event"] == "portal_seat" for e in receipt["escalations"])


def test_portal_target_security_kind_uses_security_seat(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, _tasks, item, run = harness
    item["plan_json"] = json.dumps(
        {"id": "job-1", "purpose": "detection compliance security review", "steps": []}
    )
    factory = _EngineFactory()
    hook, cloud, verdicts = _hook(harness, _policy(target="portal"), factory, monkeypatch)
    assert hook(item, run) == "held"
    assert factory.seats_called() == ["auto-security"]
    assert cloud.calls == []
    assert verdicts == []


def test_portal_failures_climb_the_ladder_then_park_without_cloud(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, tasks, item, run = harness
    factory = _EngineFactory(error=RuntimeError("pipeline down"))
    hook, cloud, verdicts = _hook(harness, _policy(target="portal"), factory, monkeypatch)
    assert hook(item, run) == "parked"
    assert factory.seats_called() == ["auto-coding", "auto-reasoning::deep"]
    assert len(factory.engines["auto-reasoning::deep"].calls) == 2
    assert cloud.calls == []
    assert verdicts == []
    events = hook.escalator.ledger.events("job-1")
    assert sum(1 for e in events if e["event"] == "portal_seat") == 3
    assert events[-1]["event"] == "parked"
    assert (tasks / "job-1" / "portal-3.md").is_file()


def test_portal_then_cloud_falls_back_only_after_portal_failures(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, _tasks, item, run = harness
    factory = _EngineFactory(error=RuntimeError("pipeline down"))
    policy = _policy(target="portal_then_cloud", cloud=True)
    hook, cloud, _verdicts = _hook(harness, policy, factory, monkeypatch)
    assert hook(item, run) == "parked"
    assert factory.seats_called() == ["auto-coding", "auto-reasoning::deep"]
    assert len(cloud.calls) == 1
    assert cloud.calls[0]["tier"] == "escalate"
    assert cloud.calls[0]["attempt"] == 3


def test_portal_then_cloud_success_holds_without_cloud(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, _tasks, item, run = harness
    factory = _EngineFactory()
    policy = _policy(target="portal_then_cloud", cloud=True)
    hook, cloud, verdicts = _hook(harness, policy, factory, monkeypatch)
    assert hook(item, run) == "held"
    assert cloud.calls == []
    assert verdicts == []


def test_portal_then_cloud_without_personal_cloud_stays_local(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, _tasks, item, run = harness
    factory = _EngineFactory(error=RuntimeError("pipeline down"))
    hook, cloud, verdicts = _hook(
        harness, _policy(target="portal_then_cloud", cloud=False), factory, monkeypatch
    )
    assert hook(item, run) == "parked"
    assert len(cloud.calls) == 0
    assert verdicts == []
    assert sum(len(e.calls) for e in factory.engines.values()) == 3


def test_legacy_default_preserves_the_cloud_ladder(
    harness: tuple[Path, Path, dict[str, Any], QueueRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, _tasks, item, run = harness
    factory = _EngineFactory()
    hook, cloud, _verdicts = _hook(harness, _policy(), factory, monkeypatch)
    assert hook.escalator.portal_dispatcher is None
    assert hook(item, run) == "parked"
    assert [call["tier"] for call in cloud.calls] == ["auto", "auto", "escalate"]
    assert factory.engines == {}


def test_build_escalator_wires_configured_portal_seats(
    harness: tuple[Path, Path, dict[str, Any], QueueRun], env: None
) -> None:
    repo, tasks, _item, _run = harness
    policy = _policy(target="portal", seats={"code": ["ws-a", "ws-b"]})
    hook = build_escalator(tasks, repo, None, policy)
    assert hook is not None
    dispatcher = hook.escalator.portal_dispatcher
    assert isinstance(dispatcher, _REAL_DISPATCHER)
    assert dispatcher.seat_for("code", 1) == "ws-a"
    assert dispatcher.seat_for("code", 2) == "ws-b"
    assert hook.escalator.cloud_fallback is False
    assert build_escalator(tasks, repo, None, {"escalation": {"enabled": False}}) is None
