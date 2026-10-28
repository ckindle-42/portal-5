#!/usr/bin/env python3
"""Run orchestration discipline suites against one Pipeline workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from portal.modules.orchestration.contracts import Bite, Budget  # noqa: E402
from portal.modules.orchestration.disciplines.detection_engineering import run_checker  # noqa: E402
from portal.modules.orchestration.planner import (  # noqa: E402
    instantiate_plan_template,
    planner_prompt,
    validate_planned_plan,
)
from portal.modules.orchestration.tools import (  # noqa: E402
    ACTION_TOOLS,
    READ_TOOLS,
    TASK_DATA_DIRECTORY,
    TaskToolExecutor,
)
from portal.modules.orchestration.worker import Engine, run_bite  # noqa: E402
from portal.platform.inference.router.text_tool_calls import TEXT_TOOL_CALL_MARKERS  # noqa: E402
from portal.platform.inference.router.thinking import NO_ANSWER_MESSAGE  # noqa: E402
from portal.platform.mcp_host.workspace import get_generated_dir  # noqa: E402
from scripts import host_quiet  # noqa: E402

PLANNER_MAX_TOKENS = 8192  # mirrors portal/modules/orchestration/planner.py plan_goal

DEFAULT_PIPELINE = "http://localhost:9099"
DEFAULT_TIMEOUT = 300


class SuiteEngine(Engine):
    """Pipeline client that captures tool audit and served-seat evidence."""

    def __init__(self, model_tag: str, base_url: str, api_key: str = "") -> None:
        super().__init__(model_tag, "trial", base_url, api_key)
        self.correlation_id = ""
        self.last_trace: dict[str, Any] = {}
        self.last_response: dict[str, Any] = {}
        self.bite_responses: list[dict[str, Any]] = []
        self.audit_calls: list[dict[str, Any]] = []
        self.expected_bite_tools: tuple[str, ...] | None = None

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        if self.correlation_id:
            headers["X-Correlation-ID"] = self.correlation_id
        return headers

    def chat(self, body: dict[str, Any], timeout: float, on_event: Any) -> dict[str, Any]:
        if self.expected_bite_tools is not None:
            self._validate_bite_request(body)
            body = {**body, "exec_audit": True}
        else:
            self.audit_calls = []
        self.correlation_id = f"bite-{uuid4().hex[:16]}"
        self.last_response = {}

        def capture(event: dict[str, Any]) -> None:
            if event.get("type") == "exec_audit":
                self.audit_calls.extend(_audit_calls(event))
            on_event(event)

        try:
            response = super().chat(body, timeout, capture)
            self.last_response = response
            self.bite_responses.append(response)
            return response
        finally:
            cid = self.correlation_id
            self.correlation_id = ""
            self.last_trace = self._read_trace(cid)

    def _validate_bite_request(self, body: dict[str, Any]) -> None:
        expected = set(self.expected_bite_tools or ())
        allowed = body.get("portal_bite_tools")
        raw_schemas = body.get("tools")
        schemas = raw_schemas if isinstance(raw_schemas, list) else []
        schema_names = {
            tool.get("function", {}).get("name")
            for tool in schemas
            if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
        }
        if (
            not isinstance(allowed, list)
            or not all(isinstance(name, str) for name in allowed)
            or set(allowed) != expected
            or schema_names != expected
            or "chat_template_kwargs" in body
            or "portal_bite_max_hops" not in body
        ):
            raise HarnessError(
                "arm worker bite tool request is missing tools, finish, or hop limits, or forces thinking"
            )

    def _read_trace(self, cid: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}/v1/trace/{cid}",
                headers=self._headers(),
                timeout=5,
            )
            response.raise_for_status()
            value = response.json()
            return value if isinstance(value, dict) else {}
        except (httpx.HTTPError, ValueError):
            return {}


class HarnessError(RuntimeError):
    """The suite request or response did not preserve the arm worker contract."""


def _audit_calls(event: dict[str, Any]) -> list[dict[str, Any]]:
    raw = event.get("tool_calls")
    if not isinstance(raw, list):
        return []
    out = []
    for call in raw:
        if not isinstance(call, dict):
            continue
        arguments = call.get("arguments", {})
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            args = None
        output = call.get("output")
        out.append(
            {
                "name": call.get("tool", ""),
                "args": args,
                "output": output,
                "error": output
                if isinstance(output, str) and output.startswith("ERROR:")
                else None,
            }
        )
    return out


def load_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("disciplines"), dict):
        raise ValueError(f"{path} must define disciplines")
    return raw


def load_suite(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        cases = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        raw = yaml.safe_load(text)
        cases = raw.get("cases", raw.get("controls")) if isinstance(raw, dict) else raw
    if not isinstance(cases, list) or not cases or not all(isinstance(x, dict) for x in cases):
        raise ValueError(f"{path} must contain a non-empty cases list")
    ids = [case.get("id") for case in cases]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"{path} cases need unique non-empty ids")
    return cases


def _selected_suites(config: dict[str, Any], discipline: str, suite: str) -> dict[str, Path]:
    entry = config["disciplines"].get(discipline)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown orchestration discipline: {discipline}")
    names = ("bite", "planner", "checker") if suite == "all" else (suite,)
    paths = {}
    for name in names:
        relative = entry.get(f"{name}_suite")
        path = (ROOT / str(relative)).resolve()
        if not isinstance(relative, str) or not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f"{discipline}.{name}_suite is missing or outside the repository")
        paths[name] = path
    return paths


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-") or "case"


def _workspace_path(path: Path) -> str:
    root = Path(os.environ.get("AI_OUTPUT_DIR", "~/AI_Output")).expanduser().resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("seeded bite workspaces must be under AI_OUTPUT_DIR for Pipeline tools")
    return "/workspace/" + resolved.relative_to(root).as_posix()


def _write_seeds(case: dict[str, Any], task_dir: Path) -> list[str]:
    seeds = case.get("seed", {})
    if not isinstance(seeds, dict):
        raise ValueError(f"{case['id']} seed must be an object")
    names = []
    for name, content in seeds.items():
        relative = Path(str(name))
        if relative.is_absolute() or ".." in relative.parts or not isinstance(content, str):
            raise ValueError(f"{case['id']} has an invalid seed file")
        data_dir = task_dir / TASK_DATA_DIRECTORY
        target = (data_dir / relative).resolve()
        if not target.is_relative_to(data_dir.resolve()):
            raise ValueError(f"{case['id']} seed escapes the task directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        names.append(str(relative))
    return names


def _bite_contract(
    case: dict[str, Any], discipline: str, task_dir: Path, *, dry_run: bool
) -> tuple[Bite, dict[str, Path]]:
    tools = case.get("requires_tools", case.get("tools", []))
    if not isinstance(tools, list) or not all(isinstance(x, str) for x in tools):
        raise ValueError(f"{case['id']} tools must be a list")
    seed_names = _write_seeds(case, task_dir)
    input_paths = {name: Path(name) for name in seed_names}
    procedure = str(case.get("instruction", ""))
    if case.get("seed_artifact") is not None:
        procedure += "\nSeed artifact: " + json.dumps(case["seed_artifact"], ensure_ascii=False)
    bite = Bite(
        bite_id=_safe_name(case["id"]),
        goal=str(case.get("goal") or case.get("instruction") or case["id"]),
        discipline=discipline,
        inputs=tuple(seed_names),
        write_paths=tuple(
            str(name)
            for checker in case.get("checkers", [])
            if checker.get("type") == "hidden_pytest"
            for name in checker.get("impl_files", [])
        ),
        depends_on=(),
        tools=tuple(tools),
        output_path="bite-output.txt" if seed_names else "bite-output.json",
        output_schema=case.get("artifact_schema") if not seed_names else None,
        file_type="text" if seed_names else None,
        accept=(),
        review=None,
        review_reason=None,
        risk="low",
        stage="work",
        budget=Budget(turns=8, minutes=DEFAULT_TIMEOUT / 60, output_tokens=4096),
        model="fast",
        procedure=procedure,
        reads_untrusted=False,
    )
    return bite, input_paths


def _plan_template(
    config: dict[str, Any], discipline: str, task_dir: Path, case_id: str
) -> dict[str, Any]:
    entry = config["disciplines"][discipline]
    templates = entry.get("plan_templates")
    if not isinstance(templates, dict) or not templates:
        raise ValueError(f"{discipline} has no plan template for planner-suite fixtures")
    template_key = next(iter(templates))
    declared = templates[template_key].get("parameters", [])
    values = {
        "source_file": "source.py",
        "test_file": "test_source.py",
        "expected_behavior": "returns the required result",
        "reference_file": "reference.spl",
        "technique": "T1110.001",
    }
    for name in ("source.py", "test_source.py", "reference.spl"):
        (task_dir / name).write_text("fixture\n", encoding="utf-8")
    parameters = {name: values[name] for name in declared}
    plan = instantiate_plan_template(
        config,
        template_key=template_key,
        discipline_key=discipline,
        task_id=f"suite-{_safe_name(case_id)}",
        parameters=parameters,
        source_dir=task_dir,
    )
    return plan.as_dict()


def _invalid_plan(
    case: dict[str, Any], plan: dict[str, Any], config: dict[str, Any], discipline: str
) -> dict[str, Any]:
    if case.get("expected") != "reject":
        return plan
    rule = str(case.get("rule", "")).casefold()
    discipline_config = config["disciplines"][discipline]
    if "context" in rule:
        planner = config.get("planner", {})
        limit = min(
            int(planner.get("comfortable_context_tokens", 1)),
            int(discipline_config.get("fast_context_budget_tokens", 1)),
        )
        plan["bites"][0]["budget"]["context_tokens"] = limit + 1
    elif "untrusted" in rule:
        plan["bites"][0]["reads_untrusted"] = True
        plan["bites"][0]["tools"] = list(discipline_config.get("action_tools", []))[:1]
    elif "mixed" in rule or "separated" in rule:
        plan["bites"][0]["tools"] = [
            *list(discipline_config.get("read_tools", []))[:1],
            *list(discipline_config.get("action_tools", []))[:1],
        ]
    elif "closure" in rule or "assembly" in rule:
        plan["bites"][-1]["stage"] = "work"
    elif "check" in rule or "review" in rule:
        plan["bites"][0]["accept"] = []
        plan["bites"][0].pop("review", None)
        plan["bites"][0].pop("review_reason", None)
    else:
        raise ValueError(f"no invalid-plan fixture for rule {rule!r}")
    return plan


def _planner_messages(
    case: dict[str, Any], config: dict[str, Any], discipline: str, task_dir: Path
) -> list[dict[str, str]]:
    plan = _invalid_plan(
        case,
        _plan_template(config, discipline, task_dir, case["id"]),
        config,
        discipline,
    )
    expected_pass = case.get("expected") == "pass"
    try:
        validate_planned_plan(plan, config, discipline, task_dir)
        actual_pass = True
    except ValueError:
        actual_pass = False
    if actual_pass != expected_pass:
        raise ValueError(
            f"{case['id']} fixture does not match its expected {case.get('expected')} verdict"
        )
    policy = planner_prompt(config, discipline)
    system = (
        f"{policy}\nReview the supplied plan as the validator would. "
        "Return JSON with verdict PASS or REJECT and a concise reason."
    )
    user = {"case_id": case["id"], "rule": case.get("rule"), "plan": plan}
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, sort_keys=True)},
    ]


def _checker_cases(suite_path: Path) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    cases = suite.get("cases", []) if isinstance(suite, dict) else []
    if suite_path.name == "wfe_checker_suite.yaml":
        controls_path = (ROOT / suite["controls_file"]).resolve()
        controls_data = yaml.safe_load(controls_path.read_text(encoding="utf-8"))
        controls = {item["id"]: item for item in controls_data.get("controls", [])}
        out = []
        for case in cases:
            control = controls[case["control_id"]]
            for label in ("pass", "fail"):
                fixture = {"checker": control["checker"], **control[label]}
                verdict = run_checker(control["checker"], fixture["artifact"], fixture["calls"])
                if verdict.passed is not (label == "pass"):
                    raise ValueError(f"{case['id']} {label} checker control is invalid")
                out.append((case, label, fixture))
        return out
    return [
        (
            case,
            str(case.get("expected", "reject")),
            {
                "output": case.get("output"),
                "checks": case.get("checks", []),
                "schema": case.get("schema"),
            },
        )
        for case in cases
    ]


def _checker_messages(
    case: dict[str, Any], label: str, fixture: dict[str, Any]
) -> list[dict[str, str]]:
    system = (
        "Judge whether the supplied artifact satisfies the supplied deterministic checks. "
        "A check counts only when a call to its tool used exactly the artifact's "
        "artifact_field value; validating different content does not validate the artifact, "
        "even if that content is itself valid. "
        "Return JSON with verdict PASS or REJECT and a concise reason."
    )
    user = {"case_id": case["id"], "fixture": fixture}
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, sort_keys=True)},
    ]


def _response_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = message.get("content", "")
    return content if isinstance(content, str) else ""


# A whole-reply ```json fence only. Prose or tool-call text around JSON stays invalid.
_JSON_FENCE = re.compile(
    r"^```json[ \t]*\r?\n(.*)\r?\n```[ \t]*$",
    re.DOTALL | re.IGNORECASE,
)


def _json_document(content: str) -> str:
    match = _JSON_FENCE.fullmatch(content.strip())
    return match.group(1) if match else content


def _verdict(content: str) -> str:
    value = json.loads(_json_document(content))
    verdict = value.get("verdict") if isinstance(value, dict) else None
    if verdict not in {"PASS", "REJECT"}:
        raise ValueError("response JSON must contain verdict PASS or REJECT")
    return verdict


def _score_json_verdict(content: str, label: str) -> tuple[str, str, dict[str, Any]]:
    """Score a planner/checker reply. Empty content stays blocked; bad JSON is a model fail."""
    expected = "PASS" if label == "pass" else "REJECT"
    # The stream substitutes this sentinel when the model emits no answer text.
    if not content.strip() or content.strip() == NO_ANSWER_MESSAGE:
        return "blocked", "BLOCKED", {"error": "empty model content"}
    try:
        actual = _verdict(content)
    except json.JSONDecodeError as exc:
        return "failed", "FAIL", {"expected": expected, "error": f"JSONDecodeError: {exc}"}
    except ValueError as exc:
        return "failed", "FAIL", {"expected": expected, "error": f"ValueError: {exc}"}
    passed = actual == expected
    state, status = ("passed", "PASS") if passed else ("failed", "FAIL")
    return state, status, {"expected": expected, "observed": actual}


def _hidden_pytest(case: dict[str, Any], task_dir: Path) -> dict[str, Any]:
    checkers = case.get("checkers", [])
    checker = next((item for item in checkers if item.get("type") == "hidden_pytest"), None)
    if not checker:
        return {"passed": True, "detail": "no hidden pytest checker declared"}
    grade = (ROOT / "tests/wfe/graded" / str(checker["graded"])).resolve()
    if not grade.is_relative_to((ROOT / "tests/wfe/graded").resolve()) or not grade.is_dir():
        return {"passed": False, "detail": "hidden pytest fixture is unavailable"}
    data_dir = task_dir / TASK_DATA_DIRECTORY
    impl_files = checker.get("impl_files", [])
    missing = [name for name in impl_files if not (data_dir / name).is_file()]
    if missing:
        return {"passed": False, "detail": f"missing implementation files: {missing}"}
    hidden = data_dir / ".arm-hidden-tests"
    shutil.copytree(grade, hidden)
    try:
        readable = tuple(
            path.relative_to(data_dir).as_posix() for path in data_dir.rglob("*") if path.is_file()
        )
        output = TaskToolExecutor(data_dir, ("pytest_run",), readable_paths=readable).pytest_run(
            ".arm-hidden-tests"
        )
    finally:
        shutil.rmtree(hidden, ignore_errors=True)
    match = re.search(r"(\d+) passed", output)
    passed = int(match.group(1)) if match else 0
    minimum = int(checker.get("min_passed", 1))
    return {
        "passed": output.startswith("exit_code=0") and passed >= minimum,
        "passed_tests": passed,
        "required": minimum,
        "output": output,
    }


def _score_bite(
    case: dict[str, Any], output: Any, audit_calls: list[dict[str, Any]], task_dir: Path
) -> tuple[bool, dict[str, Any]]:
    if case.get("seed"):
        signal = str(case.get("completion_signal", ""))
        called = {call["name"] for call in audit_calls}
        required = set(case.get("requires_tools", []))
        tool_ok = required <= called
        modified_tests = [
            name
            for name, seeded in case["seed"].items()
            if Path(name).name.startswith("test_")
            and (task_dir / TASK_DATA_DIRECTORY / name).is_file()
            and (task_dir / TASK_DATA_DIRECTORY / name).read_text(encoding="utf-8") != seeded
        ]
        grade = _hidden_pytest(case, task_dir)
        passed = bool(
            signal and signal in str(output) and tool_ok and not modified_tests and grade["passed"]
        )
        return passed, {
            "completion_signal": signal in str(output),
            "required_tools": sorted(required),
            "observed_tools": sorted(called),
            "modified_tests": modified_tests,
            "hidden_pytest": grade,
        }
    artifact = output
    schema = case.get("artifact_schema")
    if not isinstance(schema, dict):
        return False, {"error": "bite suite case has no artifact_schema"}
    errors = sorted(
        Draft202012Validator(schema).iter_errors(artifact), key=lambda err: list(err.path)
    )
    if errors:
        return False, {
            "error": "artifact schema failed",
            "details": [error.message for error in errors[:5]],
        }
    checker = case.get("checker")
    if not isinstance(checker, dict):
        return True, {"schema": "PASS"}
    result = run_checker(checker, artifact, audit_calls)
    return result.passed, {"checker": result.detail, "evidence": result.evidence}


def _request_body(
    seat: str,
    messages: list[dict[str, str]],
    tools: list[str],
    *,
    json_output: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": seat,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if json_output:
        body["response_format"] = {"type": "json_object"}
        # Same output budget the production planner sends (planner.plan_goal). Without it the
        # seat's predict_limit (auto-daily: 4096) applied and Gemma's thinking hit the limit
        # before any answer on the longer planner prompts (2026-10-28: finish_reason=length,
        # reasoning only, 4 BLOCKED) — a suite-only divergence, not a model result.
        body["max_tokens"] = PLANNER_MAX_TOKENS
    if tools:
        body["portal_bite_tools"] = tools
        body["exec_audit"] = True
    else:
        body["portal_no_tools"] = True
    return body


def _live_identity(engine: SuiteEngine, seat: str) -> str | None:
    trace = engine.last_trace
    if trace.get("requested") != seat or not (trace.get("workspace") or trace.get("persona")):
        return "Pipeline trace did not verify the requested workspace/persona"
    return None


def _response_parts(response: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = message.get("content", "")
    calls = message.get("tool_calls") or []
    return (content if isinstance(content, str) else "", calls if isinstance(calls, list) else [])


def _unparsed_tool_markup(response: dict[str, Any]) -> bool:
    content, _ = _response_parts(response)
    return any(marker in content for marker in TEXT_TOOL_CALL_MARKERS)


def _bite_tools_error(engine: SuiteEngine, expected: tuple[str, ...]) -> str | None:
    offered = engine.last_trace.get("tools_offered")
    if not isinstance(offered, list) or not all(isinstance(name, str) for name in offered):
        return "Pipeline trace did not verify the bite tools offered to the model"
    missing = sorted(set(expected) - set(offered))
    return f"Pipeline offered no bite tool(s): {missing}" if missing else None


def _run_bite(
    engine: SuiteEngine,
    seat: str,
    discipline: str,
    case: dict[str, Any],
    task_dir: Path,
    dry_run: bool,
    persona: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    bite, input_paths = _bite_contract(case, discipline, task_dir, dry_run=dry_run)
    expected_tools = (*bite.tools, "finish")
    engine.audit_calls = []
    engine.bite_responses = []
    workers: list[Any] = []
    offered: set[str] = set()
    last_trace: dict[str, Any] = {}
    for index, (stage_bite, stage_inputs) in enumerate(
        _stage_bites(bite, input_paths, task_dir), start=1
    ):
        worker = _run_bite_stage(
            engine,
            task_dir,
            stage_bite,
            stage_inputs,
            task_dir / f"attempt-{index:02d}",
            persona=persona,
        )
        workers.append(worker)
        last_trace = engine.last_trace
        trace_tools = last_trace.get("tools_offered")
        if isinstance(trace_tools, list):
            offered.update(name for name in trace_tools if isinstance(name, str))
        if not dry_run and any(
            _unparsed_tool_markup(response) for response in engine.bite_responses
        ):
            return (
                "harness_error",
                "HARNESS_ERROR",
                {"error": "Pipeline reply contains unparsed tool-call markup"},
            )
        if not dry_run and worker.loop_outcome in {"pipeline_error", "input_error"}:
            return "blocked", "BLOCKED", {"error": worker.failure or worker.loop_outcome}
        if not dry_run:
            if error := _bite_tools_error(engine, (*stage_bite.tools, "finish")):
                return "harness_error", "HARNESS_ERROR", {"error": error}
        if not dry_run and not worker.finished:
            return "failed", "FAIL", {"error": worker.failure or worker.loop_outcome}
    engine.last_trace = {**last_trace, "tools_offered": sorted(offered)}
    worker = workers[-1]
    local_calls = [
        {
            "name": call["name"],
            "args": call["arguments"],
            "output": call["output"],
            "error": call["output"] if call["error"] else None,
        }
        for result in workers
        for call in result.tool_results
    ]
    audit_calls = [*engine.audit_calls, *local_calls]
    content, _ = _response_parts(engine.last_response)
    (task_dir / "response.txt").write_text(content, encoding="utf-8")
    identity_error = _live_identity(engine, seat)
    if dry_run:
        return (
            "running",
            "DRY_RUN",
            {
                "pipeline_trace": bool(engine.last_trace),
                "bite_tools": list(expected_tools),
            },
        )
    if error := _bite_tools_error(engine, expected_tools):
        return "harness_error", "HARNESS_ERROR", {"error": error}
    if identity_error:
        return "blocked", "BLOCKED", {"error": identity_error}
    passed, evidence = _score_bite(case, worker.output, audit_calls, task_dir)
    return ("passed", "PASS", evidence) if passed else ("failed", "FAIL", evidence)


def _stage_bites(
    bite: Bite, input_paths: dict[str, Path], task_dir: Path
) -> list[tuple[Bite, dict[str, Path]]]:
    reads = tuple(tool for tool in bite.tools if tool in READ_TOOLS)
    actions = tuple(tool for tool in bite.tools if tool in ACTION_TOOLS)
    if not reads or not actions:
        return [(bite, input_paths)]
    inspect_path = f"bites/{_safe_name(bite.bite_id)}/inspection.txt"
    inspection = replace(
        bite,
        bite_id=f"{bite.bite_id}-inspect",
        goal=f"Inspect the source and tests for this task and report the defect. Task: {bite.goal}",
        tools=reads,
        output_path=inspect_path,
        output_schema=None,
        file_type="text",
        procedure="Read the supplied files and report the defect and expected behavior. Do not edit or run tests.",
        reads_untrusted=True,
    )
    action = replace(
        bite,
        bite_id=f"{bite.bite_id}-act",
        tools=actions,
        inputs=(*bite.inputs, "inspection"),
        procedure=(
            "Use the read-only inspection report supplied as input. Do not call file_read. "
            "Make the smallest implementation change with file_write and verify it with pytest_run. "
            f"Original task: {bite.procedure}"
        ),
        reads_untrusted=False,
    )
    return [
        (inspection, input_paths),
        (action, {**input_paths, "inspection": Path(inspect_path)}),
    ]


def _run_bite_stage(
    engine: SuiteEngine,
    task_dir: Path,
    bite: Bite,
    input_paths: dict[str, Path],
    attempt_dir: Path,
    *,
    persona: str | None = None,
) -> Any:
    engine.expected_bite_tools = (*bite.tools, "finish")
    try:
        # Same tool persona production sends (service.py), or the seat's own pool is used.
        return run_bite(
            task_dir,
            bite,
            engine,
            input_paths=input_paths,
            attempt_dir=attempt_dir,
            persona=persona,
        )
    finally:
        engine.expected_bite_tools = None


def _run_one(
    *,
    engine: SuiteEngine,
    seat: str,
    discipline: str,
    suite: str,
    case: dict[str, Any],
    label: str,
    messages: list[dict[str, str]],
    tools: list[str],
    task_dir: Path,
    dry_run: bool,
    persona: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    row = {
        "bite_id": f"{suite}-{_safe_name(case['id'])}-{_safe_name(label)}",
        "case_id": case["id"],
        "suite": suite,
        "repeat": label,
        "discipline": discipline,
        "model": seat,
    }
    try:
        if suite == "bite":
            state, status, evidence = _run_bite(
                engine, seat, discipline, case, task_dir, dry_run, persona
            )
        else:
            response = engine.chat(
                _request_body(seat, messages, tools, json_output=True),
                DEFAULT_TIMEOUT,
                lambda _event: None,
            )
            content = _response_text(response)
            (task_dir / "response.txt").write_text(content, encoding="utf-8")
            identity_error = _live_identity(engine, seat)
            if dry_run:
                state, status = "running", "DRY_RUN"
                evidence = {"pipeline_trace": bool(engine.last_trace)}
            elif identity_error:
                state, status, evidence = "blocked", "BLOCKED", {"error": identity_error}
            else:
                state, status, evidence = _score_json_verdict(content, label)
        row.update(state=state, status=status, evidence=evidence)
    except HarnessError as exc:
        row.update(state="harness_error", status="HARNESS_ERROR", evidence={"error": str(exc)})
    except Exception as exc:
        row.update(
            state="blocked", status="BLOCKED", evidence={"error": f"{type(exc).__name__}: {exc}"}
        )
    row["elapsed_seconds"] = round(time.monotonic() - started, 6)
    row["served"] = engine.last_trace
    return row


def _case_requests(
    suite_name: str,
    cases: list[dict[str, Any]],
    config: dict[str, Any],
    discipline: str,
    run_dir: Path,
) -> list[tuple[str, dict[str, Any], str, list[dict[str, str]], list[str], Path]]:
    requests = []
    if suite_name == "bite":
        for case in cases:
            case_dir = run_dir / "cases" / _safe_name(case["id"])
            case_dir.mkdir(parents=True, exist_ok=True)
            requests.append(("bite", case, "case", [], [], case_dir))
    elif suite_name == "planner":
        for case in cases:
            case_dir = run_dir / "cases" / _safe_name(case["id"])
            case_dir.mkdir(parents=True, exist_ok=True)
            requests.append(
                ("planner", case, str(case.get("expected", "reject")), [], [], case_dir)
            )
    else:
        for case, label, fixture in _checker_cases_for_discipline(config, discipline, cases):
            case_dir = run_dir / "cases" / _safe_name(f"{case['id']}-{label}")
            case_dir.mkdir(parents=True, exist_ok=True)
            messages = _checker_messages(case, label, fixture)
            requests.append(("checker", case, label, messages, [], case_dir))
    return requests


def _checker_cases_for_discipline(
    config: dict[str, Any], discipline: str, cases: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    if discipline == "detection-engineering":
        entry = config["disciplines"][discipline]
        path = (ROOT / entry["checker_suite"]).resolve()
        return _checker_cases(path)
    return [
        (
            case,
            str(case.get("expected", "reject")),
            {
                "output": case.get("output"),
                "checks": case.get("checks", []),
                "schema": case.get("schema"),
            },
        )
        for case in cases
    ]


def _run_requests(
    requests: list[tuple[str, dict[str, Any], str, list[dict[str, str]], list[str], Path]],
    *,
    config: dict[str, Any],
    discipline: str,
    seat: str,
    repeats: int,
    pipeline_url: str,
    api_key: str,
    dry_run: bool,
) -> list[dict[str, Any]]:
    engine = SuiteEngine(seat, pipeline_url, api_key)
    rows = []
    for suite, case, label, messages, tools, case_dir in requests:
        for repeat in range(1, repeats + 1):
            task_dir = case_dir / f"repeat-{repeat:02d}"
            task_dir.mkdir(parents=True, exist_ok=True)
            if suite == "planner":
                messages = _planner_messages(case, config, discipline, task_dir)
            row = _run_one(
                engine=engine,
                seat=seat,
                discipline=discipline,
                suite=suite,
                case=case,
                label=label,
                messages=messages,
                tools=tools,
                task_dir=task_dir,
                dry_run=dry_run,
                persona=config["disciplines"][discipline].get("persona"),
            )
            row["bite_id"] = f"{row['bite_id']}-r{repeat:02d}"
            row["repeat"] = repeat
            rows.append(row)
            elapsed = row.get("elapsed_seconds")
            timing = f" ({elapsed:.1f}s)" if isinstance(elapsed, int | float) else ""
            print(f"  {suite}/{case['id']} repeat {repeat}: {row['status']}{timing}", flush=True)
    return rows


def _head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _write_run(
    run_dir: Path,
    *,
    discipline: str,
    seat: str,
    suites: list[str],
    rows: list[dict[str, Any]],
    dry_run: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = run_dir.name
    plan = {
        "task_id": run_id,
        "goal": f"Live {discipline} orchestration suite trial for {seat}",
        "bites": [
            {
                "bite_id": row["bite_id"],
                "discipline": discipline,
                "model": seat,
                "suite": row["suite"],
            }
            for row in rows
        ],
    }
    receipt = {
        "head": _head(),
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workdir": str(run_dir.resolve()),
        "task_id": run_id,
        "status": "DRY_RUN" if dry_run else "PASS",
        "mode": "dry-run" if dry_run else "live",
        "gate_evidence": not dry_run,
        "discipline": discipline,
        "seat": seat,
        "suites": suites,
        "results": rows,
        **(extra or {}),
    }
    statuses = [row.get("status") for row in rows]
    if not dry_run:
        if any(value == "HARNESS_ERROR" for value in statuses):
            receipt["status"] = "HARNESS_ERROR"
        elif any(value == "BLOCKED" for value in statuses):
            receipt["status"] = "BLOCKED"
        elif any(value == "FAIL" for value in statuses):
            receipt["status"] = "FAIL"
        elif not rows:
            receipt["status"] = "BLOCKED"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def run_trial(
    *,
    config_path: Path,
    discipline: str,
    seat: str,
    suite: str,
    repeats: int,
    output_dir: Path,
    pipeline_url: str = DEFAULT_PIPELINE,
    api_key: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("--repeats must be at least 1")
    config = load_config(config_path)
    suite_paths = _selected_suites(config, discipline, suite)
    run_id = f"bite-suite-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_dir = output_dir / _safe_name(discipline) / _safe_name(seat) / run_id
    requests = []
    for suite_name, path in suite_paths.items():
        requests.extend(_case_requests(suite_name, load_suite(path), config, discipline, run_dir))
    rows = _run_requests(
        requests,
        config=config,
        discipline=discipline,
        seat=seat,
        repeats=repeats,
        pipeline_url=pipeline_url,
        api_key=api_key,
        dry_run=dry_run,
    )
    extra = {
        "summary": {
            status: sum(row["status"] == status for row in rows)
            for status in ("PASS", "FAIL", "BLOCKED", "HARNESS_ERROR", "DRY_RUN")
        }
    }
    return _write_run(
        run_dir,
        discipline=discipline,
        seat=seat,
        suites=list(suite_paths),
        rows=rows,
        dry_run=dry_run,
        extra=extra,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discipline", required=True, help="key in config/orchestration_arm.yaml")
    parser.add_argument("--seat", required=True, help="Pipeline workspace or persona id")
    parser.add_argument("--suite", choices=("bite", "planner", "checker", "all"), default="all")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--pipeline-url", default=DEFAULT_PIPELINE)
    parser.add_argument("--config", type=Path, default=ROOT / "config/orchestration_arm.yaml")
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument(
        "--dry-run", action="store_true", help="send requests to the fake Pipeline rig"
    )
    return parser


def _timing(results: list[dict[str, Any]]) -> dict[str, float | int]:
    """Total and median per-bite wall time, so a seat comparison never lacks speed."""
    elapsed = sorted(
        float(row["elapsed_seconds"])
        for row in results
        if isinstance(row.get("elapsed_seconds"), int | float)
    )
    if not elapsed:
        return {"timed": 0}
    middle = len(elapsed) // 2
    median = elapsed[middle] if len(elapsed) % 2 else (elapsed[middle - 1] + elapsed[middle]) / 2
    return {"timed": len(elapsed), "total_s": round(sum(elapsed), 1), "median_s": round(median, 1)}


def main() -> int:
    args = _parser().parse_args()
    if args.repeats < 1:
        print("ERROR: --repeats must be at least 1", file=sys.stderr)
        return 2
    output_dir = args.workdir or (get_generated_dir("tasks") / "orchestration-bite-suite")
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    pipeline_url = args.pipeline_url
    fake = None
    if args.dry_run:
        sys.path.insert(0, str(ROOT / "tests" / "unit"))
        from orchestration_fake_pipeline import FakePipeline

        fake = FakePipeline()
        pipeline_url = fake.url
    try:
        if args.dry_run:
            receipt = run_trial(
                config_path=args.config,
                discipline=args.discipline,
                seat=args.seat,
                suite=args.suite,
                repeats=args.repeats,
                output_dir=output_dir,
                pipeline_url=pipeline_url,
                api_key=api_key,
                dry_run=True,
            )
        else:
            receipt = run_live(args, output_dir, pipeline_url, api_key)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if fake is not None:
            fake.close()
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "workdir": receipt["workdir"],
                "summary": receipt.get("summary", {}),
                "timing": _timing(receipt.get("results", [])),
            },
            indent=2,
        )
    )
    return (
        0
        if receipt["status"] in {"PASS", "DRY_RUN"}
        else 3
        if receipt["status"] == "BLOCKED"
        else 1
    )


def run_live(
    args: argparse.Namespace, output_dir: Path, pipeline_url: str, api_key: str
) -> dict[str, Any]:
    context = host_quiet.begin_run(pipeline_url, api_key)
    if not context.get("allowed"):
        reason = host_quiet.refusal(context)
        host_quiet.finish_run(context, pipeline_url, api_key)
        receipt = _write_run(
            output_dir
            / _safe_name(args.discipline)
            / _safe_name(args.seat)
            / f"bite-suite-blocked-{uuid4().hex[:8]}",
            discipline=args.discipline,
            seat=args.seat,
            suites=[args.suite],
            rows=[],
            dry_run=False,
            extra={"blocked": reason, "host_quiet": context},
        )
        return receipt
    try:
        receipt = run_trial(
            config_path=args.config,
            discipline=args.discipline,
            seat=args.seat,
            suite=args.suite,
            repeats=args.repeats,
            output_dir=output_dir,
            pipeline_url=pipeline_url,
            api_key=api_key,
        )
    finally:
        host_quiet.finish_run(context, pipeline_url, api_key)
    receipt["host_quiet"] = context
    receipt_path = Path(receipt["workdir"]) / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    raise SystemExit(main())
