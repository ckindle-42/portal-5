"""Jarvis R5: recall relevance, authoritative request, workspace reads, junk-write gate.

Regression net for task pt-4ee42e935737 — "List the three largest files in
/workspace/generated and report their sizes." answered about recalled junk files
instead of the request, and the sandbox could not see /workspace/generated. No network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import (
    CONFIRM_TOOLS,
    CORE_TOOLS,
    READ_TOOLS,
)
from portal.modules.orchestration.personal_runner import (
    RECALL_MIN_SIMILARITY,
    RECALL_TOP_K,
    Completion,
    _memory_text,
    _route_messages,
    poll_personal_tasks,
)
from portal.modules.orchestration.personal_tools import LOCAL_TOOLS, run_read_tool
from portal.platform.memory import graph_memory

REQUEST = "List the three largest files in /workspace/generated and report their sizes."
JUNK = "- The file /workspace/report.txt contains {line_count} lines."


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


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from portal.platform.mcp_host import workspace as ws

    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "a.bin").write_bytes(b"x" * 300)
    (tmp_path / "generated" / "b.bin").write_bytes(b"x" * 200)
    (tmp_path / "generated" / "c.bin").write_bytes(b"x" * 100)
    monkeypatch.setattr(ws, "get_workspace_root", lambda: tmp_path)
    return tmp_path


# ── Recall relevance threshold + top-k ─────────────────────────────────────────


def test_memory_text_drops_low_similarity_and_caps_top_k() -> None:
    memories = [
        {"text": f"m{i}", "similarity": RECALL_MIN_SIMILARITY + 0.1}
        for i in range(RECALL_TOP_K + 3)
    ]
    memories.append({"text": "junk", "similarity": RECALL_MIN_SIMILARITY - 0.01})
    rendered = _memory_text({"memories": memories})
    lines = rendered.splitlines()
    assert len(lines) == RECALL_TOP_K
    assert "junk" not in rendered
    assert lines[0] == "- m0"


def test_memory_text_drops_memories_without_a_usable_score() -> None:
    assert _memory_text({"memories": [{"text": "no score"}]}) == ""
    assert _memory_text({"memories": [{"text": "bad", "similarity": "n/a"}]}) == ""
    assert _memory_text({"memories": [{"text": "null", "similarity": None}]}) == ""


def test_memory_text_keeps_a_relevant_memory() -> None:
    payload = {"memories": [{"text": "prefers terse replies", "similarity": 0.9}]}
    assert _memory_text(payload) == "- prefers terse replies"


# ── Authoritative request + untrusted framing (from the receipt) ───────────────


def test_executor_prompt_request_is_authoritative_and_memory_is_background() -> None:
    content = _route_messages(REQUEST, JUNK)[-1]["content"]
    assert REQUEST in content
    assert "authoritative" in content
    assert "untrusted background" in content
    assert content.index(REQUEST) < content.index(JUNK)


def test_executor_without_memory_has_no_recall_block() -> None:
    content = _route_messages(REQUEST)[-1]["content"]
    assert "Recalled memory" not in content


def test_executor_answers_the_request_from_real_workspace_files(
    tmp_path: Path, workspace: Path
) -> None:
    tasks = tmp_path / "tasks"
    reply = telegram_do_reply(tasks, 1, REQUEST)
    task_id = reply.removeprefix("queued ")
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "workspace_files", "arguments": json.dumps({"path": "generated"})},
    }
    caller = _Caller(
        [
            Completion("", (call,), 0),
            Completion("a.bin 300 bytes, b.bin 200 bytes, c.bin 100 bytes.", (), 0),
        ]
    )
    result = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda query: JUNK)
    assert result is not None and result.status == "done"

    executor_user = caller.bodies[0]["messages"][-1]["content"]
    assert REQUEST in executor_user
    assert "authoritative" in executor_user
    assert "untrusted background" in executor_user
    assert executor_user.index(REQUEST) < executor_user.index(JUNK)

    # The local read returned the real files to the model, largest first.
    tool_messages = [m for m in caller.bodies[1]["messages"] if m.get("role") == "tool"]
    assert tool_messages, "workspace_files result never reached the executor"
    listing = json.loads(tool_messages[0]["content"])
    assert [f["path"] for f in listing["files"]] == [
        "generated/a.bin",
        "generated/b.bin",
        "generated/c.bin",
    ]
    assert [f["size"] for f in listing["files"]] == [300, 200, 100]
    receipt = json.loads((tasks / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert "workspace_files" in receipt["tool_calls"]


def test_an_answer_that_omits_the_largest_size_is_not_done(tmp_path: Path, workspace: Path) -> None:
    tasks = tmp_path / "tasks"
    reply = telegram_do_reply(tasks, 1, REQUEST)
    task_id = reply.removeprefix("queued ")
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "workspace_files", "arguments": json.dumps({"path": "generated"})},
    }
    caller = _Caller(
        [
            Completion("", (call,), 0),
            Completion("The largest file is 1 byte.", (), 0),
        ]
    )
    result = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda query: "")
    assert result is not None and result.status == "retrying"
    receipt = json.loads((tasks / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert "largest file size" in str(receipt["error"])


# ── workspace_files read tool ──────────────────────────────────────────────────


def test_workspace_files_is_an_allowlisted_read_not_a_confirm_tool() -> None:
    assert "workspace_files" in LOCAL_TOOLS
    assert "workspace_files" in READ_TOOLS
    assert "workspace_files" in CORE_TOOLS
    assert "workspace_files" not in CONFIRM_TOOLS


def test_workspace_files_lists_sizes_largest_first(workspace: Path) -> None:
    out = json.loads(run_read_tool("workspace_files", {"path": "generated"}, workspace / "tasks"))
    assert out["count"] == 3
    assert out["scanned"] == 3
    assert out["truncated"] is False
    assert [f["size"] for f in out["files"]] == [300, 200, 100]


def test_workspace_files_keeps_the_largest_file_past_the_walk_cap(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live listing stopped at 200 files in walk order, then sorted that prefix."""
    import os

    from portal.modules.orchestration import personal_tools

    early = workspace / "generated" / "aaa"
    late = workspace / "generated" / "zzz"
    early.mkdir()
    late.mkdir()
    for index in range(personal_tools.WORKSPACE_FILE_CAP):
        (early / f"s{index:04d}.bin").write_bytes(b"x")
    (late / "big.bin").write_bytes(b"x" * 5000)

    def early_then_late(
        top: str, topdown: bool = True, onerror: Any = None, followlinks: bool = False
    ):
        if Path(top) == workspace / "generated":
            names = sorted(path.name for path in early.iterdir() if path.is_file())
            yield str(early), [], names
            yield str(late), [], ["big.bin"]
            return
        yield from os.walk(top, topdown=topdown, onerror=onerror, followlinks=followlinks)

    monkeypatch.setattr(personal_tools.os, "walk", early_then_late)
    out = json.loads(run_read_tool("workspace_files", {"path": "generated"}, workspace / "tasks"))
    assert out["scanned"] == personal_tools.WORKSPACE_FILE_CAP + 1
    assert out["truncated"] is True
    assert out["count"] == personal_tools.WORKSPACE_FILE_CAP
    assert out["files"][0] == {"path": "generated/zzz/big.bin", "size": 5000}


def test_workspace_files_accepts_the_container_prefix(workspace: Path) -> None:
    out = json.loads(
        run_read_tool("workspace_files", {"path": "/workspace/generated"}, workspace / "tasks")
    )
    assert out["count"] == 3


def test_workspace_files_rejects_traversal(workspace: Path) -> None:
    with pytest.raises(ValueError, match="outside"):
        run_read_tool("workspace_files", {"path": "../"}, workspace / "tasks")
    with pytest.raises(ValueError, match="outside"):
        run_read_tool("workspace_files", {"path": "generated/../../etc"}, workspace / "tasks")


def test_workspace_files_missing_dir_is_empty(workspace: Path) -> None:
    out = json.loads(run_read_tool("workspace_files", {"path": "nope"}, workspace / "tasks"))
    assert out["count"] == 0 and out["files"] == []


# ── Junk/templated memory write gate (J6 confirm-to-write content guard) ───────


def test_unfilled_placeholder_matcher() -> None:
    assert graph_memory.unfilled_placeholder("contains {line_count} lines") == "{line_count}"
    assert (
        graph_memory.unfilled_placeholder("Row count is <output_of_previous_step>")
        == "<output_of_previous_step>"
    )
    assert graph_memory.unfilled_placeholder("The file has 12 lines.") is None
    assert graph_memory.unfilled_placeholder("a < b and c > d") is None
    assert graph_memory.unfilled_placeholder("use the <div> tag") is None


def test_remember_rejects_unfilled_placeholders_before_any_embed() -> None:
    for text in (
        "The file /workspace/report.txt contains {line_count} lines.",
        "Row count for /workspace/data.csv is <output_of_previous_step>.",
    ):
        payload, status = asyncio.run(graph_memory._remember_impl({"text": text}))
        assert status == 400
        assert "placeholder" in payload["error"]


def test_remember_clean_text_passes_the_placeholder_gate() -> None:
    # The gate is before embedding; a clean text must not be rejected as a placeholder.
    assert (
        graph_memory.unfilled_placeholder("The file /workspace/report.txt contains 12 lines.")
        is None
    )


# ── One-shot cleanup selection logic ───────────────────────────────────────────


def test_cleanup_selects_only_placeholder_rows() -> None:
    from scripts.cleanup_junk_memories import junk_rows

    rows = [
        {"id": "1", "text": "The file /workspace/report.txt contains {line_count} lines."},
        {"id": "2", "text": "Row count for /workspace/data.csv is <output_of_previous_step>."},
        {"id": "3", "text": "The operator prefers Telegram replies under 400 characters."},
    ]
    selected = junk_rows(rows)
    assert {r["id"] for r in selected} == {"1", "2"}
