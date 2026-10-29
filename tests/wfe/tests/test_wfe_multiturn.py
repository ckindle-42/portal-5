"""Short multi-turn tasks: scripted user turns on one conversation, graded per turn.

A task may carry `turns`; the runner sends turn 1, runs its tool loop to a final answer,
then sends the next scripted turn on the same conversation. A row PASSes only when every
turn's objective checks pass. Single-turn suites behave exactly as before.
"""

from __future__ import annotations

import json

import pytest

from tests.wfe import controls
from tests.wfe import runner as rn
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.schema import Outcome

TWO_TURNS = {
    "id": "realuse-01",
    "turns": [
        {"user": "first ask", "checks": [{"type": "answer_contains", "patterns": ["one"]}]},
        {"user": "second ask", "checks": [{"type": "answer_contains", "patterns": ["two"]}]},
    ],
}


def _reply(content="", calls=None, finish="stop"):
    return {
        "message": {"content": content, "tool_calls": calls or []},
        "finish_reason": finish,
        "economics": rn.Economics(),
        "harness_caveats": [],
        "resolved_think": "default",
        "served": {},
    }


def _tool_call(name, args, call_id="c1"):
    return {"id": call_id, "function": {"name": name, "arguments": json.dumps(args)}}


def _run(
    monkeypatch, task, replies, *, max_turns=8, use_tools=True, tool_surface=None, tmp_path=None
):
    seen = []

    def fake_chat(model, messages, **kwargs):  # noqa: ARG001
        seen.append([dict(m) for m in messages])
        reply = replies[len(seen) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(rn, "chat", fake_chat)
    out = rn.run_task(
        "m",
        "sys",
        task,
        rn.Sandbox(tmp_path),
        max_turns=max_turns,
        budget_s=60,
        use_tools=use_tools,
        tool_surface=tool_surface,
    )
    return out, seen


def test_each_scripted_turn_is_sent_on_the_same_conversation(monkeypatch, tmp_path):
    out, seen = _run(monkeypatch, TWO_TURNS, [_reply("one"), _reply("two")], tmp_path=tmp_path)
    assert out["outcome"] == Outcome.PASS.value
    assert len(seen) == 2
    roles = [m["role"] for m in seen[1]]
    assert roles == ["system", "user", "assistant", "user"]
    assert seen[1][1]["content"] == "first ask"
    assert seen[1][2]["content"] == "one"
    assert seen[1][3]["content"] == "second ask"
    assert [t["outcome"] for t in out["evidence"]["turn_outcomes"]] == ["PASS", "PASS"]


def test_a_later_turn_that_fails_fails_the_row(monkeypatch, tmp_path):
    out, _ = _run(monkeypatch, TWO_TURNS, [_reply("one"), _reply("nope")], tmp_path=tmp_path)
    assert out["outcome"] == Outcome.FAIL.value
    assert "turn 1" in out["notes"]
    assert out["evidence"]["turn_outcomes"][1]["outcome"] == "FAIL"


def test_must_not_contain_fails_the_turn(monkeypatch, tmp_path):
    task = {
        "id": "realuse-02",
        "turns": [
            {"user": "go", "checks": [{"type": "answer_contains", "patterns": ["ok"]}]},
            {
                "user": "now be careful",
                "checks": [{"type": "must_not_contain", "patterns": ["forbidden"]}],
            },
        ],
    }
    out, _ = _run(monkeypatch, task, [_reply("ok"), _reply("this is forbidden")], tmp_path=tmp_path)
    assert out["outcome"] == Outcome.FAIL.value
    assert out["evidence"]["turn_outcomes"][1]["outcome"] == "FAIL"


def test_expect_tools_is_graded_on_that_turns_own_calls(monkeypatch, tmp_path):
    task = {
        "id": "realuse-03",
        "turns": [
            {"user": "write it", "expect_tools": ["file_write"]},
            {"user": "read it back", "expect_tools": ["file_read"]},
        ],
    }
    replies = [
        _reply(calls=[_tool_call("file_write", {"path": "out.txt", "content": "hello"})]),
        _reply("written"),
        _reply(calls=[_tool_call("file_read", {"path": "out.txt"}, "c2")]),
        _reply("it says hello"),
    ]
    out, seen = _run(monkeypatch, task, replies, tmp_path=tmp_path)
    assert out["outcome"] == Outcome.PASS.value
    assert len(seen) == 4
    # the tool result travels on the conversation before the turn's final answer
    assert seen[1][-1]["role"] == "tool"
    assert out["evidence"]["turn_outcomes"][0]["outcome"] == "PASS"
    assert out["evidence"]["turn_outcomes"][1]["outcome"] == "PASS"


def test_a_missing_expected_tool_fails_the_turn(monkeypatch, tmp_path):
    task = {"id": "realuse-04", "turns": [{"user": "read it", "expect_tools": ["file_read"]}]}
    out, _ = _run(monkeypatch, task, [_reply("I did not read anything")], tmp_path=tmp_path)
    assert out["outcome"] == Outcome.FAIL.value
    assert out["evidence"]["turn_outcomes"][0]["notes"].startswith("expected tools not called")


def test_a_turn_can_grade_a_file_it_produced(monkeypatch, tmp_path):
    task = {
        "id": "realuse-05",
        "turns": [
            {"user": "write out.txt", "checks": [{"type": "file_exists", "path": "out.txt"}]},
            {"user": "say done", "checks": [{"type": "answer_contains", "patterns": ["done"]}]},
        ],
    }
    replies = [
        _reply(calls=[_tool_call("file_write", {"path": "out.txt", "content": "x"})]),
        _reply("done"),
        _reply("done"),
    ]
    out, _ = _run(monkeypatch, task, replies, tmp_path=tmp_path)
    assert out["outcome"] == Outcome.PASS.value
    assert (tmp_path / "out.txt").exists()


def test_a_turn_grounds_on_a_tool_call_from_an_earlier_turn(monkeypatch, tmp_path):
    task = {
        "id": "realuse-06",
        "turns": [
            {"user": "read the file", "expect_tools": ["file_read"]},
            {
                "user": "what did it say?",
                "checks": [
                    {"type": "answer_contains", "patterns": ["secret"]},
                    {"type": "tool_grounded", "tools": ["file_read"], "evidence": ["secret"]},
                ],
            },
        ],
    }
    (tmp_path / "notes.md").write_text("the secret is 42")
    replies = [
        _reply(calls=[_tool_call("file_read", {"path": "notes.md"})]),
        _reply("it says secret"),
        _reply("the secret is 42"),
    ]
    out, _ = _run(monkeypatch, task, replies, tmp_path=tmp_path)
    assert out["outcome"] == Outcome.PASS.value


def test_single_turn_tasks_are_unchanged(monkeypatch, tmp_path):
    task = {
        "id": "single",
        "instruction": "do it",
        "checkers": [{"type": "answer_contains", "patterns": ["done"]}],
    }
    out, seen = _run(monkeypatch, task, [_reply("done")], tmp_path=tmp_path)
    assert out["outcome"] == Outcome.PASS.value
    assert [m["role"] for m in seen[0]] == ["system", "user"]
    assert seen[0][1]["content"] == "do it"
    assert "turn_outcomes" not in out["evidence"]
    assert all("scripted_turn" not in t for t in out["transcript"])


def test_a_turn_expecting_an_unoffered_tool_blocks_the_row(monkeypatch, tmp_path):
    task = {"id": "realuse-07", "turns": [{"user": "x", "expect_tools": ["kb_search"]}]}
    out, seen = _run(
        monkeypatch, task, [_reply("done")], tool_surface=["file_read"], tmp_path=tmp_path
    )
    assert out["outcome"] == Outcome.BLOCKED.value
    assert "kb_search" in out["notes"]
    assert seen == []


def test_a_stall_ends_the_conversation_after_the_completed_turns(monkeypatch, tmp_path):
    task = {
        "id": "realuse-08",
        "turns": [
            {"user": "one", "checks": [{"type": "answer_contains", "patterns": ["ok"]}]},
            {"user": "two", "checks": [{"type": "answer_contains", "patterns": ["ok"]}]},
        ],
    }
    replies = [_reply("ok"), rn.StreamStalledError("no output for 600s")]
    out, _ = _run(monkeypatch, task, replies, tmp_path=tmp_path)
    assert out["outcome"] == Outcome.BUDGET_EXHAUSTED.value
    # Turn 0 answered and passed; turn 1 never answered, so its check grades empty text.
    assert out["evidence"]["turn_outcomes"][0]["outcome"] == "PASS"
    assert out["evidence"]["checker_outcome"] == Outcome.FAIL.value
    assert "did not finish" in out["notes"]


def test_must_not_contain_checker():
    task = {"checkers": [{"type": "must_not_contain", "patterns": [r"\bSUPPORTED\b"]}]}
    ctx = CheckContext(final_text="the state is SUPPORTED", task=task)
    assert apply_checkers(task, ctx).outcome == Outcome.FAIL
    ctx = CheckContext(final_text="the state is PARTIAL", task=task)
    assert apply_checkers(task, ctx).outcome == Outcome.PASS


class TestControlSchema:
    def test_a_multi_turn_task_is_gradeable(self):
        assert controls.schema_failures(TWO_TURNS) == []
        assert controls.check_task(TWO_TURNS) == []

    def test_a_task_level_checkers_block_is_refused(self):
        task = {**TWO_TURNS, "checkers": [{"type": "answer_contains", "patterns": ["x"]}]}
        assert "per turn" in " ".join(f.notes for f in controls.schema_failures(task))

    @pytest.mark.parametrize(
        "turn",
        [
            {"user": "", "checks": [{"type": "answer_contains", "patterns": ["x"]}]},
            {"user": "x", "check": [{"type": "answer_contains", "patterns": ["x"]}]},
            {"user": "x", "checks": [{"type": "no_such_checker", "patterns": ["x"]}]},
        ],
    )
    def test_a_malformed_turn_is_refused(self, turn):
        task = {
            "id": "bad",
            "turns": [
                {"user": "ok", "checks": [{"type": "answer_contains", "patterns": ["z"]}]},
                turn,
            ],
        }
        assert controls.schema_failures(task)

    def test_a_must_not_contain_only_turn_is_refused(self):
        task = {
            "id": "weak",
            "turns": [{"user": "x", "checks": [{"type": "must_not_contain", "patterns": ["z"]}]}],
        }
        # A negative-only check passes an empty answer by construction, so it is not a
        # gradeable turn: the schema gate says so instead of scoring a silent PASS.
        notes = " ".join(f.notes for f in controls.schema_failures(task))
        assert "must_not_contain alone" in notes

    def test_a_turn_graded_only_by_its_expected_tools_is_gradeable(self):
        task = {"id": "tooled", "turns": [{"user": "look it up", "expect_tools": ["repo_search"]}]}
        assert controls.schema_failures(task) == []

    def test_a_task_with_nothing_graded_is_refused(self):
        task = {"id": "empty", "turns": [{"user": "hello"}]}
        assert controls.schema_failures(task)
