"""Regression tests for the QAT P0 contract corrections."""

from __future__ import annotations

import base64
import json
import struct
import subprocess
import time
import zlib
from pathlib import Path

import httpx
import pytest

from tests.qat import config as qat_config
from tests.qat import gate, hardening, preflight, report, runner, scenarios
from tests.qat.config import McpFleetEntry
from tests.qat.models import GateReport, QATResult, QATScenario, Status
from tests.qat.owui_client import OWUIClient, red_square_png

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


def test_poll_turn_returns_finished_answer_despite_lingering_tasks() -> None:
    """F12: a background title/tag task must not hold a finished answer hostage."""
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    assistant_id = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal assistant_id
        if request.url.path == "/api/v1/chats/new":
            return httpx.Response(201, json={"id": "chat-f12"})
        if request.url.path == "/api/chat/completions":
            assistant_id = json.loads(request.content)["id"]
            return httpx.Response(200, json={})
        if request.url.path == "/api/tasks/chat/chat-f12":
            return httpx.Response(200, json={"task_ids": ["title-gen-1"]})
        if request.url.path == "/api/v1/chats/chat-f12":
            return httpx.Response(
                200,
                json={
                    "chat": {
                        "history": {
                            "messages": {
                                assistant_id: {
                                    "id": assistant_id,
                                    "role": "assistant",
                                    "content": "finished answer",
                                    "done": True,
                                }
                            }
                        }
                    }
                },
            )
        if request.url.path == "/v1/trace":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    client = OWUIClient(settings, httpx.MockTransport(handler))
    chat_id = client.create_chat("qat-token", "auto", "F12", prompt="hi")
    client.send_turn("qat-token", chat_id, "auto", "hi")
    start = time.monotonic()
    outcome = client.poll_turn("qat-token", chat_id, max_wait_s=5.0)
    elapsed = time.monotonic() - start
    assert elapsed < 4.0  # the old loop slept through the whole budget first
    assert outcome.done is True
    assert outcome.text == "finished answer"


def test_poll_turn_still_times_out_when_the_answer_never_finishes() -> None:
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    assistant_id = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal assistant_id
        if request.url.path == "/api/v1/chats/new":
            return httpx.Response(201, json={"id": "chat-f12b"})
        if request.url.path == "/api/chat/completions":
            assistant_id = json.loads(request.content)["id"]
            return httpx.Response(200, json={})
        if request.url.path == "/api/tasks/chat/chat-f12b":
            return httpx.Response(200, json={"task_ids": []})
        if request.url.path == "/api/v1/chats/chat-f12b":
            return httpx.Response(
                200,
                json={
                    "chat": {
                        "history": {
                            "messages": {
                                assistant_id: {
                                    "id": assistant_id,
                                    "role": "assistant",
                                    "content": "",
                                    "done": False,
                                }
                            }
                        }
                    }
                },
            )
        return httpx.Response(404)

    client = OWUIClient(settings, httpx.MockTransport(handler))
    chat_id = client.create_chat("qat-token", "auto", "F12b", prompt="hi")
    client.send_turn("qat-token", chat_id, "auto", "hi")
    with pytest.raises(TimeoutError):
        client.poll_turn("qat-token", chat_id, max_wait_s=0.5)


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
    posts: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer omlx-token"
        if request.method == "POST":
            posts.append(request.url.raw_path)
            return httpx.Response(200, json={})
        # residency reads answer cold, confirming the eviction at once
        return httpx.Response(200, json={"models": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = gate.evict_omlx(client, settings, ["family/model"])
    assert result.status is Status.PASS
    assert posts == [b"/admin/api/models/family%2Fmodel/unload"]


def test_ollama_eviction_requires_success_and_empty_residency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(Path("/tmp"))
    monkeypatch.setattr(gate, "_poll_pause", lambda _seconds: None)
    monkeypatch.setattr(gate, "_pipeline_ollama_in_flight", lambda _name: False)
    monkeypatch.setattr(gate, "OLLAMA_EVICT_BUDGET_S", 0.0)

    def failed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(failed)) as client:
        assert gate.evict_ollama(client, settings, ["q:9b"]).status is Status.FAIL

    def resident(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={})
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "q:9b", "expires_at": "2026-11-26T04:39:04+00:00"},
                    ]
                },
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(resident)) as client:
        result = gate.evict_ollama(client, settings, ["q:9b"])
    assert result.status is Status.FAIL
    assert result.detail.startswith("Ollama models remain resident after")
    assert result.evidence["state"] == {"q:9b": "releasing"}
    assert result.evidence["expires_at"]["q:9b"] == "2026-11-26T04:39:04+00:00"
    assert result.evidence["budget_s"] == 0.0


def _ps_then_clear(hold_for: int, expires: list[str]) -> httpx.MockTransport:
    """Hold `name` in /api/ps for `hold_for` reads, then report it gone."""
    reads = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={})
        if request.url.path == "/api/ps":
            reads["n"] += 1
            if reads["n"] <= hold_for:
                stamp = expires[min(reads["n"] - 1, len(expires) - 1)]
                return httpx.Response(
                    200,
                    json={"models": [{"name": "glm-4.7-flash:Q4_K_M-ctx24k", "expires_at": stamp}]},
                )
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_ollama_eviction_waits_for_an_in_flight_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(Path("/tmp"))
    monkeypatch.setattr(gate, "_poll_pause", lambda _seconds: None)
    monkeypatch.setattr(gate, "_pipeline_ollama_in_flight", lambda _name: True)
    transport = _ps_then_clear(1, ["2026-11-26T05:00:00+00:00"])
    with httpx.Client(transport=transport) as client:
        result = gate.evict_ollama(client, settings, ["glm-4.7-flash:Q4_K_M-ctx24k"])
    assert result.status is Status.PASS
    assert "in_flight" in result.detail


def test_ollama_eviction_polls_a_release_until_the_model_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(Path("/tmp"))
    monkeypatch.setattr(gate, "_poll_pause", lambda _seconds: None)
    monkeypatch.setattr(gate, "_pipeline_ollama_in_flight", lambda _name: False)
    transport = _ps_then_clear(2, ["2026-11-26T04:39:04+00:00", "2026-11-26T04:39:04+00:00"])
    with httpx.Client(transport=transport) as client:
        result = gate.evict_ollama(client, settings, ["glm-4.7-flash:Q4_K_M-ctx24k"])
    assert result.status is Status.PASS
    assert "releasing" in result.detail
    assert "in_flight" not in result.detail


def test_ollama_eviction_treats_a_blocked_unload_as_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(Path("/tmp"))
    monkeypatch.setattr(gate, "_poll_pause", lambda _seconds: None)
    monkeypatch.setattr(gate, "_pipeline_ollama_in_flight", lambda _name: False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            raise httpx.ReadTimeout("queued behind an in-flight request")
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = gate.evict_ollama(client, settings, ["glm-4.7-flash:Q4_K_M-ctx24k"])
    assert result.status is Status.PASS
    assert "in_flight" in result.detail


def test_runner_eviction_call_site_polls_until_the_release_finishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The intra-phase call site must not fail on the first /api/ps that still lists a release."""
    monkeypatch.setattr(gate, "_poll_pause", lambda _seconds: None)
    monkeypatch.setattr(gate, "_pipeline_ollama_in_flight", lambda _name: False)
    reads = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        if request.url.path == "/api/ps":
            reads["n"] += 1
            if reads["n"] < 3:
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {
                                "name": "glm-4.7-flash:Q4_K_M-ctx24k",
                                "expires_at": "2026-11-26T04:39:04+00:00",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"models": []})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={})
        if request.url.path.startswith("/v1/models"):
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)

    real_client = httpx.Client

    def client_factory(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(runner.httpx, "Client", client_factory)
    assert runner._evict_resident_engines(make_settings(tmp_path)) == []
    assert reads["n"] >= 3


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
        runner.gate, "run_gate", lambda *args, **kwargs: GateReport(phase="phase", ok=True)
    )
    runner._execute(settings, plan, state, runner.RunnerOptions({2}, set(), set()), {})
    assert seen == ["gate-2-phase", "one"]


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
    assert by_id["s2-p3-auto-coding"].timeout_s >= 360.0
    assert by_id["s2-p3-auto-coding::cad"].timeout_s == 600
    assert by_id["s2-p6-auto-audio::image"].timeout_s == 900
    assert by_id["s2-p6-auto-audio::video"].timeout_s == 1800
    assert by_id["s2-p6-auto-audio::music"].timeout_s == 900
    assert "s2-p6-auto-audio-stt" in by_id and "s2-p6-auto-audio-tts" in by_id


def test_primary_model_for_reads_base_and_variant_hints() -> None:
    portal_data = {
        "workspaces": {
            "auto": {"model_hint": "router-primary"},
            "auto-coding": {
                "model_hint": "coding-primary",
                "variants": {"cad": {"model_hint": "cad-primary"}, "bigfix": {}},
            },
        }
    }

    assert qat_config.primary_model_for("auto", portal_data) == ""
    assert qat_config.primary_model_for("auto-coding", portal_data) == "coding-primary"
    assert qat_config.primary_model_for("auto-coding::cad", portal_data) == "cad-primary"
    assert qat_config.primary_model_for("auto-coding::bigfix", portal_data) == "coding-primary"


def test_completed_chat_matches_primary_and_records_actual_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    outcome = SimpleNamespace(
        chat_id="chat-1",
        text="the answer",
        trace={"workspace": "auto-coding", "model": "coding-primary", "backend": "omlx"},
        served_model="auto-coding",
        artifact_urls=(),
        leak_marker=None,
        tool_calls=(),
    )

    class FakeResponse:
        is_success = True
        status_code = 200
        headers: dict[str, str] = {}

    class FakeClient:
        def __init__(self, settings: object) -> None:
            pass

        def signin(self) -> str:
            return "token"

        def create_chat(self, *args: object, **kwargs: object) -> str:
            return "chat-1"

        def send_turn(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

        def poll_turn(self, *args: object, **kwargs: object) -> object:
            return outcome

    monkeypatch.setattr(runner, "OWUIClient", FakeClient)
    portal_data = {"workspaces": {"auto-coding": {"model_hint": "coding-primary"}}}
    monkeypatch.setattr(
        runner,
        "primary_model_for",
        lambda workspace: qat_config.primary_model_for(workspace, portal_data),
    )
    monkeypatch.setattr(runner, "_finalize_chat", lambda *args: (True, "archived"))
    settings = make_settings(tmp_path)
    scenario = QATScenario(
        "primary-chat", "Primary chat", 2, "phase", 1, "auto-coding", prompts=("hello",)
    )

    result = runner._run_chat(
        settings,
        scenario,
        runner.RunState(settings, tmp_path, make_discovery()),
        runner.RunnerOptions({2}, set(), set()),
    )

    assert result.status is Status.PASS
    assert result.served_model == "coding-primary"


def test_pipeline_backstop_fails_and_preserves_fallback_spans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace = {
        "correlation_id": "corr-1",
        "workspace": "auto-coding::cad",
        "model": "coding-backstop",
        "backend": "ollama-coding",
        "spans": [
            {"name": "backend.failed", "error": "primary engine unavailable"},
            {"name": "backend.fallback", "reason": "selected backstop model"},
        ],
    }

    class FakeResponse:
        status_code = 200
        headers = {"X-Correlation-ID": "corr-1"}

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "the answer"}}]}

    class FakeHTTPClient:
        def __init__(self, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeHTTPClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(runner.httpx, "Client", FakeHTTPClient)
    monkeypatch.setattr(runner, "primary_model_for", lambda workspace: "coding-primary")
    monkeypatch.setattr(
        runner.OWUIClient,
        "lookup_trace",
        lambda self, **kwargs: trace,
    )
    scenario = QATScenario(
        "primary-backstop",
        "Backstop response",
        2,
        "phase",
        1,
        "auto-coding::cad",
        kind="pipeline",
        prompts=("hello",),
    )

    result = runner._run_pipeline_chat(make_settings(tmp_path), scenario)

    assert result.status is Status.FAIL
    assert result.defect_class.value == "INFRA_ENV_GAP"
    assert "expected coding-primary, served coding-backstop" in result.detail
    assert result.evidence["primary_mismatch"]["failed_fallback_spans"] == trace["spans"]


def test_dynamic_auto_chat_checks_resolved_trace_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    portal_data = {
        "workspaces": {
            "auto": {"model_hint": "router-primary"},
            "auto-coding": {
                "model_hint": "coding-primary",
                "variants": {"cad": {"model_hint": "cad-primary"}},
            },
        }
    }
    resolved_workspaces: list[str] = []
    outcome = SimpleNamespace(
        chat_id="chat-1",
        text="the answer",
        trace={"workspace": "auto-coding::cad", "model": "cad-primary", "backend": "omlx"},
        served_model="auto",
        artifact_urls=(),
        leak_marker=None,
        tool_calls=(),
    )

    class FakeResponse:
        is_success = True
        status_code = 200
        headers: dict[str, str] = {}

    class FakeClient:
        def __init__(self, settings: object) -> None:
            pass

        def signin(self) -> str:
            return "token"

        def create_chat(self, *args: object, **kwargs: object) -> str:
            return "chat-1"

        def send_turn(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

        def poll_turn(self, *args: object, **kwargs: object) -> object:
            return outcome

    def resolve(workspace: str) -> str:
        resolved_workspaces.append(workspace)
        return qat_config.primary_model_for(workspace, portal_data)

    monkeypatch.setattr(runner, "OWUIClient", FakeClient)
    monkeypatch.setattr(runner, "primary_model_for", resolve)
    monkeypatch.setattr(runner, "_finalize_chat", lambda *args: (True, "archived"))
    settings = make_settings(tmp_path)
    scenario = QATScenario(
        "auto-primary", "Dynamic auto", 2, "phase", 1, "auto", prompts=("hello",)
    )

    result = runner._run_chat(
        settings,
        scenario,
        runner.RunState(settings, tmp_path, make_discovery()),
        runner.RunnerOptions({2}, set(), set()),
    )

    assert result.status is Status.PASS
    assert result.served_model == "cad-primary"
    assert resolved_workspaces == ["auto-coding::cad"]


def _png_idat(png: bytes) -> bytes:
    pos = 8
    blobs: list[bytes] = []
    while pos + 8 <= len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        kind = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        if kind == b"IDAT":
            blobs.append(data)
        pos += 12 + length
        if kind == b"IEND":
            break
    return zlib.decompress(b"".join(blobs))


def test_auto_vision_scenarios_request_inline_png(tmp_path: Path) -> None:
    registry = scenarios.build_registry(make_settings(tmp_path), make_discovery())
    wanted = {"s2-p1-auto-vision", "s2-p2-auto-vision"}
    vision = [s for s in registry if s.scenario_id in wanted]
    assert {s.scenario_id for s in vision} == wanted
    assert all(s.attachment == scenarios.INLINE_VISION_PNG for s in vision)
    assert all(s.prompts == (scenarios.VISION_PROBE,) for s in vision)


def test_send_turn_posts_red_square_image_url() -> None:
    settings = make_settings(Path("/tmp"), OWUI_API_KEY="qat-token")
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/chats/new":
            return httpx.Response(201, json={"id": "chat-vision"})
        if request.url.path == "/api/chat/completions":
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    png = red_square_png()
    client = OWUIClient(settings, httpx.MockTransport(handler))
    chat_id = client.create_chat("token", "auto-vision", "vision", prompt=scenarios.VISION_PROBE)
    client.send_turn("token", chat_id, "auto-vision", scenarios.VISION_PROBE, image_png=png)
    content = bodies[0]["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": scenarios.VISION_PROBE}
    image = content[1]
    assert image["type"] == "image_url"
    url = image["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.removeprefix("data:image/png;base64,"))
    assert decoded == png
    assert decoded[16:24] == struct.pack(">II", 64, 64)
    assert decoded[24:26] == bytes((8, 2))
    assert _png_idat(decoded) == (b"\x00" + bytes((255, 0, 0)) * 64) * 64


def test_report_uses_actual_served_model_in_acceptance_matrix(tmp_path: Path) -> None:
    scenario = QATScenario("actual-model", "Actual model", 2, "phase", 1, "auto-coding")
    result = QATResult(
        "actual-model", Status.PASS, "chat turn completed", served_model="coding-primary"
    )

    path = report.write_markdown(tmp_path, make_discovery(), [scenario], [result])

    assert "| actual-model | coding-primary | PASS |" in path.read_text(encoding="utf-8")
