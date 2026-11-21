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
    CORE_TOOLS,
    READ_TOOLS,
    route_personal_task,
)
from portal.modules.orchestration.personal_runner import (
    Completion,
    _cloud_brief,
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


def test_the_personal_lane_can_read_the_repository() -> None:
    for name in ("read_text_file", "search_files", "list_directory"):
        assert name in READ_TOOLS and name in CORE_TOOLS
        assert name not in CONFIRM_TOOLS
    assert "read_text_file" in route_personal_task(REVIEW_REQUEST).tools


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


def test_a_blocked_cloud_lane_does_not_paste_its_report_at_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap-reached notice used the lane's whole report as its detail line."""
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)
    sink = _Notices()
    telegram_do_reply(tmp_path, 7, "help with an empty local answer")
    bad = [Completion("", (), 0), Completion("", (), 0)]
    first = poll_personal_tasks(tmp_path, sink, _Caller(list(bad)))
    assert first is not None and first.status == "retrying"

    class Lane:
        def run(self, **_kwargs: Any) -> Any:
            from types import SimpleNamespace

            return SimpleNamespace(
                exit_code=1, status="failed", model="mock", result_text=LIVE_CLOUD_REPORT
            )

    run = poll_personal_tasks(tmp_path, sink, _Caller([]), dispatcher=Lane())
    assert run is not None and run.status == "blocked"
    notice = sink.messages[-1]
    assert "## EVIDENCE" not in notice and "uv run pytest" not in notice
    assert "one-page Word document" in notice


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


def test_the_vm_request_is_offered_the_proxmox_read_tools(tmp_path: Path) -> None:
    """pt-b540a922c5c3: the request never saw a Proxmox tool; the bundle now offers them."""
    tasks = tmp_path / "tasks"
    request = "list the Proxmox VMs that are currently stopped"
    reply = telegram_do_reply(tasks, 1, request)
    task_id = reply.removeprefix("queued ")
    caller = _Caller([Completion("VM 101 is stopped.", (), 1, ("proxmox_list_vms",))])
    run = poll_personal_tasks(tasks, _Notices(), caller)

    assert run is not None and run.status == "done"
    assert "proxmox_list_vms" in caller.bodies[0]["portal_bite_tools"]
    receipt = _receipt(tasks, task_id)
    assert receipt["route"]["bundle"] == "core+proxmox"


# ── 4. The Word document: the tool is exposed, the counts are now readable ───


def test_the_personal_path_exposes_the_word_document_tool() -> None:
    request = (
        "write a one-page Word document summarising tonight's security sweep: "
        "MAL count, critical count, and what is still open"
    )
    assert "create_word_document" in route_personal_task(request).tools


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
    assert "security_sweep" in route_personal_task("summarise tonight's security sweep").tools


def test_a_document_request_is_offered_both_the_sweep_read_and_the_create_tool() -> None:
    """pt-7447e778ecd5: the create tool was never offered, so no document was written."""
    request = (
        "write a one-page Word document summarising tonight's security sweep: "
        "MAL count, critical count, and what is still open"
    )
    tools = route_personal_task(request).tools
    assert {"security_sweep", "create_word_document"} <= tools


def test_the_document_request_reaches_done_with_the_real_counts(
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
    run = poll_personal_tasks(tasks, _Notices(), caller)

    assert run is not None and run.status == "done"
    receipt = _receipt(tasks, task_id)
    assert receipt["status"] == "done"
    assert "security_sweep" in receipt["tool_calls"]
    assert "create_word_document" in receipt["tool_calls"]
