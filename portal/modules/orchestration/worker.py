"""One-bite Pipeline client and deterministic output checks."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from .contracts import Bite


@dataclass(frozen=True)
class Engine:
    """Pipeline endpoint and identity for one seated workspace variant."""

    model_tag: str
    model_digest: str
    base_url: str
    api_key: str = ""
    load_plan_engine: str = "omlx"
    load_plan_model: str = ""

    def identity(self) -> dict[str, str]:
        return {"model_tag": self.model_tag, "model_digest": self.model_digest}

    def chat(
        self,
        body: dict[str, Any],
        timeout: float,
        on_event: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        content: list[str] = []
        usage: dict[str, Any] = {}
        finish_reason = "stop"
        try:
            with httpx.stream(
                "POST",
                _chat_url(self.base_url),
                headers=self._headers(),
                json=body,
                timeout=httpx.Timeout(max(0.05, timeout), connect=min(5.0, max(0.05, timeout))),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        continue
                    event = _decode_event(payload)
                    on_event(event)
                    if "error" in event:
                        raise PipelineError(str(event["error"]))
                    _merge_event(event, content, calls, usage)
                    choices = event.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        finish_reason = str(choices[0].get("finish_reason") or finish_reason)
        except (httpx.HTTPError, ValueError) as exc:
            raise PipelineError(f"{type(exc).__name__}: {exc}") from exc
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "".join(content),
                        "tool_calls": calls,
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage,
        }

    def load_plan(self, timeout: float) -> dict[str, Any]:
        if not self.load_plan_model:
            return {"skipped": True}
        body = {"models": [{"engine": self.load_plan_engine, "model": self.load_plan_model}]}
        try:
            response = httpx.post(
                _admin_url(self.base_url),
                headers=self._headers(),
                json=body,
                timeout=min(10.0, max(0.05, timeout)),
            )
            response.raise_for_status()
            plan = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PipelineError(f"load-plan failed: {type(exc).__name__}: {exc}") from exc
        if isinstance(plan, dict) and plan.get("fits") is False:
            raise PipelineError(f"load guard refused the seat: {plan}")
        return plan if isinstance(plan, dict) else {"response": plan}

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


class PipelineError(RuntimeError):
    """The Pipeline or its load guard rejected the bite request."""


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    failures: tuple[str, ...]
    values: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class WorkerResult:
    finished: bool
    output: Any
    output_tokens: int
    elapsed_seconds: float
    loop_outcome: str
    red_flags: tuple[str, ...]
    tool_calls: tuple[dict[str, Any], ...]
    failure: str | None = None


@dataclass(frozen=True)
class FinishResult:
    content: str
    calls: tuple[dict[str, Any], ...]
    arguments: dict[str, Any] | None
    tokens: int
    red_flags: frozenset[str]
    failure: str | None


def run_bite(
    task_dir: Path,
    bite: Bite,
    engine: Engine,
    *,
    input_paths: dict[str, Path],
    attempt_dir: Path,
) -> WorkerResult:
    """Run a fresh bite through one Pipeline tool-loop request."""
    started = time.monotonic()
    transcript = _Transcript(attempt_dir / "transcript.jsonl")
    output_path = _inside_task(task_dir, bite.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    try:
        messages = _messages(bite, input_paths)
    except (OSError, UnicodeError) as exc:
        elapsed = time.monotonic() - started
        return WorkerResult(
            False,
            None,
            0,
            elapsed,
            "input_error",
            (),
            (),
            f"input could not be read: {type(exc).__name__}: {exc}",
        )
    body = _request_body(bite, engine, messages)
    transcript.append("request", {"body": body, "model": engine.model_tag})
    try:
        plan = engine.load_plan(bite.budget.minutes * 60)
        transcript.append("load_plan", {"model": engine.model_tag, "plan": plan})
        response = engine.chat(
            body, _remaining_time(bite, started), lambda event: transcript.append("event", event)
        )
    except PipelineError as exc:
        elapsed = time.monotonic() - started
        flags = ("wall_clock_cap",) if elapsed > bite.budget.minutes * 60 else ()
        return WorkerResult(False, None, 0, elapsed, "pipeline_error", flags, (), str(exc))
    return _finish_response(task_dir, bite, engine, response, messages, body, transcript, started)


def _finish_response(
    task_dir: Path,
    bite: Bite,
    engine: Engine,
    response: dict[str, Any],
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    transcript: _Transcript,
    started: float,
) -> WorkerResult:
    tokens = _response_tokens(response)
    transcript.append("response", {"response": response})
    finish = _finish_arguments(bite, engine, response, messages, body, tokens, transcript, started)
    red_flags = set(finish.red_flags)
    output = finish.arguments.get("output") if finish.arguments is not None else None
    finished, payload_flags = _validate_finish_args(bite, finish.arguments)
    red_flags.update(payload_flags)
    if _is_refusal(finish.content) or _is_refusal(output if isinstance(output, str) else ""):
        red_flags.add("refusal")
    if finish.tokens > bite.budget.output_tokens:
        red_flags.add("output_token_cap")
    elapsed = time.monotonic() - started
    if elapsed > bite.budget.minutes * 60:
        red_flags.add("wall_clock_cap")
    if finished:
        _validate_output(bite, output, red_flags, transcript)
        if not red_flags:
            _write_output(_inside_task(task_dir, bite.output_path), bite, output)
    transcript.append(
        "result",
        {
            "finished": finished,
            "red_flags": sorted(red_flags),
            "tokens": finish.tokens,
            "elapsed_seconds": elapsed,
        },
    )
    return WorkerResult(
        finished,
        output,
        finish.tokens,
        elapsed,
        "finished" if finished else "wandering",
        tuple(sorted(red_flags)),
        finish.calls,
        finish.failure,
    )


def _finish_arguments(
    bite: Bite,
    engine: Engine,
    response: dict[str, Any],
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    tokens: int,
    transcript: _Transcript,
    started: float,
) -> FinishResult:
    content, calls = _response_parts(response)
    call, flags = _select_finish_call(calls)
    if call is None:
        return FinishResult(content, tuple(calls), None, tokens, frozenset(flags), None)
    try:
        arguments = _call_arguments(call)
    except (json.JSONDecodeError, ValueError) as exc:
        repaired, tokens, failure = _repair_json(
            bite, engine, messages, body, call, str(exc), tokens, transcript, started
        )
        repair_content, calls = _response_parts(repaired)
        content = f"{content}{repair_content}"
        if failure:
            flags.add("invalid_tool_call_json")
            return FinishResult(content, tuple(calls), None, tokens, frozenset(flags), failure)
        call, repair_flags = _select_finish_call(calls)
        flags.update(repair_flags)
        if call is None:
            flags.add("invalid_tool_call_json")
            return FinishResult(
                content, tuple(calls), None, tokens, frozenset(flags), "repair lacked finish"
            )
        try:
            arguments = _call_arguments(call)
        except (json.JSONDecodeError, ValueError) as repair_error:
            flags.add("invalid_tool_call_json")
            return FinishResult(
                content,
                tuple(calls),
                None,
                tokens,
                frozenset(flags),
                f"JSON repair failed: {repair_error}",
            )
    return FinishResult(content, tuple(calls), arguments, tokens, frozenset(flags), None)


def _select_finish_call(calls: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, set[str]]:
    if len(calls) != 1:
        return None, {"missing_finish" if not calls else "multiple_tool_calls"}
    call = calls[0]
    if call["function"].get("name") != "finish":
        return None, {"tool_outside_allowlist"}
    return call, set()


def _validate_finish_args(bite: Bite, arguments: dict[str, Any] | None) -> tuple[bool, set[str]]:
    if arguments is None or "output" not in arguments:
        return False, {"missing_finish_output"}
    if arguments.get("output_path", bite.output_path) != bite.output_path:
        return False, {"invalid_finish_path"}
    return True, set()


def _repair_json(
    bite: Bite,
    engine: Engine,
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    call: dict[str, Any],
    error: str,
    tokens: int,
    transcript: _Transcript,
    started: float,
) -> tuple[dict[str, Any], int, str | None]:
    if bite.budget.turns < 2:
        return {}, tokens, "JSON repair requires one additional turn"
    if tokens >= bite.budget.output_tokens:
        return {}, tokens, "JSON repair output budget exhausted"
    tool_call_id = str(call.get("id", "finish-repair"))
    repair_messages = [
        *messages,
        {"role": "assistant", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps({"error": error})},
        {"role": "user", "content": "Repair the malformed finish arguments and call finish once."},
    ]
    repair_body = {
        **body,
        "messages": repair_messages,
        "max_tokens": max(1, bite.budget.output_tokens - tokens),
        "portal_bite_max_hops": max(1, bite.budget.turns - 1),
    }
    transcript.append("repair_request", {"reason": error, "body": repair_body})
    try:
        response = engine.chat(
            repair_body,
            _remaining_time(bite, started),
            lambda event: transcript.append("repair_event", event),
        )
    except PipelineError as exc:
        return {}, tokens, f"JSON repair failed: {exc}"
    tokens += _response_tokens(response)
    transcript.append("repair_response", {"response": response})
    return response, tokens, None


def _request_body(bite: Bite, engine: Engine, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": engine.model_tag,
        "messages": messages,
        "tools": [_finish_schema(bite)],
        "tool_choice": "auto",
        "portal_bite_tools": [*bite.tools, "finish"],
        "portal_bite_max_hops": bite.budget.turns,
        "max_tokens": bite.budget.output_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": True},
    }


def _finish_schema(bite: Bite) -> dict[str, Any]:
    output_schema = bite.output_schema or {
        "type": "string" if bite.file_type == "text" else "object"
    }
    return {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish this bite with its checked output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output": output_schema,
                    "output_path": {"type": "string", "const": bite.output_path},
                },
                "required": ["output", "output_path"],
                "additionalProperties": False,
            },
        },
    }


def _messages(bite: Bite, input_paths: dict[str, Path]) -> list[dict[str, Any]]:
    system = (
        "Execute exactly one task bite with the supplied Pipeline tools. "
        "Use only listed bite tools and call finish once when done. Keep reasoning enabled.\n"
        f"Goal: {bite.goal}\nProcedure: {bite.procedure}\n"
        f"Acceptance: {json.dumps(bite.accept)}\n"
        f"Declared input paths: {json.dumps({key: str(value) for key, value in input_paths.items()})}"
    )
    inputs = {name: {"path": str(path)} for name, path in input_paths.items()}
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps({"bite_id": bite.bite_id, "inputs": inputs}),
        },
    ]


def _response_parts(response: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = message.get("content") or ""
    calls = message.get("tool_calls") or []
    return str(content), calls if isinstance(calls, list) else []


def _call_arguments(call: dict[str, Any]) -> dict[str, Any]:
    function = call.get("function") or {}
    args = function.get("arguments", {})
    if isinstance(args, str):
        args = json.loads(args)
    if not isinstance(args, dict):
        raise ValueError("tool arguments must be an object")
    return args


def _validate_output(bite: Bite, output: Any, red_flags: set[str], transcript: _Transcript) -> None:
    if bite.output_schema is not None:
        try:
            Draft202012Validator(bite.output_schema).validate(output)
        except ValidationError as exc:
            red_flags.add("invalid_output_schema")
            transcript.append("schema_error", {"error": exc.message})
    if bite.file_type == "text" and not isinstance(output, str):
        red_flags.add("invalid_file_type")
    if bite.file_type == "json" and not isinstance(output, (dict, list)):
        red_flags.add("invalid_file_type")


def _write_output(path: Path, bite: Bite, output: Any) -> None:
    text = str(output) if bite.file_type == "text" else json.dumps(output, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _merge_event(
    event: dict[str, Any],
    content: list[str],
    calls: list[dict[str, Any]],
    usage: dict[str, Any],
) -> None:
    if isinstance(event.get("usage"), dict):
        for key, value in event["usage"].items():
            if key == "completion_tokens" and isinstance(value, int):
                usage[key] = int(usage.get(key, 0)) + value
            else:
                usage[key] = value
    choices = event.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return
    delta = choices[0].get("delta") or {}
    if isinstance(delta.get("content"), str):
        content.append(delta["content"])
    _merge_tool_deltas(delta.get("tool_calls") or [], calls)


def _merge_tool_deltas(deltas: list[dict[str, Any]], calls: list[dict[str, Any]]) -> None:
    for delta in deltas:
        index = delta.get("index", 0)
        if not isinstance(index, int) or index < 0:
            continue
        while len(calls) <= index:
            calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        call = calls[index]
        function = delta.get("function") or {}
        if "id" in delta:
            call["id"] = delta["id"]
        if "type" in delta:
            call["type"] = delta["type"]
        if "name" in function:
            call["function"]["name"] += function["name"]
        if "arguments" in function:
            call["function"]["arguments"] += function["arguments"]


def _decode_event(payload: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"malformed Pipeline SSE JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError("Pipeline SSE event must be an object")
    return value


def _response_tokens(response: dict[str, Any]) -> int:
    usage = response.get("usage") or {}
    count = usage.get("completion_tokens")
    if isinstance(count, int) and count >= 0:
        return count
    content, calls = _response_parts(response)
    return math.ceil((len(content) + sum(len(json.dumps(call)) for call in calls)) / 4)


def _remaining_time(bite: Bite, started: float) -> float:
    return max(0.05, bite.budget.minutes * 60 - (time.monotonic() - started))


def _chat_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    return root + "/chat/completions" if root.endswith("/v1") else root + "/v1/chat/completions"


def _admin_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root + "/admin/load-plan"


class _Transcript:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, payload: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind, "time": time.time(), **payload}, default=str))
            stream.write("\n")
            stream.flush()


def _inside_task(task_dir: Path, relative: str) -> Path:
    target = (task_dir / relative).resolve()
    if not target.is_relative_to(task_dir.resolve()):
        raise ValueError("bite output path escapes the task directory")
    return target


def _is_refusal(value: str) -> bool:
    return bool(
        re.match(
            r"^\s*(I (?:cannot|can't|won't) (?:help|assist|comply)|I'm sorry.{0,40}(?:cannot|can't))",
            value,
            re.I,
        )
    )


def check_output(bite: Bite, output: Any, task_dir: Path) -> CheckResult:
    """Run the bite's declared deterministic acceptance checks."""
    failures: list[str] = []
    values: list[dict[str, Any]] = []
    for index, check in enumerate(bite.accept):
        passed, detail = _check_one(check, output, task_dir)
        values.append({"index": index, "check": check, "passed": passed, "detail": detail})
        if not passed:
            failures.append(f"check {index}: {detail}")
    return CheckResult(not failures, tuple(failures), tuple(values))


def _check_one(check: dict[str, Any], output: Any, task_dir: Path) -> tuple[bool, str]:
    kind = check.get("type")
    if kind == "equals":
        actual = _at_path(output, str(check.get("path", "$")))
        return actual == check.get("value"), f"expected {check.get('value')!r}, got {actual!r}"
    if kind == "contains":
        actual = _at_path(output, str(check.get("path", "$")))
        needle = check.get("value")
        passed = needle in actual if isinstance(actual, (str, list)) else False
        return passed, f"{needle!r} {'found' if passed else 'not found'}"
    if kind == "path_exists":
        raw_path = check.get("path")
        if not isinstance(raw_path, str):
            return False, "path_exists requires a string path"
        path = _inside_task(task_dir, raw_path)
        return path.is_file(), f"{raw_path} {'exists' if path.is_file() else 'does not exist'}"
    return False, f"unknown deterministic check {kind!r}"


def _at_path(value: Any, path: str) -> Any:
    if path in {"", "$"}:
        return value
    current = value
    for part in path.removeprefix("$").lstrip(".").split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current
