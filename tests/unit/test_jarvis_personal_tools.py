"""Slice S2: the allowlisted local file read and the Pipeline tool pre-flight. No network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import (
    CONFIRM_TOOLS,
    CORE_TOOLS,
    FAST_WORKSPACE,
    PersonalRoute,
    route_personal_task,
)
from portal.modules.orchestration.personal_runner import (
    Completion,
    ToolsUnavailableError,
    _bundle_name,
    _preflight,
    _tool_names_payload,
    poll_personal_tasks,
)
from portal.modules.orchestration.personal_tools import (
    LOCAL_TOOLS,
    READ_LOCAL_MAX_BYTES,
    run_read_tool,
    tool_bundle,
    tool_schema,
)

# ── a hermetic pair of allowlisted roots ─────────────────────────────────────


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The workspace root and the sweep root, both under tmp_path."""
    from portal.modules.orchestration import personal_tools

    workspace = tmp_path / "AI_Output"
    sweep = tmp_path / "portal5" / "security"
    workspace.mkdir()
    sweep.mkdir(parents=True)
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(workspace))
    monkeypatch.setattr(personal_tools, "SWEEP_DIR", sweep)
    return workspace, sweep


def _read(path: str, **arguments: Any) -> dict[str, Any]:
    return json.loads(run_read_tool("read_local_file", {"path": path, **arguments}, Path("/")))


# ── read_local_file: the reads it must serve (S2 live proof 2) ───────────────


def test_read_local_file_reads_a_workspace_file(roots: tuple[Path, Path]) -> None:
    workspace, _sweep = roots
    (workspace / "generated").mkdir()
    (workspace / "generated" / "notes.md").write_text("MAL count: 3\n", encoding="utf-8")

    out = _read(str(workspace / "generated" / "notes.md"))

    assert out["path"] == str(workspace / "generated" / "notes.md")
    assert out["content"] == "MAL count: 3\n"
    assert out["bytes"] == 13
    assert out["truncated"] is False


def test_read_local_file_reads_the_security_sweep_root(roots: tuple[Path, Path]) -> None:
    _workspace, sweep = roots
    report = sweep / "security_sweep_20261120.md"
    report.write_text("# Security sweep\n\n- MAL: 2\n", encoding="utf-8")

    out = _read(str(report))

    assert out["content"].startswith("# Security sweep")
    assert "MAL: 2" in out["content"]


def test_read_local_file_accepts_a_relative_and_a_workspace_path(
    roots: tuple[Path, Path],
) -> None:
    workspace, _sweep = roots
    (workspace / "generated").mkdir()
    (workspace / "generated" / "a.txt").write_text("alpha", encoding="utf-8")

    assert _read("generated/a.txt")["content"] == "alpha"
    assert _read("/workspace/generated/a.txt")["content"] == "alpha"


# ── read_local_file: the reads it must refuse ────────────────────────────────


@pytest.mark.parametrize(
    "path",
    ["generated/../../etc/passwd", "../AI_Output/generated/a.txt", "~/.ssh/id_rsa", "/etc/passwd"],
)
def test_read_local_file_refuses_paths_outside_the_roots(
    roots: tuple[Path, Path], path: str
) -> None:
    workspace, _sweep = roots
    (workspace / "generated").mkdir()
    (workspace / "generated" / "a.txt").write_text("alpha", encoding="utf-8")

    with pytest.raises(PermissionError):
        _read(path)


def test_read_local_file_refuses_a_relative_walk_but_not_a_legal_name(
    roots: tuple[Path, Path],
) -> None:
    workspace, _sweep = roots
    (workspace / "dot..dot.txt").write_text("legal", encoding="utf-8")

    assert _read("dot..dot.txt")["content"] == "legal"
    with pytest.raises(PermissionError):
        _read("../AI_Output/dot..dot.txt")


def test_read_local_file_reports_a_missing_file_without_raising(
    roots: tuple[Path, Path],
) -> None:
    out = _read("generated/missing.md")

    assert "no readable file" in str(out["error"])


# ── read_local_file: the size bound ──────────────────────────────────────────


def test_read_local_file_caps_the_window_at_the_module_bound(roots: tuple[Path, Path]) -> None:
    workspace, _sweep = roots
    (workspace / "big.txt").write_bytes(b"x" * (READ_LOCAL_MAX_BYTES + 1024))

    out = _read("big.txt")

    assert len(out["content"]) == READ_LOCAL_MAX_BYTES
    assert out["bytes"] == READ_LOCAL_MAX_BYTES + 1024
    assert out["truncated"] is True


def test_read_local_file_honours_a_smaller_max_bytes(roots: tuple[Path, Path]) -> None:
    workspace, _sweep = roots
    (workspace / "small.txt").write_text("0123456789", encoding="utf-8")

    out = _read("small.txt", max_bytes=4)

    assert out["content"] == "0123"
    assert out["truncated"] is True
    with pytest.raises(ValueError):
        _read("small.txt", max_bytes=0)


# ── read_local_file: registration ────────────────────────────────────────────


def test_read_local_file_is_a_local_read_tool_never_a_confirm_tool() -> None:
    assert "read_local_file" in LOCAL_TOOLS
    assert "read_local_file" in CORE_TOOLS
    assert "read_local_file" not in CONFIRM_TOOLS


def test_the_router_offers_read_local_file_on_every_route() -> None:
    """No planner steers the read: the core bundle carries it, sweep or not."""
    sweep = route_personal_task("read the newest security sweep file in ~/.portal5/security")
    plain = route_personal_task("what is the queue status")

    assert "read_local_file" in sweep.tools
    assert "read_local_file" in plain.tools
    assert sweep.bundle_name == "core+documents"


def test_read_local_file_schema_names_the_path_argument() -> None:
    parameters = tool_schema("read_local_file")["function"]["parameters"]

    assert parameters["required"] == ["path"]
    assert set(parameters["properties"]) == {"path", "max_bytes"}


def test_security_sweep_stays_a_convenience_wrapper() -> None:
    assert "security_sweep" in LOCAL_TOOLS
    assert "security_sweep" in route_personal_task("show me the security sweep").tools


# ── the pre-flight: a domain bundle absent from the Pipeline ─────────────────


PROXMOX_REQUEST = "list the Proxmox VMs that are currently stopped"
PROXMOX_BUNDLE = sorted(
    name for name in route_personal_task(PROXMOX_REQUEST).tools if name.startswith("proxmox_")
)
# The Pipeline serves the core tools the registry normally holds; only proxmox is unwired.
CORE_PIPELINE_TOOLS = frozenset(
    name
    for name in route_personal_task(PROXMOX_REQUEST).tools
    if name not in LOCAL_TOOLS and not name.startswith("proxmox_")
)


class _Notices:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append((task_id, kind, message))


class _Caller:
    def __init__(self, replies: list[Completion], registered: frozenset[str] | None = None) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []
        self.registered = registered

    def complete(self, body: dict[str, Any]) -> Completion:
        self.bodies.append(json.loads(json.dumps(body)))
        return self.replies.pop(0)

    def tool_names(self) -> frozenset[str] | None:
        return self.registered


class _CallerWithoutProbe(_Caller):
    """A caller from before the pre-flight existed: it cannot be asked."""

    tool_names = None  # type: ignore[assignment]


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def start(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        raise AssertionError("a wiring fault must never reach a cloud lane")

    run = start


def _no_memory(query: str) -> str:
    return ""


def _receipt(root: Path) -> dict[str, Any]:
    path = next(root.glob("*/receipt.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def test_an_unwired_mcp_blocks_the_task_before_any_model_call(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, PROXMOX_REQUEST)
    caller = _Caller([], registered=CORE_PIPELINE_TOOLS)
    dispatcher = _RecordingDispatcher()

    run = poll_personal_tasks(
        tmp_path, _Notices(), caller, dispatcher=dispatcher, recall=_no_memory
    )

    assert run is not None and run.status == "blocked"
    receipt = _receipt(tmp_path)
    assert "proxmox tools unavailable on Pipeline" in receipt["error"]
    assert "proxmox_list_vms" in receipt["error"]
    assert receipt["preflight"] == {"checked": True, "missing": PROXMOX_BUNDLE}
    # The receipt records the route beside the pre-flight, and the loop never ran.
    assert receipt["route"] == {
        "bundle": "core+proxmox",
        "workspace": FAST_WORKSPACE,
        "tools": sorted(route_personal_task(PROXMOX_REQUEST).tools),
    }
    assert caller.bodies == []
    assert not list(tmp_path.glob("*/attempts/local-*"))
    assert dispatcher.calls == []


def test_the_unavailable_check_is_terminal_and_never_retried(tmp_path: Path) -> None:
    """A second poll of the same task does not re-run it: the row is blocked, not queued."""
    telegram_do_reply(tmp_path, 1, PROXMOX_REQUEST)
    first = _Caller([], registered=CORE_PIPELINE_TOOLS)
    notices = _Notices()
    poll_personal_tasks(tmp_path, notices, first, recall=_no_memory)

    assert poll_personal_tasks(tmp_path, notices, _Caller([]), recall=_no_memory) is None
    assert any("unavailable on Pipeline" in message for _tid, _kind, message in notices.messages)


def test_a_registered_domain_tool_passes_the_preflight_and_runs(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, PROXMOX_REQUEST)
    caller = _Caller(
        [Completion("vm 100 is stopped.", (), 1, ("proxmox_list_vms",))],
        registered=CORE_PIPELINE_TOOLS | frozenset(PROXMOX_BUNDLE),
    )

    run = poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)

    assert run is not None and run.status == "done"
    receipt = _receipt(tmp_path)
    assert receipt["preflight"] == {"checked": True, "missing": []}
    assert receipt["tool_calls"] == ["proxmox_list_vms"]


def test_a_failed_attempt_receipt_also_records_the_preflight(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, PROXMOX_REQUEST)
    caller = _Caller(
        [Completion("", (), 0)],
        registered=CORE_PIPELINE_TOOLS | frozenset(PROXMOX_BUNDLE),
    )

    poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)

    attempt = json.loads(
        next(tmp_path.glob("*/attempts/local-1/receipt.json")).read_text(encoding="utf-8")
    )
    assert attempt["preflight"] == {"checked": True, "missing": []}
    assert attempt["route"]["bundle"] == "core+proxmox"


def test_a_caller_that_cannot_be_asked_skips_the_preflight(tmp_path: Path) -> None:
    """Unknown availability is not a failure: the loop runs and its audit is the receipt."""
    telegram_do_reply(tmp_path, 1, PROXMOX_REQUEST)
    caller = _CallerWithoutProbe([Completion("vm 100 is stopped.", (), 1, ("proxmox_list_vms",))])

    run = poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)

    assert run is not None and run.status == "done"
    assert _receipt(tmp_path)["preflight"]["checked"] is False


def test_a_route_of_local_tools_never_asks_the_pipeline() -> None:
    """A local read needs no registry: no probe, no HTTP, checked=False."""
    asked: list[int] = []

    class _Counter:
        def tool_names(self) -> frozenset[str]:
            asked.append(1)
            return frozenset()

    out = _preflight(
        _Counter(),  # type: ignore[arg-type]
        PersonalRoute(FAST_WORKSPACE, frozenset({"queue_status"}), "core"),
    )

    assert out == {"checked": False, "missing": []}
    assert asked == []


def test_preflight_raises_with_the_bundle_and_the_missing_names() -> None:
    class _RegistryOnly:
        def tool_names(self) -> frozenset[str]:
            return frozenset({"workspace_files"})

    route = PersonalRoute(
        FAST_WORKSPACE, frozenset({"create_word_document", "proxmox_list_vms"}), "core+documents"
    )

    with pytest.raises(ToolsUnavailableError) as caught:
        _preflight(route=route, caller=_RegistryOnly())  # type: ignore[arg-type]

    assert str(caught.value).startswith("personal tools unavailable on Pipeline: ")
    assert caught.value.missing == ("create_word_document", "proxmox_list_vms")
    assert caught.value.as_receipt() == {
        "checked": True,
        "missing": ["create_word_document", "proxmox_list_vms"],
    }


@pytest.mark.parametrize(
    ("name", "bundle"),
    [
        ("proxmox_list_vms", "proxmox"),
        ("git_status", "git"),
        ("unifi_list_devices", "unifi"),
        ("browser_navigate", "browser"),
        ("create_word_document", "documents"),
        ("get_pipeline_status", "get"),
    ],
)
def test_tool_bundle_names_the_owning_mcp(name: str, bundle: str) -> None:
    assert tool_bundle(name) == bundle


def test_one_bundle_in_a_missing_set_is_named_two_are_generalised() -> None:
    assert _bundle_name(["proxmox_list_vms", "proxmox_list_nodes"]) == "proxmox"
    assert _bundle_name(["proxmox_list_vms", "git_status"]) == "personal"


def test_tool_names_payload_reads_the_endpoint_shape() -> None:
    assert _tool_names_payload({"object": "list", "data": ["a", "b"]}) == frozenset({"a", "b"})
    assert _tool_names_payload({"object": "list", "data": []}) == frozenset()
    assert _tool_names_payload({"data": "nope"}) is None
    assert _tool_names_payload([1, 2]) is None


# ── the local read the router now offers, end to end through the loop ────────


def test_a_read_local_file_call_is_served_by_the_runner(
    tmp_path: Path, roots: tuple[Path, Path]
) -> None:
    workspace, _sweep = roots
    (workspace / "notes.md").write_text("MAL count: 3\n", encoding="utf-8")
    telegram_do_reply(tmp_path, 1, "read ~/AI_Output/notes.md and report the MAL count")
    call = {
        "id": "c-read",
        "type": "function",
        "function": {"name": "read_local_file", "arguments": json.dumps({"path": "notes.md"})},
    }
    caller = _CallerWithoutProbe([Completion("", (call,), 0), Completion("MAL count: 3", (), 1)])

    run = poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)

    assert run is not None and run.status == "done"
    receipt = _receipt(tmp_path)
    assert "read_local_file" in receipt["route"]["tools"]
    assert receipt["tool_calls"] == ["read_local_file"]
    assert receipt["final_text"] == "MAL count: 3"


# ── the probe's wire: EngineCaller asks /v1/tools ────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    """Stands in for httpx.Client so the probe's URL, headers and status handling are tested."""

    opened: list[dict[str, Any]] = []
    reply = _FakeResponse(200, {"object": "list", "data": ["proxmox_list_vms"]})

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeResponse:
        _FakeClient.opened.append({"url": url, "headers": headers, "kwargs": self.kwargs})
        return _FakeClient.reply


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    from portal.modules.orchestration import personal_runner

    _FakeClient.opened = []
    _FakeClient.reply = _FakeResponse(200, {"object": "list", "data": ["proxmox_list_vms"]})
    monkeypatch.setattr(personal_runner.httpx, "Client", _FakeClient)
    return _FakeClient


def test_engine_caller_reads_the_registry_with_the_pipeline_key(
    probe: type[_FakeClient],
) -> None:
    from portal.modules.orchestration.personal_runner import EngineCaller

    names = EngineCaller("http://127.0.0.1:9099", "secret").tool_names()

    assert names == frozenset({"proxmox_list_vms"})
    assert probe.opened[0]["url"] == "http://127.0.0.1:9099/v1/tools"
    assert probe.opened[0]["headers"] == {"Authorization": "Bearer secret"}


def test_engine_caller_builds_the_tools_url_from_a_v1_base(probe: type[_FakeClient]) -> None:
    from portal.modules.orchestration.personal_runner import EngineCaller

    EngineCaller("http://127.0.0.1:9099/v1", "secret").tool_names()

    assert probe.opened[0]["url"] == "http://127.0.0.1:9099/v1/tools"


def test_an_unauthenticated_or_stale_pipeline_leaves_availability_unknown(
    probe: type[_FakeClient],
) -> None:
    from portal.modules.orchestration.personal_runner import EngineCaller

    for reply in (_FakeResponse(401, {"detail": "Invalid API key"}), _FakeResponse(404, {})):
        probe.reply = reply
        assert EngineCaller("http://127.0.0.1:9099", "secret").tool_names() is None


def test_a_connect_failure_leaves_availability_unknown(
    probe: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from portal.modules.orchestration.personal_runner import EngineCaller

    def refuses(url: str, headers: dict[str, str] | None = None) -> _FakeResponse:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(probe, "get", staticmethod(refuses))

    assert EngineCaller("http://127.0.0.1:9099", "secret").tool_names() is None


# ── the Pipeline endpoint the pre-flight reads ───────────────────────────────


def test_the_pipeline_serves_its_registered_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from portal.platform.inference import tool_registry as registry_module
    from portal.platform.inference.router import auth, handlers

    monkeypatch.setattr(
        registry_module.tool_registry, "list_tool_names", lambda: ["proxmox_list_vms"]
    )

    out = asyncio.run(
        handlers.list_registered_tools(authorization=f"Bearer {auth.PIPELINE_API_KEY}")
    )

    assert out == {"object": "list", "data": ["proxmox_list_vms"]}


def test_the_tools_endpoint_requires_the_pipeline_key() -> None:
    import asyncio

    from fastapi import HTTPException

    from portal.platform.inference.router import handlers

    with pytest.raises(HTTPException):
        asyncio.run(handlers.list_registered_tools(authorization=None))
