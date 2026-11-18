"""Offline orchestration arm tests through a fake Pipeline API."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml
from fastapi import HTTPException

from portal.modules.orchestration.contracts import parse_plan
from portal.modules.orchestration.planner import instantiate_plan_template
from portal.modules.orchestration.service import (
    ArmService,
    StubNoticeSink,
    load_arm_config,
    module_is_enabled,
    seated_model_tags,
)
from portal.modules.orchestration.worker import Engine
from portal.platform.inference.router import auth
from portal.platform.inference.router.eval_gate import apply_bite_tool_scope

_fake_spec = spec_from_file_location(
    "_orchestration_fake_pipeline", Path(__file__).with_name("orchestration_fake_pipeline.py")
)

_fake_module = module_from_spec(_fake_spec)

_fake_spec.loader.exec_module(_fake_module)

FakePipeline = _fake_module.FakePipeline

finish_response = _fake_module.finish_response

text_response = _fake_module.text_response

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


def plan(task_id: str, *bites: dict[str, Any]) -> dict[str, Any]:
    return {"task_id": task_id, "goal": "Run the offline scenario.", "bites": list(bites)}


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


@pytest.fixture
def fake_pipeline():
    server = FakePipeline()
    try:
        yield server
    finally:
        server.close()


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


def test_module_switch_is_on_in_repo_config() -> None:
    # Enabled after the 2026-10-23 end-to-end run (Telegram approval, repair, review) passed.
    assert module_is_enabled(Path("config/portal.yaml"))


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
