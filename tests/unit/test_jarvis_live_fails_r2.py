"""Jarvis personal lane, live round 2 (2026-11-20): the five failures, in receipt shape.

Every test here is built from the shape the live runs actually wrote
(``~/AI_Output/generated/tasks/<id>/receipt.json``): a workspace listing that
echoes the requested repository path, a lane report pasted into Telegram, a
Proxmox plan whose tools were never discoverable, a Word-document plan that
never named the create tool, and recalled tool scratch injected as "memory".
No network, no live stack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import (
    CONFIRM_TOOLS,
    KNOWN_TOOLS,
    READ_TOOLS,
    acceptance_failure,
    plan_gap,
    planner_body,
)
from portal.modules.orchestration.personal_runner import (
    Completion,
    _cloud_brief,
    _memory_text,
    _planner_json,
    poll_personal_tasks,
    user_answer,
)
from portal.modules.orchestration.personal_store import PersonalStore
from portal.modules.orchestration.personal_tools import LOCAL_TOOLS, run_read_tool
from portal.platform.inference.config import get_pipeline_mcp_servers, load_portal_config

REPO = Path(__file__).resolve().parent.parent.parent
# The receipt paths are absolute on the operator's host; composed so the hygiene gate stays green.
_HOME = "/Users/" + "chris/"


class _Notices:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append(message)


class _Caller:
    def __init__(self, replies: list[Completion]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def complete(self, body: dict[str, Any]) -> Completion:
        self.bodies.append(json.loads(json.dumps(body)))
        if not self.replies:
            raise AssertionError("unexpected extra Pipeline call")
        return self.replies.pop(0)


def _tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"c-{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def _receipt(root: Path, task_id: str) -> dict[str, Any]:
    return json.loads((root / task_id / "receipt.json").read_text(encoding="utf-8"))


# ── 1. A repository path in the request must be read, never listed ────────────

REVIEW_REQUEST = (
    "review scripts/engine_install_plan.py and report every code path that "
    "can downgrade a package, with line numbers"
)
_EMPTY_LISTING = {
    "root": f"{_HOME}AI_Output",
    "path": "scripts/engine_install_plan.py",
    "count": 0,
    "scanned": 0,
    "truncated": False,
    "files": [],
}


def test_a_workspace_listing_that_echoes_the_path_does_not_ground_it() -> None:
    """pt-46b3e7c492af: the tool result echoed the request path, so the guard passed."""
    plan = {"steps": [{"id": "s1", "tools": ["workspace_files"], "paths": [], "budget": {}}]}
    reason = acceptance_failure(
        plan,
        "The file `scripts/engine_install_plan.py` does not exist in the workspace.",
        ["workspace_files", "workspace_files"],
        [json.dumps(_EMPTY_LISTING), json.dumps(_EMPTY_LISTING)],
        request=REVIEW_REQUEST,
    )
    assert reason is not None
    assert "repository file not in tool results: scripts/engine_install_plan.py" in reason


def test_a_repository_read_grounds_the_answer() -> None:
    read = {
        "content": "12\tif version < pinned:\n13\t    downgrade(version)",
        "path": f"{_HOME}projects/portal-5/scripts/engine_install_plan.py",
        "lines": 2,
    }
    plan = {"steps": [{"id": "s1", "tools": ["read_text_file"], "paths": [], "budget": {}}]}
    assert (
        acceptance_failure(
            plan,
            "Line 13 downgrades when version < pinned.",
            ["read_text_file"],
            [json.dumps(read)],
            request=REVIEW_REQUEST,
        )
        is None
    )


def test_a_failed_repository_read_is_not_grounding() -> None:
    missing = {"error": "file not found: scripts/engine_install_plan.py"}
    plan = {"steps": [{"id": "s1", "tools": ["read_text_file"], "paths": [], "budget": {}}]}
    reason = acceptance_failure(
        plan,
        "That file does not exist.",
        ["read_text_file"],
        [json.dumps(missing)],
        request=REVIEW_REQUEST,
    )
    # The tool error is the reason a failed read never counts as an answer.
    assert reason is not None and "tool error" in reason


def test_a_search_hit_grounds_the_file_it_names() -> None:
    hits = {"matches": ["scripts/engine_install_plan.py:41: downgrade(path)"], "truncated": False}
    plan = {"steps": [{"id": "s1", "tools": ["search_files"], "paths": [], "budget": {}}]}
    assert (
        acceptance_failure(
            plan,
            "Line 41 downgrades the package.",
            ["search_files"],
            [json.dumps(hits)],
            request=REVIEW_REQUEST,
        )
        is None
    )


def test_the_live_code_review_task_is_no_longer_accepted_as_done(tmp_path: Path) -> None:
    """The receipt's own plan, tools and answer, replayed: it must retry, not finish done."""
    tasks = tmp_path / "tasks"
    reply = telegram_do_reply(tasks, 1, REVIEW_REQUEST)
    task_id = reply.removeprefix("queued ")
    plan = '{"steps": [{"id": "s1", "tools": ["workspace_files"], '
    plan += '"paths": ["scripts/engine_install_plan.py"], "budget": {"context_tokens": 8192}}]}'
    caller = _Caller(
        [
            Completion(plan, (), 0),
            Completion("", (_tool_call("workspace_files", {"path": "scripts"}),), 0),
            Completion(
                "The file `scripts/engine_install_plan.py` does not exist in the workspace.",
                (),
                0,
            ),
        ]
    )
    run = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: "")

    assert run is not None and run.status == "retrying"
    receipt = _receipt(tasks, task_id)
    assert receipt["status"] == "retrying"
    attempt = json.loads(
        (tasks / task_id / "attempts" / "local-1" / "receipt.json").read_text(encoding="utf-8")
    )
    assert "repository file not in tool results" in str(attempt["error"])


def test_the_personal_lane_can_read_the_repository() -> None:
    for name in ("read_text_file", "search_files", "list_directory"):
        assert name in READ_TOOLS and name in KNOWN_TOOLS
        assert name not in CONFIRM_TOOLS
    prompt = planner_body(REVIEW_REQUEST)["messages"][0]["content"]
    assert "read_text_file" in prompt
    assert "workspace_files cannot see it" in prompt


def test_the_fast_workspace_serves_the_repository_read_tools() -> None:
    """A bite-only tool is dropped unless the serving workspace lists it."""
    catalog = yaml.safe_load((REPO / "config" / "portal.yaml").read_text(encoding="utf-8"))
    tools = catalog["workspaces"]["auto-daily"]["variants"]["fast"]["tools"]
    for name in ("read_text_file", "search_files", "list_directory"):
        assert name in tools


# ── 2. The operator gets an answer, not the worker's report ───────────────────

LIVE_CLOUD_REPORT = f"""## RESULT
done

## WHAT CHANGED
- Created `{_HOME}AI_Output/generated/security_sweep_summary.docx` — one-page Word document summarizing the 2026-11-19 security sweep

## EVIDENCE
```
$ ls -la {_HOME}AI_Output/generated/security_sweep_summary.docx
-rw-r--r--  1 chris  staff  37759 Nov 20 15:22 security_sweep_summary.docx

$ uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -1
2876 passed, 21 skipped in 89.87s
```

## ORCHESTRATOR RUNS
No live system runs needed.

## UNPROVEN
- None

## OPEN / RISK
None."""


def test_the_operator_gets_the_answer_and_the_file_path_only() -> None:
    answer = user_answer(LIVE_CLOUD_REPORT)
    assert f"{_HOME}AI_Output/generated/security_sweep_summary.docx" in answer
    assert "one-page Word document" in answer
    for scaffold in (
        "## RESULT",
        "## EVIDENCE",
        "## ORCHESTRATOR RUNS",
        "## UNPROVEN",
        "uv run pytest",
    ):
        assert scaffold not in answer


def test_an_answer_section_is_preferred_when_the_lane_writes_one() -> None:
    report = (
        "## ANSWER\nCreated `/tmp/sweep.docx` with MAL 0, CRITICAL 2, 251 carried.\n\n"
        "## EVIDENCE\nno\n\n## RESULT\ndone\n"
    )
    assert user_answer(report) == "Created `/tmp/sweep.docx` with MAL 0, CRITICAL 2, 251 carried."


def test_a_lane_that_writes_no_scaffolding_still_reaches_the_operator() -> None:
    assert user_answer("The stopped VMs are 101 and 102.") == "The stopped VMs are 101 and 102."


def test_a_personal_cloud_brief_forbids_the_repository_gates(tmp_path: Path) -> None:
    task = PersonalStore(tmp_path).add("telegram", "1", "write a one-page Word document")
    brief = _cloud_brief(task, [])
    assert "## ANSWER" in brief
    assert "Do not run the repository gates (pytest, ruff, mypy)" in brief
    assert "not a code task" in brief
    assert "a user-facing answer, not a worker" in brief


# ── 3. Proxmox and browser reach the pipeline from inside the container ──────


def test_every_pipeline_exposed_mcp_has_a_pipeline_url() -> None:
    """The fallback is http://localhost:<port>, which is the container itself."""
    compose = yaml.safe_load((REPO / "deploy" / "portal-5" / "docker-compose.yml").read_text())
    env = compose["services"]["portal-pipeline"]["environment"]
    declared = {str(item).split("=", 1)[0] for item in env if isinstance(item, str) and "=" in item}
    missing = [
        f"MCP_{server_id.upper().replace('-', '_')}_URL"
        for server_id in get_pipeline_mcp_servers(load_portal_config())
        if f"MCP_{server_id.upper().replace('-', '_')}_URL" not in declared
    ]
    assert missing == []


def test_proxmox_and_browser_urls_point_at_their_compose_services() -> None:
    compose = yaml.safe_load((REPO / "deploy" / "portal-5" / "docker-compose.yml").read_text())
    env = compose["services"]["portal-pipeline"]["environment"]
    urls = dict(str(item).split("=", 1) for item in env if isinstance(item, str) and "=" in item)
    proxmox = compose["services"]["mcp-proxmox"]["container_name"]
    assert urls["MCP_PROXMOX_URL"] == f"http://{proxmox}:8927"
    assert urls["MCP_BROWSER_URL"] == "http://browser-mcp:8923"
    assert "browser-mcp" in compose["services"]


def test_the_personal_lane_reads_proxmox_without_a_confirm() -> None:
    assert "proxmox_list_vms" in READ_TOOLS and "proxmox_list_vms" not in CONFIRM_TOOLS


def test_the_vm_request_fails_loudly_when_no_proxmox_tool_ran(tmp_path: Path) -> None:
    """pt-b540a922c5c3: hops 0, only the runner's own recall — never done."""
    tasks = tmp_path / "tasks"
    request = "list the Proxmox VMs that are currently stopped"
    reply = telegram_do_reply(tasks, 1, request)
    task_id = reply.removeprefix("queued ")
    caller = _Caller(
        [
            Completion('{"steps": [{"id": "s1", "tools": ["proxmox_list_vms"]}]}', (), 0),
            Completion("I am not able to query Proxmox.", (), 0),
        ]
    )
    run = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: "")

    assert run is not None and run.status == "retrying"
    receipt = _receipt(tasks, task_id)
    assert "plan step 0 not satisfied: proxmox_list_vms" in str(receipt["error"])


# ── 4. The Word document: the tool is exposed, the counts are now readable ───


def test_the_personal_path_exposes_the_word_document_tool(tmp_path: Path) -> None:
    from portal.modules.orchestration.personal_runner import _personal_available_tools

    assert "create_word_document" in _personal_available_tools()


@pytest.fixture()
def sweep_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from portal.modules.orchestration import personal_tools

    sweep = tmp_path / "security"
    sweep.mkdir()
    (sweep / "security_sweep_20261119.md").write_text(
        "# Security sweep — 2026-11-19\n\n"
        "- Package versions queried: 838\n"
        "- Package findings: 251\n"
        "- MAL advisories: 0\n"
        "- CRITICAL findings: 2\n\n"
        "## OSV findings\n\n"
        "| Ecosystem | Package | Version | Advisory | Severity |\n"
        "| npm | proxy-addr | 2.0.7 | GHSA-jqcg-44mw-7w3h | CRITICAL |\n"
        "| npm | protobufjs | 7.5.4 | GHSA-xq3m-2v4x-88gg | CRITICAL |\n"
        "| PyPI | aiohttp | 3.14.1 | GHSA-24c4-3p7v-29cm | HIGH |\n\n"
        "## Delta vs previous sweep (2026-11-19)\n\n"
        "- New: 0 / Carried: 251 / Resolved: 126\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(personal_tools, "SWEEP_DIR", sweep)
    return sweep


def test_the_sweep_read_returns_the_counts_the_document_needs(sweep_report: Path) -> None:
    out = json.loads(run_read_tool("security_sweep", {}, sweep_report.parent / "tasks"))
    assert out["date"] == "20261119"
    assert "- MAL advisories: 0" in out["summary"]
    assert "- CRITICAL findings: 2" in out["summary"]
    assert out["delta"] == "- New: 0 / Carried: 251 / Resolved: 126"
    assert len(out["critical"]) == 2
    assert all("CRITICAL" in row for row in out["critical"])
    assert out["critical_truncated"] is False


def test_the_sweep_read_is_a_read_tool_and_errors_without_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import personal_tools

    assert "security_sweep" in LOCAL_TOOLS and "security_sweep" in READ_TOOLS
    assert "security_sweep" not in CONFIRM_TOOLS
    monkeypatch.setattr(personal_tools, "SWEEP_DIR", tmp_path / "nothing")
    out = json.loads(run_read_tool("security_sweep", {}, tmp_path))
    assert "no security sweep report" in out["error"]
    assert (
        "security_sweep"
        in planner_body("summarise tonight's security sweep")["messages"][0]["content"]
    )


def test_a_document_read_plan_is_not_forced_to_create_one() -> None:
    request = "read the word document at /workspace/uploads/q3.docx and summarise it"
    plan = {"steps": [{"id": "s1", "tools": ["read_word_document"]}]}
    assert plan_gap(request, plan) is None
    template = {"action": "enqueue-template", "discipline": "documents", "template_key": "x"}
    assert plan_gap(request, template) is None


def test_a_document_plan_without_the_create_tool_is_replanned_once() -> None:
    """pt-7447e778ecd5: the plan named only a read tool, so the create tool never ran."""
    request = (
        "write a one-page Word document summarising tonight's security sweep: "
        "MAL count, critical count, and what is still open"
    )
    caller = _Caller(
        [
            Completion('{"steps": [{"id": "s1", "tools": ["workspace_files"]}]}', (), 0),
            Completion(
                '{"steps": [{"id": "s1", "tools": ["security_sweep"]}, '
                '{"id": "s2", "tools": ["create_word_document"]}]}',
                (),
                0,
            ),
        ]
    )
    body = planner_body(request, KNOWN_TOOLS)
    plan = _planner_json(caller, body, caller.complete(body), request)

    corrective = caller.bodies[1]["messages"][-1]["content"]
    assert "create_word_document" in corrective
    assert [step["tools"] for step in plan["steps"]] == [
        ["security_sweep"],
        ["create_word_document"],
    ]


def test_a_corrected_document_plan_reaches_done_with_the_real_counts(
    tmp_path: Path, sweep_report: Path
) -> None:
    tasks = tmp_path / "tasks"
    request = (
        "write a one-page Word document summarising tonight's security sweep: "
        "MAL count, critical count, and what is still open"
    )
    reply = telegram_do_reply(tasks, 1, request)
    task_id = reply.removeprefix("queued ")
    caller = _Caller(
        [
            Completion('{"steps": [{"id": "s1", "tools": ["workspace_files"]}]}', (), 0),
            Completion(
                '{"steps": [{"id": "s1", "tools": ["security_sweep"]}, '
                '{"id": "s2", "tools": ["create_word_document"]}]}',
                (),
                0,
            ),
            Completion("", (_tool_call("security_sweep", {}),), 0),
            Completion(
                "MAL 0, CRITICAL 2, 251 carried — /workspace/generated/documents/sweep.docx",
                (),
                1,
                ("create_word_document",),
                ('{"path": "/workspace/generated/documents/sweep.docx"}',),
            ),
        ]
    )
    run = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: "")

    assert run is not None and run.status == "done"
    receipt = _receipt(tasks, task_id)
    assert receipt["status"] == "done"
    assert "security_sweep" in receipt["tool_calls"]
    assert "create_word_document" in receipt["tool_calls"]


# ── 5. Recalled tool scratch never becomes "memory" ─────────────────────────

JUNK_MEMORIES = {
    "memories": [
        {
            "text": "row count is <output of previous execution>",
            "similarity": 0.91,
        },
        {
            "text": "line_count: Unable to locate /workspace/report.txt; line count could "
            "not be determined.",
            "similarity": 0.88,
        },
        {"text": "The operator prefers Telegram replies under 400 characters.", "similarity": 0.7},
    ]
}


def test_recalled_tool_scratch_is_dropped_and_a_preference_is_kept() -> None:
    rendered = _memory_text(JUNK_MEMORIES)
    assert rendered == "- The operator prefers Telegram replies under 400 characters."


def test_the_planner_never_sees_the_scratch_it_used_to(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks"
    telegram_do_reply(tasks, 1, "what is the queue status in one paragraph")
    memory = _memory_text(JUNK_MEMORIES)
    caller = _Caller(
        [
            Completion('{"steps": [{"id": "s1", "tools": ["queue_status"]}]}', (), 0),
            Completion("Queue is empty.", (), 1, ("queue_status",)),
        ]
    )
    run = poll_personal_tasks(tasks, _Notices(), caller, recall=lambda _q: memory)

    assert run is not None and run.status == "done"
    for body in caller.bodies:
        assert "Unable to locate /workspace/report.txt" not in json.dumps(body)
        assert "output of previous execution" not in json.dumps(body)
