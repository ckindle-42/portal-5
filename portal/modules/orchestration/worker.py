"""One-bite Pipeline client and deterministic output checks."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator, ValidationError  # type: ignore[import-untyped]

from .contracts import Bite
from .tools import (
    ACTION_TOOLS,
    READ_TOOLS,
    TASK_DATA_DIRECTORY,
    TaskToolExecutor,
    tool_schema,
)

DEFAULT_CONTEXT_TOKENS = 16_384
CONTEXT_RESERVE_TOKENS = 512
SNAPSHOT_CHARS_PER_TOKEN = 3
SNAPSHOT_TRUNCATION_MARKER = "[TRUNCATED: input snapshot clipped to fit the bite context budget]"


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


class QueueYieldError(RuntimeError):
    """A queued bite must wait for the Pipeline's current admission state."""


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
    tool_results: tuple[dict[str, Any], ...] = ()


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
    require_idle: bool = False,
) -> WorkerResult:
    """Run a fresh bite and execute its client tools within the task directory."""
    started = time.monotonic()
    transcript = _Transcript(attempt_dir / "transcript.jsonl")
    data_dir = task_dir / TASK_DATA_DIRECTORY
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = _inside_task(data_dir, bite.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    try:
        messages = _messages(bite, input_paths, data_dir)
    except (OSError, UnicodeError, ValueError) as exc:
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
    executor = TaskToolExecutor(
        data_dir,
        bite.tools,
        readable_paths=tuple(path.as_posix() for path in input_paths.values()),
        writable_paths=_writable_paths(bite, input_paths),
    )
    try:
        plan = engine.load_plan(bite.budget.minutes * 60)
    except PipelineError as exc:
        if require_idle:
            raise QueueYieldError(str(exc)) from exc
        elapsed = time.monotonic() - started
        flags = ("wall_clock_cap",) if elapsed > bite.budget.minutes * 60 else ()
        return WorkerResult(False, None, 0, elapsed, "pipeline_error", flags, (), str(exc))
    transcript.append("load_plan", {"model": engine.model_tag, "plan": plan})
    if require_idle and (plan.get("busy") is not False or plan.get("fits") is not True):
        raise QueueYieldError(f"Pipeline load-plan is busy or cannot admit the seat: {plan}")
    calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    tokens = 0
    turn = 0
    while turn < bite.budget.turns:
        remaining_tokens = bite.budget.output_tokens - tokens
        if remaining_tokens < 1:
            return WorkerResult(
                False,
                None,
                tokens,
                time.monotonic() - started,
                "output_token_cap",
                ("output_token_cap",),
                tuple(calls),
                "output token budget exhausted",
                tuple(tool_results),
            )
        if time.monotonic() - started >= bite.budget.minutes * 60:
            return WorkerResult(
                False,
                None,
                tokens,
                time.monotonic() - started,
                "wall_clock_cap",
                ("wall_clock_cap",),
                tuple(calls),
                "wall-clock budget exhausted",
                tuple(tool_results),
            )
        request = {
            **body,
            "messages": messages,
            "max_tokens": remaining_tokens,
            "portal_bite_max_hops": bite.budget.turns - turn,
        }
        transcript.append("request", {"body": request, "model": engine.model_tag})
        try:
            response = engine.chat(
                request,
                _remaining_time(bite, started),
                lambda event: transcript.append("event", event),
            )
        except PipelineError as exc:
            elapsed = time.monotonic() - started
            flags = ("wall_clock_cap",) if elapsed > bite.budget.minutes * 60 else ()
            return WorkerResult(
                False, None, tokens, elapsed, "pipeline_error", flags, tuple(calls), str(exc)
            )
        turn_tokens = _response_tokens(response)
        tokens += turn_tokens
        prior_call_count = len(calls)
        result = _handle_response(
            task_dir,
            bite,
            engine,
            response,
            messages,
            request,
            transcript,
            executor,
            started,
            turn,
            tokens,
            turn_tokens,
            calls,
            tool_results,
        )
        if result is not None:
            return result
        turn += len(calls) - prior_call_count
    return WorkerResult(
        False,
        None,
        tokens,
        time.monotonic() - started,
        "wandering",
        ("missing_finish",),
        tuple(calls),
        "tool hop limit exhausted without finish",
        tuple(tool_results),
    )


def _handle_response(
    task_dir: Path,
    bite: Bite,
    engine: Engine,
    response: dict[str, Any],
    messages: list[dict[str, Any]],
    request: dict[str, Any],
    transcript: _Transcript,
    executor: TaskToolExecutor,
    started: float,
    turn: int,
    tokens: int,
    turn_tokens: int,
    calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> WorkerResult | None:
    content, turn_calls = _response_parts(response)
    transcript.append("response", {"response": response})
    prior_calls = list(calls)
    calls.extend(turn_calls)
    elapsed = time.monotonic() - started
    if tokens > bite.budget.output_tokens:
        return WorkerResult(
            False,
            None,
            tokens,
            elapsed,
            "output_token_cap",
            ("output_token_cap",),
            tuple(calls),
            "output token budget exhausted",
            tuple(tool_results),
        )
    if elapsed > bite.budget.minutes * 60:
        return WorkerResult(
            False,
            None,
            tokens,
            elapsed,
            "wall_clock_cap",
            ("wall_clock_cap",),
            tuple(calls),
            "wall-clock budget exhausted",
            tuple(tool_results),
        )
    names = [str((call.get("function") or {}).get("name") or "") for call in turn_calls]
    if not turn_calls or "finish" in names or any(name not in bite.tools for name in names):
        return _finished_response(
            task_dir,
            bite,
            engine,
            response,
            messages,
            request,
            transcript,
            started,
            prior_calls,
            tokens - turn_tokens,
            turn,
            calls,
            tool_results,
        )
    hop_limit_reached = turn + len(turn_calls) >= bite.budget.turns
    if hop_limit_reached or tokens >= bite.budget.output_tokens:
        flag = "hop_limit_exhausted" if hop_limit_reached else "output_token_cap"
        return WorkerResult(
            False,
            None,
            tokens,
            elapsed,
            flag,
            (flag,),
            tuple(calls),
            "no budget remains to continue the client tool loop",
            tuple(tool_results),
        )
    _append_tool_exchanges(turn_calls, content, messages, transcript, executor, tool_results, turn)
    return None


def _finished_response(
    task_dir: Path,
    bite: Bite,
    engine: Engine,
    response: dict[str, Any],
    messages: list[dict[str, Any]],
    request: dict[str, Any],
    transcript: _Transcript,
    started: float,
    prior_calls: list[dict[str, Any]],
    tokens_before: int,
    turn: int,
    calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> WorkerResult:
    result = _finish_response(
        task_dir,
        bite,
        engine,
        response,
        messages,
        request,
        transcript,
        started,
        prior_calls=prior_calls,
        tokens_before=tokens_before,
        turns_remaining=bite.budget.turns - turn - 1,
    )
    return replace(result, tool_calls=tuple(calls), tool_results=tuple(tool_results))


def _append_tool_exchanges(
    calls: list[dict[str, Any]],
    content: str,
    messages: list[dict[str, Any]],
    transcript: _Transcript,
    executor: TaskToolExecutor,
    tool_results: list[dict[str, Any]],
    turn: int,
) -> None:
    messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})
    for offset, call in enumerate(calls):
        name = str((call.get("function") or {}).get("name") or "")
        try:
            arguments = _call_arguments(call)
            result = executor.dispatch(name, arguments)
        except (json.JSONDecodeError, ValueError) as exc:
            arguments = {}
            result = f"ERROR: invalid tool arguments: {exc}"
        call_id = str(call.get("id") or f"bite-tool-{turn + offset + 1}")
        messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": result})
        record = {
            "name": name,
            "arguments": arguments,
            "output": result,
            "error": result.startswith("ERROR:"),
        }
        transcript.append("tool_result", record)
        tool_results.append(record)


def _finish_response(
    task_dir: Path,
    bite: Bite,
    engine: Engine,
    response: dict[str, Any],
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    transcript: _Transcript,
    started: float,
    *,
    prior_calls: list[dict[str, Any]],
    tokens_before: int,
    turns_remaining: int,
) -> WorkerResult:
    tokens = tokens_before + _response_tokens(response)
    finish = _finish_arguments(
        bite,
        engine,
        response,
        messages,
        body,
        tokens,
        transcript,
        started,
        turns_remaining=turns_remaining,
    )
    red_flags = set(finish.red_flags)
    output = finish.arguments.get("output") if finish.arguments is not None else None
    finished, payload_flags = _validate_finish_args(finish.arguments)
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
            _write_output(
                _inside_task(task_dir / TASK_DATA_DIRECTORY, bite.output_path), bite, output
            )
    result_record = {
        "finished": finished,
        "red_flags": sorted(red_flags),
        "tokens": finish.tokens,
        "elapsed_seconds": elapsed,
        "worker_output_path": bite.output_path,
    }
    if finish.arguments is not None and "output_path" in finish.arguments:
        result_record["ignored_model_output_path"] = finish.arguments["output_path"]
    transcript.append("result", result_record)
    return WorkerResult(
        finished,
        output,
        finish.tokens,
        elapsed,
        "finished" if finished else "wandering",
        tuple(sorted(red_flags)),
        (*prior_calls, *finish.calls),
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
    *,
    turns_remaining: int,
) -> FinishResult:
    content, calls = _response_parts(response)
    call, flags = _select_finish_call(calls)
    if call is None:
        repair_result = _finish_repair_result(
            bite,
            engine,
            messages,
            body,
            content,
            calls,
            tokens,
            transcript,
            started,
            turns_remaining=turns_remaining,
        )
        if repair_result is not None:
            return repair_result
        return FinishResult(content, tuple(calls), None, tokens, frozenset(flags), None)
    try:
        arguments = _call_arguments(call)
    except (json.JSONDecodeError, ValueError) as exc:
        repaired, tokens, failure = _repair_json(
            bite,
            engine,
            messages,
            body,
            call,
            str(exc),
            tokens,
            transcript,
            started,
            turns_remaining=turns_remaining,
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


def _validate_finish_args(arguments: dict[str, Any] | None) -> tuple[bool, set[str]]:
    if arguments is None or "output" not in arguments:
        return False, {"missing_finish_output"}
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
    *,
    turns_remaining: int,
) -> tuple[dict[str, Any], int, str | None]:
    if turns_remaining < 1:
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
        "portal_bite_max_hops": turns_remaining,
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


def _finish_repair_result(
    bite: Bite,
    engine: Engine,
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    content: str,
    calls: list[dict[str, Any]],
    tokens: int,
    transcript: _Transcript,
    started: float,
    *,
    turns_remaining: int,
) -> FinishResult | None:
    if calls or not content:
        return None
    repaired, tokens, _failure = _repair_finish(
        bite,
        engine,
        messages,
        body,
        content,
        tokens,
        transcript,
        started,
        turns_remaining=turns_remaining,
    )
    repair_content, repair_calls = _response_parts(repaired)
    repaired_call, repaired_flags = _select_finish_call(repair_calls)
    arguments: dict[str, Any] | None = None
    if repaired_call is not None:
        try:
            arguments = _call_arguments(repaired_call)
        except (json.JSONDecodeError, ValueError):
            arguments = None
    if arguments is None:
        _unused_call, flags = _select_finish_call(calls)
        return FinishResult(
            f"{content}{repair_content}", tuple(calls), None, tokens, frozenset(flags), None
        )
    return FinishResult(
        f"{content}{repair_content}",
        tuple(repair_calls),
        arguments,
        tokens,
        frozenset(repaired_flags),
        None,
    )


def _repair_finish(
    bite: Bite,
    engine: Engine,
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    content: str,
    tokens: int,
    transcript: _Transcript,
    started: float,
    *,
    turns_remaining: int,
) -> tuple[dict[str, Any], int, str | None]:
    if turns_remaining < 1:
        return {}, tokens, "finish repair requires one additional turn"
    if tokens >= bite.budget.output_tokens:
        return {}, tokens, "finish repair output budget exhausted"
    required = ", ".join(_finish_schema(bite)["function"]["parameters"]["required"])
    repair_messages = [
        *messages,
        {"role": "assistant", "content": content},
        {
            "role": "user",
            "content": (
                "You replied with plain text and no tool call. Call finish once now, "
                f"passing your answer as its required field(s): {required}."
            ),
        },
    ]
    repair_body = {
        **body,
        "messages": repair_messages,
        "max_tokens": max(1, bite.budget.output_tokens - tokens),
        "portal_bite_max_hops": turns_remaining,
    }
    transcript.append("finish_repair", {"stage": "request", "body": repair_body})
    try:
        response = engine.chat(
            repair_body,
            _remaining_time(bite, started),
            lambda event: transcript.append("finish_repair", {"stage": "event", "event": event}),
        )
    except PipelineError as exc:
        return {}, tokens, f"finish repair failed: {exc}"
    tokens += _response_tokens(response)
    transcript.append("finish_repair", {"stage": "response", "response": response})
    return response, tokens, None


def _request_body(bite: Bite, engine: Engine, messages: list[dict[str, Any]]) -> dict[str, Any]:
    tool_names = set(bite.tools)
    if tool_names & READ_TOOLS and tool_names & ACTION_TOOLS:
        raise ValueError("reading and acting tools cannot share one bite")
    return {
        "model": engine.model_tag,
        "messages": messages,
        "tools": [*(tool_schema(name) for name in bite.tools), _finish_schema(bite)],
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
                "properties": {"output": output_schema},
                "required": ["output"],
                "additionalProperties": False,
            },
        },
    }


def _messages(
    bite: Bite, input_paths: dict[str, Path], task_dir: Path | None = None
) -> list[dict[str, Any]]:
    declared_paths: dict[str, str] = {}
    root = task_dir.resolve() if task_dir is not None else None
    for name, value in input_paths.items():
        path = Path(value)
        if root is None:
            declared_paths[name] = str(path)
        elif not path.is_absolute() and (root / path).resolve().is_relative_to(root):
            declared_paths[name] = (root / path).resolve().relative_to(root).as_posix()
        elif path.is_absolute() and path.resolve().is_relative_to(root):
            declared_paths[name] = path.resolve().relative_to(root).as_posix()
        else:
            relative = Path(name)
            fallback = (root / relative).resolve()
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not fallback.is_relative_to(root)
                or not fallback.is_file()
            ):
                raise ValueError(f"input {name!r} is not staged inside the task directory")
            declared_paths[name] = fallback.relative_to(root).as_posix()
    system = (
        "Execute exactly one task bite with the supplied Pipeline tools. "
        "Use only listed bite tools and call finish once when done. Keep reasoning enabled.\n"
        f"Goal: {bite.goal}\nProcedure: {bite.procedure}\n"
        f"Acceptance: {json.dumps(bite.accept)}\n"
        f"Deep review: {bite.review_reason or 'not requested'}\n"
        f"Declared input paths: {json.dumps(declared_paths)}"
    )
    if set(bite.tools) & ACTION_TOOLS:
        system += (
            "\nThe declared inputs and existing staged write targets are included in the user "
            "message as read-only snapshots. This action bite has no file_read tool; do not call one."
        )
    inputs = {name: {"path": path} for name, path in declared_paths.items()}
    user_content = json.dumps({"bite_id": bite.bite_id, "inputs": inputs})
    snapshot_paths = dict(declared_paths)
    if set(bite.tools) & ACTION_TOOLS and root is not None:
        for write_path in bite.write_paths:
            staged_path = input_paths.get(write_path, Path(write_path))
            if staged_path.is_absolute() or ".." in staged_path.parts:
                continue
            resolved = (root / staged_path).resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                snapshot_paths.setdefault(write_path, resolved.relative_to(root).as_posix())
    if set(bite.tools) & ACTION_TOOLS and snapshot_paths and root is not None:
        user_content += "\n\n" + _input_snapshot_text(
            bite, snapshot_paths, root, system, user_content
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


def _input_snapshot_text(
    bite: Bite,
    declared_paths: dict[str, str],
    root: Path,
    system: str,
    user_content: str,
) -> str:
    prefix = "Read-only snapshots of the declared staged input files follow.\n"
    marker = f"\n{SNAPSHOT_TRUNCATION_MARKER}\n"
    paths = [(name, relative, root / relative) for name, relative in declared_paths.items()]
    file_sizes = [path.stat().st_size for _, _, path in paths]
    snapshot_headers = [
        (f"--- BEGIN FILE {name} (staged copy: {relative}) ---\n", f"\n--- END FILE {name} ---\n")
        for name, relative, _ in paths
    ]
    schemas = [*(tool_schema(name) for name in bite.tools), _finish_schema(bite)]
    context_tokens = bite.budget.context_tokens or DEFAULT_CONTEXT_TOKENS
    output_reserve = min(bite.budget.output_tokens, context_tokens // 2)
    prompt_tokens = max(0, context_tokens - output_reserve - CONTEXT_RESERVE_TOKENS)
    prompt_bytes = prompt_tokens * SNAPSHOT_CHARS_PER_TOKEN
    fixed_bytes = (
        len(system.encode("utf-8"))
        + len(user_content.encode("utf-8"))
        + len(b"\n\n")
        + len(json.dumps(schemas).encode("utf-8"))
        + len(prefix.encode("utf-8"))
        + sum(
            len(header.encode("utf-8")) + len(footer.encode("utf-8")) + len(marker.encode("utf-8"))
            for header, footer in snapshot_headers
        )
    )
    if fixed_bytes > prompt_bytes:
        return prefix + SNAPSHOT_TRUNCATION_MARKER
    content_budget = prompt_bytes - fixed_bytes
    remaining_size = sum(file_sizes)
    parts = [prefix]
    for (_name, _relative, path), (header, footer), size in zip(
        paths, snapshot_headers, file_sizes, strict=True
    ):
        allocation = min(size, content_budget * size // remaining_size) if remaining_size else 0
        content_budget -= allocation
        remaining_size -= size
        with path.open("rb") as source:
            raw = source.read(allocation)
        content = raw.decode("utf-8", errors="ignore")
        parts.append(header)
        parts.append(content)
        if allocation < size:
            parts.append(marker)
        parts.append(footer)
    return "".join(parts)


def _writable_paths(bite: Bite, input_paths: dict[str, Path]) -> tuple[str, ...]:
    paths: list[str] = []
    for declared in bite.write_paths:
        resolved = input_paths.get(declared, Path(declared))
        if resolved.is_absolute() or ".." in resolved.parts:
            raise ValueError(f"write path escapes task data: {declared}")
        paths.append(resolved.as_posix())
    return tuple(paths)


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
