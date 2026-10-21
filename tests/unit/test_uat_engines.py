"""Unit tests for scripts/uat_engines.py. No network."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx

_SPEC = importlib.util.spec_from_file_location(
    "uat_engines",
    Path(__file__).resolve().parents[2] / "scripts" / "uat_engines.py",
)
uat = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(uat)


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        workspaces={
            "general-engine": SimpleNamespace(
                module="general",
                expose_to_owui=True,
                variants={"fast": {}, "red": {"module": "security"}},
            ),
            "sec-engine": SimpleNamespace(
                module="security",
                expose_to_owui=True,
                variants={"deep": {"module": "security_redteam"}},
            ),
            "media-engine": SimpleNamespace(
                module="media",
                expose_to_owui=False,
                variants={"clip": {"module": "video"}},
            ),
            "hidden-engine": SimpleNamespace(module="general", expose_to_owui=False, variants={}),
            "ide-engine": SimpleNamespace(
                module="general",
                expose_to_owui=True,
                stack_down_only=True,
                variants={"reap": {"stack_down_only": True}},
            ),
            "hybrid-engine": SimpleNamespace(
                module="general",
                expose_to_owui=True,
                stack_down_only=True,
                variants={"light": {"stack_down_only": False}},
            ),
        }
    )


def test_select_shots_skips_security_modules():
    config = _config()
    mods = ["general", "security", "media"]
    run, skip, down = uat.select_shots(config, mods)

    assert run == [
        "general-engine",
        "general-engine::fast",
        "hidden-engine",
        "hybrid-engine::light",
        "media-engine",
    ]
    assert skip == ["general-engine::red", "sec-engine"]
    assert down == ["hybrid-engine", "ide-engine", "ide-engine::reap"]
    assert "sec-engine::deep" not in run
    assert "sec-engine::deep" not in skip
    assert "media-engine::clip" not in run

    disabled = uat.disabled_variant_ids(config, mods)
    owned = uat.owned_disabled_ids(config, mods)
    assert disabled == ["media-engine::clip"]
    assert owned == ["sec-engine::deep"]
    assert "general-engine::red" not in disabled
    listed = sorted(set(skip).union(owned))
    plan = uat.render_plan(run, listed, down, [], None, None, None, disabled, [], design=True)
    head, _, tail = plan.partition("disabled variants")
    assert "sec-engine::deep" in head
    assert "general-engine::red" in head
    assert "skipped: owned elsewhere" in head
    assert "stack-down only, not tested (3):" in head
    assert "ide-engine::reap" in head
    assert "sec-engine::deep" not in tail
    assert "media-engine::clip" in tail


def test_stack_down_only_resolution_prefers_the_variant_override():
    config = _config()
    assert uat.is_stack_down_only(config, "ide-engine")
    assert uat.is_stack_down_only(config, "ide-engine::reap")
    assert uat.is_stack_down_only(config, "hybrid-engine")
    assert not uat.is_stack_down_only(config, "hybrid-engine::light")
    assert not uat.is_stack_down_only(config, "general-engine")
    assert not uat.is_stack_down_only(config, "general-engine::fast")
    assert not uat.is_stack_down_only(config, "missing-engine")


def test_stack_down_ids_get_no_request_and_own_sections():
    config = _config()
    mods = ["general", "security", "media"]
    run, skip, down = uat.select_shots(config, mods)
    plan = uat.render_plan(run, skip, down, [], None, None, None, [], [], design=False)
    assert "stack-down only, not tested (3):" in plan
    assert "hybrid-engine" in plan

    only_run, only_skip, only_down, error = uat.resolve_only("ide-engine", run, skip, down)
    assert (only_run, only_skip, only_down, error) == ([], [], ["ide-engine"], None)

    report = {
        "shots": [],
        "checks": [],
        "skipped": skip,
        "stack_down_only": down,
        "totals": uat.compute_totals([], skip, []),
    }
    text = uat.render_summary(report)
    assert "## stack-down only, not tested" in text
    assert "- ide-engine" in text
    assert "- hybrid-engine" in text
    assert text.index("## skipped: owned elsewhere") < text.index("## stack-down only, not tested")
    assert report["totals"]["shots_failed"] == 0


def test_disabled_variant_check_reads_httpx_404():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "media-engine::clip"
        assert body["stream"] is False
        return httpx.Response(
            404,
            json={"detail": "Workspace 'media-engine::clip' is disabled (module not enabled)."},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    status, payload, _route, _cid, error = uat.post_json(
        client,
        "http://pipeline.test/v1/chat/completions",
        "k",
        uat.chat_payload("media-engine::clip", "hi", stream=False),
        "cid",
    )

    assert error is None
    ok, reason = uat.classify_disabled_response(status, payload)
    assert ok
    assert "disabled" in reason
    inferred, why = uat.classify_disabled_response(
        200, {"detail": "disabled", "choices": [{"message": {"content": "ran"}}]}
    )
    assert not inferred
    assert "HTTP 200" in why


def test_alias_comparison_uses_route_model():
    routes = {
        "old-name": "eng::v;backend;same-model",
        "eng::v": "eng::v;backend;same-model",
        "other": "eng;backend;different-model",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            headers={"x-portal-route": routes[model]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    alias = uat.fire_shot(client, "http://pipeline.test", "k", "old-name")
    target = uat.fire_shot(client, "http://pipeline.test", "k", "eng::v")
    ok, reason = uat.compare_route_models(alias["route"], target["route"])
    assert alias["ok"] and target["ok"]
    assert ok and reason == "same-model"

    other = uat.fire_shot(client, "http://pipeline.test", "k", "other")
    bad, why = uat.compare_route_models(other["route"], target["route"])
    assert not bad
    assert why == "different-model != same-model"


def test_empty_answer_fails_the_shot():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  "}}]},
            headers={"x-portal-route": "eng;backend;model"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    shot = uat.fire_shot(client, "http://pipeline.test", "k", "eng")
    assert shot["http_status"] == 200
    assert shot["route_model"] == "model"
    assert not shot["ok"]
    assert shot["error"] == "empty answer"


def test_summary_table_checks_and_totals():
    report = {
        "shots": [{"id": "auto-daily", "http_status": 200, "route_model": "gemma", "seconds": 1.2}],
        "checks": [{"name": "streaming", "ok": False, "reason": "no [DONE]"}],
        "skipped": ["auto-security"],
        "totals": {
            "shots_ok": 1,
            "shots_failed": 0,
            "skipped": 1,
            "checks_ok": 0,
            "checks_failed": 1,
        },
    }
    text = uat.render_summary(report)
    assert "| id | status | route model | seconds |" in text
    assert "| auto-daily | 200 | gemma | 1.2 |" in text
    assert "- FAIL streaming: no [DONE]" in text
    assert "- shots: 1 ok, 0 failed, 1 skipped" in text
    assert "- checks: 0 pass, 1 fail" in text
    assert "## skipped: owned elsewhere" in text
    assert "- auto-security" in text


def test_streaming_check_requires_sse_chunks_and_done():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        body = 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = uat.fire_stream(client, "http://pipeline.test", "k", "general-engine")
    assert result == {
        "name": "streaming",
        "ok": True,
        "reason": "1 SSE chunks and [DONE]",
    }
    bare, why = uat.sse_status(["data: [DONE]"])
    assert not bare
    assert "chunks=0" in why


def test_empty_content_with_reasoning_fails_and_is_named():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "", "reasoning_content": "because"}}]},
            headers={"x-portal-route": "eng;backend;model"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    shot = uat.fire_shot(client, "http://pipeline.test", "k", "eng")
    assert shot["http_status"] == 200
    assert not shot["ok"]
    assert shot["reasoning_only"]
    assert shot["error"] == "empty answer; answer only in reasoning"
    report = {
        "shots": [shot],
        "checks": [],
        "skipped": [],
        "totals": uat.compute_totals([shot], [], []),
    }
    text = uat.render_summary(report)
    assert "answer only in reasoning" in text
    assert report["totals"]["shots_failed"] == 1


def test_role_skips_trace_when_bodies_are_off_and_engine_holds():
    prompt = "You are the daily driver role for this check."
    check = uat.judge_role(
        "chat;backend;model",
        "chat;other-backend;model",
        {"bodies_captured": False},
        prompt,
    )
    assert check["skipped"] is True
    assert check["ok"] is False
    report = {
        "shots": [],
        "checks": [check],
        "skipped": [],
        "totals": uat.compute_totals([], [], [check]),
    }
    text = uat.render_summary(report)
    assert "SKIP: set PORTAL_TRACE_BODIES=1" in text
    assert report["totals"]["checks_failed"] == 0
    assert report["totals"]["checks_ok"] == 0


def test_role_fails_when_the_engine_changes_without_trace_bodies():
    check = uat.judge_role(
        "chat;backend;model",
        "other;backend;model",
        {"bodies_captured": False},
        "You are the daily driver role for this check.",
    )
    assert check.get("skipped") is not True
    assert check["ok"] is False
    assert check["reason"] == "engine other != chat"


def test_role_passes_when_the_prompt_is_in_the_trace():
    prompt = "You are the daily driver role for this check."
    check = uat.judge_role(
        "chat;backend;model",
        "chat;backend;model",
        {"bodies_captured": True, "bodies": {"messages": [{"content": prompt}]}},
        prompt,
    )
    assert check["ok"] is True
    assert check.get("skipped") is not True
    assert "engine chat" in check["reason"]
    assert "persona prompt in trace messages" in check["reason"]
