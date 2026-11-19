"""Jarvis R6: the planner returns a plan, not a tool call.

The captured local failure (2026-11-19, task on auto-daily::fast): the IFM
planner seat (K2-Horizon-MoVA on auto-reasoning) answered a read-only request
with prose plus a native tool call in its own markup instead of the JSON plan,
twice, and the task went to cloud. The planner turn is toolless, the seat is
asked for JSON, and a prose/markup answer gets one corrective retry inside the
same attempt before the local failure is recorded. No network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import planner_body
from portal.modules.orchestration.personal_runner import Completion, poll_personal_tasks

REQUEST = "List the three largest files in /workspace/generated and report their sizes."

# The two captured shapes: attempt 1 called execute_bash, attempt 2 workspace_files.
CAPTURED_TAIL_1 = (
    "I'll list the files for you. "
    "<ifm|tool_calls>\n<ifm|tool_call>execute_bash\n"
    "<ifm|arg_key>command</ifm|arg_key>\n"
    "<ifm|arg_value>find /workspace/generated -type f</ifm|arg_value>\n"
    "</ifm|tool_call>\n</ifm|tool_calls>"
)
CAPTURED_TAIL_2 = (
    "Let me check the workspace. "
    "<ifm|tool_calls>\n<ifm|tool_call>workspace_files\n"
    "<ifm|arg_key>path</ifm|arg_key>\n<ifm|arg_value>generated</ifm|arg_value>\n"
    "</ifm|tool_call>\n</ifm|tool_calls>"
)


class _Notices:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append((task_id, kind, message))


class _Caller:
    def __init__(self, replies: list[Completion]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def complete(self, body: dict[str, Any]) -> Completion:
        self.bodies.append(json.loads(json.dumps(body)))
        return self.replies.pop(0)


def _plan() -> str:
    return json.dumps({"steps": [{"id": "s1", "tools": [], "paths": []}]})


def _queued(tmp_path: Path) -> tuple[Path, str]:
    tasks = tmp_path / "tasks"
    reply = telegram_do_reply(tasks, 1, REQUEST)
    return tasks, reply.removeprefix("queued ")


# ── the planner turn ──────────────────────────────────────────────────────────


_ARM_CONFIG = {
    "planner": {"comfortable_context_tokens": 32768},
    "disciplines": {
        "test_fixing": {
            "fast_context_budget_tokens": 32768,
            "tool_allowlist": ["file_read"],
            "read_tools": ["file_read"],
            "action_tools": [],
            "procedures": [],
        }
    },
}


def test_planner_turn_is_toolless_and_asks_for_json() -> None:
    body = planner_body(REQUEST)
    assert body["portal_no_tools"] is True
    assert body["tool_choice"] == "none"
    assert body["response_format"] == {"type": "json_object"}
    assert '{"steps"' in body["messages"][0]["content"]


def test_deep_arm_planner_turn_is_toolless_and_asks_for_json() -> None:
    from portal.modules.orchestration import planner

    captured: dict[str, Any] = {}

    class _StopError(Exception):
        pass

    class _Engine:
        model_tag = "auto-daily::deep"
        model_digest = "d"
        load_plan_engine = "omlx"
        load_plan_model = "m"

        def load_plan(self, timeout: float) -> dict[str, Any]:
            return {}

        def chat(self, body: dict[str, Any], timeout: float, on_event) -> dict[str, Any]:
            captured.update(body)
            raise _StopError

    with pytest.raises(_StopError):
        planner.plan_goal(
            _Engine(),
            goal="g",
            task_id="t",
            discipline="test_fixing",
            arm_config=_ARM_CONFIG,
        )
    assert captured["portal_no_tools"] is True
    assert captured["response_format"] == {"type": "json_object"}


def test_prose_answer_gets_one_corrective_retry_inside_the_attempt(
    tmp_path: Path,
) -> None:
    tasks, task_id = _queued(tmp_path)
    caller = _Caller(
        [
            Completion(CAPTURED_TAIL_1),
            Completion(_plan()),
            Completion("a.bin 300 bytes, b.bin 200 bytes, c.bin 100 bytes."),
        ]
    )
    result = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: "")
    assert result is not None and result.status == "done"
    assert len(caller.bodies) == 3, "exactly one corrective retry happened"
    retry = caller.bodies[1]
    assert [m["role"] for m in retry["messages"]] == ["system", "user", "assistant", "user"]
    assert "execute_bash" in retry["messages"][2]["content"]
    assert "JSON object only" in retry["messages"][3]["content"]
    assert retry["portal_no_tools"] is True
    assert retry["response_format"] == {"type": "json_object"}
    receipt = json.loads((tasks / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "done"


def test_valid_planner_json_is_not_retried(tmp_path: Path) -> None:
    tasks, _ = _queued(tmp_path)
    caller = _Caller([Completion(_plan()), Completion("Done.")])
    result = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: "")
    assert result is not None and result.status == "done"
    assert len(caller.bodies) == 2


def test_retry_exhausted_counts_as_a_local_failure(tmp_path: Path) -> None:
    tasks, task_id = _queued(tmp_path)
    caller = _Caller([Completion(CAPTURED_TAIL_1), Completion(CAPTURED_TAIL_2)])
    result = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: "")
    assert result is not None and result.status == "retrying"
    receipt = json.loads((tasks / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "retrying"
    assert "workspace_files" in receipt["error"], "the failure names the last rejected answer"
    attempts = json.loads(
        (tasks / task_id / "attempts" / "local-1" / "receipt.json").read_text(encoding="utf-8")
    )
    assert attempts["status"] == "local-failed"


@pytest.mark.parametrize(
    "bad",
    [CAPTURED_TAIL_1, CAPTURED_TAIL_2],
)
def test_parse_planner_json_rejects_the_captured_markup(bad: str) -> None:
    from portal.modules.orchestration.personal_policy import parse_planner_json

    with pytest.raises(ValueError, match="JSON object"):
        parse_planner_json(bad)
