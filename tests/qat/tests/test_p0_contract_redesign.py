"""Regression tests for the QAT P0 contract corrections."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from tests.qat import gate, hardening, preflight, report, runner, scenarios
from tests.qat.config import McpFleetEntry
from tests.qat.models import QATResult, QATScenario, Status
from tests.qat.owui_client import OWUIClient

from .test_config_and_scenarios import make_discovery, make_settings


def test_owui_native_chat_payload_and_trace_envelope() -> None:
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    captured: dict[str, object] = {}
    assistant_id = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal assistant_id
        if request.url.path == "/api/v1/chats/new":
            created = json.loads(request.content)
            captured["created"] = created
            history = created["chat"]["history"]
            assert history["currentId"]
            return httpx.Response(201, json={"id": "chat-1"})
        if request.url.path == "/api/chat/completions":
            body = json.loads(request.content)
            captured["completion"] = body
            assistant_id = body["id"]
            return httpx.Response(200, headers={"X-Correlation-ID": "corr-1"}, json={})
        if request.url.path == "/api/tasks/chat/chat-1":
            return httpx.Response(200, json={"task_ids": []})
        if request.url.path == "/api/v1/chats/chat-1":
            return httpx.Response(
                200,
                json={
                    "chat": {
                        "history": {
                            "messages": {
                                assistant_id: {
                                    "id": assistant_id,
                                    "role": "assistant",
                                    "content": "Created /api/v1/files/01234567-89ab-cdef-0123-456789abcdef/content/result.wav",
                                    "files": [
                                        {
                                            "url": "/api/v1/files/01234567-89ab-cdef-0123-456789abcdef/content/result.wav"
                                        }
                                    ],
                                    "info": {
                                        "model": "served-model",
                                        "tool_calls": [{"name": "remember"}],
                                    },
                                    "done": True,
                                }
                            }
                        }
                    }
                },
            )
        if request.url.path == "/v1/trace":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [{"correlation_id": "corr-1", "workspace": "auto"}],
                },
            )
        if request.url.path == "/v1/trace/corr-1":
            return httpx.Response(
                200,
                json={
                    "correlation_id": "corr-1",
                    "spans": [{"name": "tool.completed", "tool": "remember", "outcome": "ok"}],
                },
            )
        return httpx.Response(404)

    client = OWUIClient(settings, httpx.MockTransport(handler))
    chat_id = client.create_chat("qat-token", "auto", "QAT test", prompt="remember this")
    response = client.send_turn(
        "qat-token", chat_id, "auto", "remember this", ("server:mcp:remember",), True
    )
    outcome = client.poll_turn(
        "qat-token",
        chat_id,
        max_wait_s=2,
        correlation_id=response.headers.get("X-Correlation-ID"),
        model_slug="auto",
        turn_started_at=0,
    )

    created = captured["created"]["chat"]
    messages = created["history"]["messages"]
    user = next(m for m in messages.values() if m["role"] == "user")
    assistant = next(m for m in messages.values() if m["role"] == "assistant")
    assert user["childrenIds"] == [assistant["id"]]
    assert assistant["parentId"] == user["id"]
    assert assistant["childrenIds"] == [] and assistant["done"] is False
    body = captured["completion"]
    assert body["stream"] is True
    assert body["id"] == assistant["id"]
    assert body["chat_id"] == "chat-1"
    assert body["session_id"].startswith("portal-qat-")
    assert body["features"] == {
        "web_search": False,
        "code_interpreter": False,
        "image_generation": False,
        "memory": False,
    }
    assert body["tool_ids"] == ["server:mcp:remember"]
    assert body["params"] == {"function_calling": True}
    assert outcome.done is True
    assert outcome.served_model == "served-model"
    assert outcome.artifact_urls == (
        "/api/v1/files/01234567-89ab-cdef-0123-456789abcdef/content/result.wav",
    )
    assert outcome.trace["spans"][0]["name"] == "tool.completed"


def test_owui_followup_sends_full_branch_messages() -> None:
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/chats/new":
            return httpx.Response(201, json={"id": "chat-2"})
        if request.url.path == "/api/chat/completions":
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    client = OWUIClient(settings, httpx.MockTransport(handler))
    chat_id = client.create_chat("token", "auto", "continuity", prompt="ORCHID-9")
    prior = [
        {"role": "user", "content": "Remember ORCHID-9."},
        {"role": "assistant", "content": "I will remember ORCHID-9."},
    ]
    client.send_turn("token", chat_id, "auto", "What was the marker?", prior_messages=prior)
    assert bodies[0]["messages"] == prior + [{"role": "user", "content": "What was the marker?"}]


def test_artifact_bearer_token_is_sent_only_to_owui_origin() -> None:
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth.append(request.headers.get("authorization"))
        return httpx.Response(200, content=b"artifact")

    client = OWUIClient(settings, httpx.MockTransport(handler))
    assert client.download_artifact("secret", "/api/v1/files/01234567/content/a.wav") == b"artifact"
    assert client.download_artifact("secret", "https://third.example/a.wav") == b"artifact"
    assert auth == ["Bearer secret", None]


def test_archive_creates_nested_qat_date_folders() -> None:
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    creates: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/folders/" and request.method == "GET":
            return httpx.Response(200, json=[])
        if request.url.path == "/api/v1/folders/" and request.method == "POST":
            body = json.loads(request.content)
            creates.append(body)
            return httpx.Response(201, json={"id": f"folder-{len(creates)}"})
        if request.url.path == "/api/v1/chats/chat-1/folder":
            assert json.loads(request.content) == {"folder_id": "folder-2"}
            return httpx.Response(200)
        return httpx.Response(404)

    client = OWUIClient(settings, httpx.MockTransport(handler))
    assert client.archive_chat("token", "chat-1", "2026-11-22") == (True, "archived")
    assert creates == [{"name": "QAT"}, {"name": "2026-11-22", "parent_id": "folder-1"}]


def test_omlx_status_ignores_virtual_entries() -> None:
    settings = make_settings(Path("/tmp"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "models": [
                    {"id": "resident-model", "loaded": True},
                    {"id": "markitdown", "loaded": True},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _result, names = gate.omlx_residency(client, settings)
    assert names == ["resident-model"]


def test_omlx_unload_uses_admin_route_and_escaped_model_name() -> None:
    settings = make_settings(Path("/tmp"), OMLX_API_KEY="omlx-token")
    paths: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.raw_path)
        assert request.headers["authorization"] == "Bearer omlx-token"
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = gate.evict_omlx(client, settings, ["family/model"])
    assert result.status is Status.PASS
    assert paths == [b"/admin/api/models/family%2Fmodel/unload"]


def test_ollama_eviction_requires_success_and_empty_residency() -> None:
    settings = make_settings(Path("/tmp"))

    def failed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(failed)) as client:
        assert gate.evict_ollama(client, settings, ["q:9b"]).status is Status.FAIL

    def resident(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "q:9b"}]})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(resident)) as client:
        result = gate.evict_ollama(client, settings, ["q:9b"])
    assert result.status is Status.FAIL


def test_vm_stat_speculative_pages_are_not_used_memory() -> None:
    output = (
        "Pages free: 10.\nPages active: 20.\nPages inactive: 30.\n"
        "Pages speculative: 100.\nPages wired down: 10.\n"
    )
    used_pct, _ = gate.parse_vm_stat(output)
    assert used_pct == pytest.approx((20 + 10) / (10 + 20 + 30 + 100 + 10) * 100)


def test_hardening_negative_probes_have_case_specific_contracts() -> None:
    settings = make_settings(Path("/tmp"))
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            body = (
                json.loads(request.content)
                if request.headers.get("content-type", "").startswith("application/json")
                else {}
            )
        except ValueError:
            return httpx.Response(400)
        prompt = body.get("messages", [{}])[0].get("content", "") if body else ""
        if isinstance(prompt, str) and len(prompt) > 4_200_000:
            seen["oversized_bytes"] = len(request.content)
            return httpx.Response(413)
        if body.get("portal_strict_seat") is True:
            seen["strict"] = True
            return httpx.Response(404)
        if prompt == "":
            return httpx.Response(422)
        return httpx.Response(400)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = {r.scenario_id: r for r in hardening._negative_probes(settings, client)}
    assert all(
        rows[f"s1-neg-{name}"].status is Status.PASS
        for name in ("empty-prompt", "oversized-prompt", "invalid-slug", "malformed-json")
    )
    assert seen["strict"] is True
    assert seen["oversized_bytes"] > 4_200_000


def test_health_all_accepts_ollama_tags_and_lists_exact_failures() -> None:
    settings = make_settings(Path("/tmp"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "pipeline": {"status": "ok"},
                "ollama": {"models": []},
                "data": {"status": "error", "detail": "down"},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = hardening._health_all(settings, client)
    assert result.status is Status.WARN
    assert "data" in result.detail and "error" in result.detail
    assert result.evidence["non_ok"] == {"data": "error"}


def test_browser_redaction_404_is_not_a_pass() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
        result = hardening._browser_redaction("http://localhost:8923", client)
    assert result.status is Status.FAIL


def test_run_cmd_preserves_complete_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = '{"result":"' + ("x" * 3000) + '"}'
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, payload, ""),
    )
    code, output = preflight.run_cmd(["python"], tmp_path)
    assert code == 0
    assert len(output) == len(payload)
    assert json.loads(output)["result"].endswith("x")


def test_trace_preflight_reports_exact_failed_and_warned_hops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "sections": [
            {"key": "host", "hops": [{"name": "uname", "status": "PASS"}]},
            {
                "key": "pins",
                "hops": [
                    {"name": "seat-a", "status": "FAIL"},
                    {"name": "seat-b", "status": "WARN"},
                ],
            },
        ]
    }
    monkeypatch.setattr(preflight, "run_cmd", lambda *args, **kwargs: (1, json.dumps(payload)))
    result = preflight.run_trace_sections(make_settings(Path("/tmp")))
    assert result.status is Status.FAIL
    assert "pins/seat-a" in result.detail and "pins/seat-b" in result.detail
    assert result.evidence["failed_hops"] == ["pins/seat-a"]
    assert result.evidence["warned_hops"] == ["pins/seat-b"]


def test_pipeline_chat_none_content_is_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_client = httpx.Client

    def factory(**kwargs: object) -> httpx.Client:
        kwargs.pop("timeout", None)
        return real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"choices": [{"message": {"content": None}}]}
                )
            )
        )

    monkeypatch.setattr(runner.httpx, "Client", factory)
    scenario = QATScenario(
        "pipeline-none",
        "Pipeline None",
        3,
        "security_canonical",
        1,
        "auto-security::blue",
        kind="pipeline",
        prompts=("test",),
    )
    result = runner._run_pipeline_chat(make_settings(tmp_path), scenario)
    assert result.status is Status.FAIL


def test_lab_requirement_missing_or_warn_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = make_settings(tmp_path)
    scenario = QATScenario(
        "lab", "lab", 3, "security_adversarial", 1, "auto", kind="infra", requires=("p0-lab-ready",)
    )
    state = runner.RunState(settings, tmp_path, make_discovery())
    assert (
        runner._execute_one(
            settings, scenario, state, runner.RunnerOptions({3}, set(), set())
        ).status
        is Status.SKIP
    )
    state.results.append(QATResult("p0-lab-ready", Status.WARN))
    assert (
        runner._execute_one(
            settings, scenario, state, runner.RunnerOptions({3}, set(), set())
        ).status
        is Status.SKIP
    )


def test_reports_default_operator_verdict_to_pending_and_list_unclassified_failures(
    tmp_path: Path,
) -> None:
    scenario = QATScenario("fail-row", "failure", 2, "media_heavy", 1, "auto")
    result = QATResult("fail-row", Status.FAIL, "unclassified defect")
    html_path = report.write_review_html(tmp_path, [scenario], [result])
    md_path = report.write_markdown(tmp_path, make_discovery(), [scenario], [result])
    assert "<option selected>PENDING</option>" in html_path.read_text()
    assert "| fail-row | UNCLASSIFIED |" in md_path.read_text()


def test_dry_run_prints_only_filtered_scenarios(capsys: pytest.CaptureFixture[str]) -> None:
    opts = runner.RunnerOptions({2}, {"media_heavy"}, set(), dry_run=True)
    runner.run_selected(make_settings(Path("/tmp")), opts)
    output = capsys.readouterr().out
    assert "stage 2 · phase media_heavy" in output
    assert "stage 2 · phase smoke_routing" not in output
    assert "s2-p6-" in output


def test_worksheet_operations_do_not_execute_scenarios(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        runner, "_execute", lambda *args, **kwargs: pytest.fail("live execution called")
    )
    emit = runner.RunnerOptions(
        {4}, {"adaptive_deep"}, set(), emit_worksheets=True, output_dir=tmp_path
    )
    runner.run_selected(make_settings(tmp_path), emit)
    assert list((tmp_path / "worksheets").glob("*.json"))


def test_runner_checkpoints_each_completed_scenario(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = make_settings(tmp_path)
    plan = [
        QATScenario("one", "one", 2, "phase", 1, "auto"),
        QATScenario("two", "two", 2, "phase", 2, "auto"),
    ]
    state = runner.RunState(settings, tmp_path, make_discovery(), scenarios=plan)
    seen: list[str] = []

    def execute(
        settings_arg: object, scenario: QATScenario, state_arg: object, opts: object
    ) -> QATResult:
        if scenario.scenario_id == "two":
            seen.extend(
                json.loads(line)["scenario_id"]
                for line in (tmp_path / "results.jsonl").read_text().splitlines()
            )
        return QATResult(scenario.scenario_id, Status.PASS)

    monkeypatch.setattr(runner, "_execute_one", execute)
    monkeypatch.setattr(
        runner.gate, "run_gate", lambda *args, **kwargs: type("Gate", (), {"blocked": False})()
    )
    runner._execute(settings, plan, state, runner.RunnerOptions({2}, set(), set()), {})
    assert seen == ["one"]


def test_registry_hunt_timeout_and_separate_mcp_contracts(tmp_path: Path) -> None:
    discovery = make_discovery()
    discovery.mcp_fleet = (*discovery.mcp_fleet, McpFleetEntry("unifi", "unifi", 8949, "security"))
    registry = scenarios.build_registry(make_settings(tmp_path), discovery)
    hunt = [
        s
        for s in registry
        if s.phase == "security_hunt" and s.kind == "chat" and s.scenario_id.startswith("s3-hunt-")
    ]
    prompt = " ".join(p for s in hunt for p in s.prompts).lower()
    assert "windows:security" in prompt and "windows:sysmon" in prompt and "fgt_traffic" in prompt
    assert "earliest=" in prompt and "latest=" in prompt
    assert all(s.expected_tools for s in hunt)
    assert any(s.scenario_id.endswith("unifi-readonly") and "unifi" in s.tags for s in registry)
    assert not any(
        s.scenario_id.endswith("proxmox-readonly") and "unifi" in s.tags for s in registry
    )
    by_id = {s.scenario_id: s for s in registry}
    assert by_id["s2-p3-auto-coding::cad"].timeout_s == 600
    assert by_id["s2-p6-auto-audio::image"].timeout_s == 900
    assert by_id["s2-p6-auto-audio::video"].timeout_s == 1800
    assert by_id["s2-p6-auto-audio::music"].timeout_s == 900
    assert "s2-p6-auto-audio-stt" in by_id and "s2-p6-auto-audio-tts" in by_id
