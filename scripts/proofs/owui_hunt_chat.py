#!/usr/bin/env python3
"""Live proof: Open WebUI reports hunt progress, then delivers terminal results later.

Product path: OWUI :8080 -> Pipeline :9099 -> security-reviewer workspace model ->
hunt_* tool calls on the review MCP (:8943). Sends a progress turn, waits for the
durable job through native MCP, then sends a second turn to retrieve terminal results.
It prints both turns and PASS/FAIL.

Tool-call evidence: the pipeline's trailing ``exec_audit`` SSE event when the request
reaches it; otherwise the pipeline's ``/v1/trace`` record for the turn (args need
PORTAL_TRACE_BODIES=1). Credentials: OWUI_API_KEY (and PIPELINE_API_KEY for the trace
fallback) from the environment or the repo .env, the same source the UAT and WFE
harnesses read; never printed.

    python3 scripts/proofs/owui_hunt_chat.py [--index hb_kyoushi_s1] [--job-id hunt-r2-<12hex>]
        [--require-sources]

Turn 2 passes on what its prompt asks for: the leads and first case for the job, with an
answer citing a returned lead id and the case id. ``hunt_sources`` is required only with
``--require-sources``. The receipt records each turn's prompt tokens and the run's peak.

Exit codes: 0 PASS, 1 FAIL, 2 setup error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

REPO = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = "hb_kyoushi_s1"
DEFAULT_MODEL = "security-reviewer"
JOB_RE = re.compile(r"(?<![\w-])hunt-r2-[0-9a-f]{12}(?![\w-])")
RESULT_CHARS = 300
TERMINAL_STATUSES = {"COMPLETE", "PARTIAL", "FAILED"}
RESULT_TOOLS = ("hunt_status", "hunt_sources", "hunt_leads", "hunt_case")
# What the results prompt asks for; hunt_sources is opt-in via --require-sources.
REQUIRED_RESULT_TOOLS = ("hunt_leads", "hunt_case")


def env(name: str) -> str:
    """Read a credential from the environment, falling back to the repo .env."""
    if os.environ.get(name):
        return os.environ[name]
    dotenv = REPO / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k == name:
                return v.strip().strip("'\"")
    return ""


@dataclass
class Turn:
    """One streamed chat turn: content, tool-call audit, timings, terminal state."""

    content: list[str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    finish: str = ""
    error: str = ""
    usage: dict[str, Any] | None = None
    done: bool = False
    t0: float = 0.0
    t_end: float = 0.0
    m0: float = 0.0
    first_token_m: float | None = None

    @property
    def answer(self) -> str:
        return "".join(self.content)

    @property
    def prompt_tokens(self) -> int:
        value = (self.usage or {}).get("prompt_tokens")
        return value if isinstance(value, int) else 0


@dataclass
class PromptPeak:
    """Highest prompt-token count across the proof's turns."""

    tokens: int = 0

    def observe(self, turn: Turn) -> None:
        self.tokens = max(self.tokens, turn.prompt_tokens)


def _audit_calls(raw: Any) -> list[dict[str, Any]]:
    """Normalize the exec_audit event's tool_calls into receipt rows."""
    out: list[dict[str, Any]] = []
    for tc in raw if isinstance(raw, list) else []:
        if not isinstance(tc, dict) or not tc.get("tool"):
            continue
        args = tc.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        out.append(
            {
                "tool": str(tc["tool"]),
                "arguments": args if isinstance(args, dict) else {"_raw": args},
                "output": tc.get("output"),
                "source": "exec_audit",
            }
        )
    return out


def fold_payload(turn: Turn, payload: str) -> None:
    """Fold one SSE data payload into the turn."""
    if payload == "[DONE]":
        turn.done = True
        return
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return
    if not isinstance(obj, dict):
        return
    if obj.get("type") == "exec_audit":
        turn.calls.extend(_audit_calls(obj.get("tool_calls")))
        return
    if isinstance(obj.get("error"), str) and obj["error"]:
        turn.error = obj["error"]
        return
    if isinstance(obj.get("usage"), dict):
        turn.usage = obj["usage"]
    for choice in obj.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        if choice.get("finish_reason"):
            turn.finish = str(choice["finish_reason"])
        piece = (choice.get("delta") or {}).get("content")
        if piece:
            if turn.first_token_m is None:
                turn.first_token_m = time.monotonic()
            turn.content.append(str(piece))


def stream_turn(
    owui_url: str,
    key: str,
    model: str,
    prompt: str,
    idle_s: float,
    messages: list[dict[str, str]] | None = None,
) -> Turn:
    """POST one streaming chat turn to OWUI and follow it to [DONE]."""
    body = json.dumps(
        {
            "model": model,
            "stream": True,
            "exec_audit": True,
            "messages": messages or [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        f"{owui_url}/api/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    turn = Turn(t0=time.time(), m0=time.monotonic())
    with urllib.request.urlopen(req, timeout=idle_s) as resp:  # noqa: S310
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data: "):
                fold_payload(turn, line[6:].strip())
    turn.t_end = time.time()
    return turn


def http_json(url: str, key: str = "", timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.load(resp)


def _mcp_result_obj(result: Any) -> dict[str, Any] | None:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", []):
        raw = getattr(block, "text", "")
        if raw:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return None


def wait_for_terminal(review_mcp_url: str, job_id: str) -> dict[str, Any]:
    """Wait through the native MCP endpoint until the durable hunt is terminal."""

    async def poll() -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        started = loop.time()
        checks: list[dict[str, Any]] = []
        async with (
            streamable_http_client(review_mcp_url) as transport,
            ClientSession(transport[0], transport[1]) as session,
        ):
            await session.initialize()
            while True:
                response = await asyncio.wait_for(
                    session.call_tool("hunt_status", {"job_id": job_id}), timeout=120.0
                )
                status = _mcp_result_obj(response)
                if getattr(response, "isError", False) or status is None:
                    raise RuntimeError(f"hunt_status returned no usable status for {job_id}")
                state = str(status.get("status") or "").upper()
                elapsed = round(loop.time() - started, 1)
                stage = status.get("stage")
                checks.append({"status": state, "stage": stage, "elapsed_s": elapsed})
                print(f"  {elapsed}s: status={state} stage={stage or '-'}", flush=True)
                if state in TERMINAL_STATUSES:
                    return {**status, "polls": checks, "elapsed_s": elapsed}
                await asyncio.sleep(1.0)

    return asyncio.run(poll())


def find_turn_trace(pipe_url: str, pipe_key: str, workspace: str, since: float) -> dict | None:
    """The pipeline trace record for this turn, or None (fallback evidence source)."""
    try:
        listing = http_json(f"{pipe_url}/v1/trace?limit=20", pipe_key)
        for summary in listing.get("data") or []:
            if (
                summary.get("workspace") == workspace
                and (summary.get("started_at") or 0) >= since - 2
            ):
                record = http_json(f"{pipe_url}/v1/trace/{summary['correlation_id']}", pipe_key)
                if isinstance(record, dict):
                    return record
    except Exception as exc:  # noqa: BLE001 — the fallback must not mask the turn result
        print(f"note: pipeline trace lookup failed: {exc}", file=sys.stderr)
    return None


def calls_from_trace(record: dict) -> list[dict[str, Any]]:
    """Rebuild the turn's tool calls from trace spans (+ bodies when captured)."""
    flat_args: list[tuple[str, Any]] = []
    entries = (record.get("bodies") or {}).get("tool_arguments") or []
    for entry in entries if isinstance(entries, list) else [entries]:
        if isinstance(entry, dict):
            flat_args.extend(entry.items())
    completed: dict[str, dict] = {}
    requested: list[dict] = []
    for span in record.get("spans") or []:
        if span.get("name") == "tool.requested":
            requested.append(span)
        elif span.get("name") == "tool.completed":
            completed[str(span.get("tool_call_id"))] = span
    calls: list[dict[str, Any]] = []
    cursor = 0
    for span in requested:
        tool = str(span.get("tool") or "")
        args = None
        while cursor < len(flat_args):
            name, value = flat_args[cursor]
            cursor += 1
            if name == tool:
                args = value
                break
        done = completed.get(str(span.get("tool_call_id"))) or {}
        calls.append(
            {
                "tool": tool,
                "arguments": args,
                "output": None,
                "outcome": done.get("outcome"),
                "at_ms": span.get("at_ms"),
                "source": "trace",
            }
        )
    return calls


def _output_obj(call: dict) -> dict | None:
    raw = call.get("output")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _args(call: dict) -> dict:
    args = call.get("arguments")
    return args if isinstance(args, dict) else {}


def _start_job_id(calls: list[dict], answer: str) -> str:
    for call in calls:
        if call.get("tool") == "hunt_start":
            out = _output_obj(call)
            if out and isinstance(out.get("job_id"), str):
                return out["job_id"]
    match = JOB_RE.search(answer)
    return match.group(0) if match else ""


def answer_cites_leads(calls: list[dict], answer: str) -> tuple[bool, str]:
    """Whether the final answer cites the leads the hunt returned."""
    if not answer.strip():
        return False, "the answer is empty"
    notable_ids: list[str] = []
    observed = False
    for call in calls:
        if call.get("tool") == "hunt_leads":
            out = _output_obj(call)
            observed = observed or out is not None
            for lead in (out or {}).get("leads") or []:
                if isinstance(lead, dict) and lead.get("notable_id"):
                    notable_ids.append(str(lead["notable_id"]))
    cited = [nid for nid in notable_ids if nid in answer]
    if cited:
        return True, f"cites notable id(s): {', '.join(cited[:3])}"
    if notable_ids:
        return False, f"none of the {len(notable_ids)} notable ids appear in the answer"
    if not observed:
        return False, "lead outputs were not observable"
    return False, "hunt_leads returned no notable ids"


def answer_cites_case(calls: list[dict], answer: str) -> tuple[bool, str]:
    """Whether the final answer cites the first case's returned id."""
    case_ids = [
        str(output["case_id"])
        for call in calls
        if call.get("tool") == "hunt_case"
        for output in [_output_obj(call)]
        if output is not None and output.get("case_id")
    ]
    cited = [case_id for case_id in case_ids if case_id in answer]
    if cited:
        return True, f"cites case id(s): {', '.join(cited[:3])}"
    if case_ids:
        return False, f"none of the case ids ({', '.join(case_ids[:3])}) appear in the answer"
    return False, "hunt_case returned no case id to cite"


def _check_job_arguments(calls: list[dict], tool: str, job_id: str) -> list[str]:
    selected = [call for call in calls if call.get("tool") == tool]
    if not selected:
        return [f"{tool} was never called"]
    reasons = []
    for call in selected:
        if call.get("arguments") is None:
            reasons.append(f"{tool} arguments were not observable in the turn evidence")
            continue
        arg_job = str(_args(call).get("job_id") or "")
        if not JOB_RE.fullmatch(arg_job):
            reasons.append(f"{tool} did not carry a real R2 job id (job_id={arg_job!r})")
        elif arg_job != job_id:
            reasons.append(f"{tool} used job id {arg_job}, not the started job {job_id}")
    return reasons


def _check_output_job_ids(calls: list[dict], tools: tuple[str, ...], job_id: str) -> list[str]:
    reasons = []
    for call in calls:
        tool = str(call.get("tool") or "")
        if tool not in tools:
            continue
        output = _output_obj(call)
        if output is not None and str(output.get("job_id") or "") != job_id:
            reasons.append(f"{tool} output did not identify the requested job {job_id}")
    return reasons


def _required_result_tools(require_sources: bool) -> tuple[str, ...]:
    if require_sources:
        return (*REQUIRED_RESULT_TOOLS, "hunt_sources")
    return REQUIRED_RESULT_TOOLS


def _check_result_arguments(calls: list[dict], job_id: str, required: tuple[str, ...]) -> list[str]:
    called = {str(call.get("tool") or "") for call in calls}
    reasons: list[str] = []
    for tool in RESULT_TOOLS:
        if tool in required or tool in called:
            reasons.extend(_check_job_arguments(calls, tool, job_id))
    return reasons


def _check_terminal_status(calls: list[dict], status: dict | None, state: str) -> list[str]:
    if not any(call.get("tool") == "hunt_status" for call in calls):
        return []
    if status is None:
        return ["terminal hunt_status output was not observable"]
    if state not in TERMINAL_STATUSES:
        return [f"results turn did not observe a terminal status (status={state or 'unknown'})"]
    return []


def _check_view_outputs(calls: list[dict], tools: tuple[str, ...]) -> list[str]:
    reasons: list[str] = []
    for tool in tools:
        outputs = [_output_obj(call) for call in calls if call.get("tool") == tool]
        if not outputs:
            continue
        output = outputs[-1]
        if output is None:
            reasons.append(f"{tool} output was not observable")
        elif "error" in output:
            reasons.append(f"{tool} returned an error: {_short(output['error'], 200)}")
    return reasons


def grade_progress(calls: list[dict], answer: str) -> tuple[bool, list[str], dict[str, Any]]:
    """Grade the first turn's progress response before any result views are read."""
    names = [str(c.get("tool") or "") for c in calls]
    reasons: list[str] = []
    if "hunt_start" not in names:
        reasons.append("hunt_start was never called")
    job_id = _start_job_id(calls, answer)
    if not JOB_RE.fullmatch(job_id):
        reasons.append(f"hunt_start did not return a real R2 job id (job_id={job_id!r})")
    reasons.extend(_check_job_arguments(calls, "hunt_status", job_id))
    reasons.extend(_check_output_job_ids(calls, ("hunt_status",), job_id))
    status_calls = [call for call in calls if call.get("tool") == "hunt_status"]
    status = _output_obj(status_calls[-1]) if status_calls else None
    state = str((status or {}).get("status") or "").upper()
    if status is None:
        reasons.append("hunt_status output was not observable")
    elif state != "RUNNING":
        reasons.append(f"first turn did not report a running hunt (status={state or 'unknown'})")
    if any(name in {"hunt_sources", "hunt_leads", "hunt_case"} for name in names):
        reasons.append("first turn called a result view before the hunt finished")
    stage = str((status or {}).get("stage") or "")
    if job_id and job_id not in answer:
        reasons.append("the progress answer omitted the started job id")
    if state == "RUNNING" and stage and stage.casefold() not in answer.casefold():
        reasons.append(f"the progress answer omitted the current stage {stage!r}")
    details = {"job_id": job_id, "status": state, "stage": stage, "tools_called": names}
    return (not reasons), reasons, details


def grade_results(
    calls: list[dict], answer: str, job_id: str, require_sources: bool = False
) -> tuple[bool, list[str], dict[str, Any]]:
    """Grade the later turn on the result views its prompt asked for."""
    names = [str(call.get("tool") or "") for call in calls]
    reasons: list[str] = []
    if not JOB_RE.fullmatch(job_id):
        reasons.append(f"the carried job id is not a real R2 id (job_id={job_id!r})")
    if "hunt_start" in names:
        reasons.append("the results turn unexpectedly started a second hunt")
    required = _required_result_tools(require_sources)
    reasons.extend(_check_result_arguments(calls, job_id, required))
    reasons.extend(_check_output_job_ids(calls, RESULT_TOOLS, job_id))
    status_calls = [call for call in calls if call.get("tool") == "hunt_status"]
    status = _output_obj(status_calls[-1]) if status_calls else None
    state = str((status or {}).get("status") or "").upper()
    reasons.extend(_check_terminal_status(calls, status, state))
    reasons.extend(_check_view_outputs(calls, ("hunt_sources", "hunt_leads", "hunt_case")))
    leads_calls = [call for call in calls if call.get("tool") == "hunt_leads"]
    leads = _output_obj(leads_calls[-1]) if leads_calls else None
    if leads is not None and not leads.get("leads"):
        reasons.append("hunt_leads returned no leads")
    cases = [call for call in calls if call.get("tool") == "hunt_case"]
    case = _output_obj(cases[-1]) if cases else None
    if case is not None and ("error" in case or case.get("case") != 1):
        reasons.append("hunt_case did not return the first case")
    cites, how = answer_cites_leads(calls, answer)
    if not cites:
        reasons.append(f"the answer does not cite a returned lead: {how}")
    cites_case, case_how = answer_cites_case(calls, answer)
    if not cites_case:
        reasons.append(f"the answer does not cite the returned case: {case_how}")
    details = {
        "job_id": job_id,
        "status": state,
        "citation": how,
        "case_citation": case_how,
        "tools_called": names,
    }
    return (not reasons), reasons, details


def _short(value: Any, limit: int = RESULT_CHARS) -> str:
    if value is None:
        return "-"
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else f"{text[:limit]}…[{len(text)} chars]"


def print_receipt(
    label: str,
    model: str,
    prompt: str,
    turn: Turn,
    calls: list[dict],
    source: str,
    details: dict,
    peak: PromptPeak,
) -> None:
    print(f"== OWUI hunt chat proof: {label} ==")
    print(f"workspace/model: {model}")
    print(f"prompt: {prompt}")
    print(f"tool-call evidence: {source}")
    print(f"-- tool calls ({len(calls)}) --")
    for i, call in enumerate(calls, 1):
        outcome = f" outcome={call['outcome']}" if call.get("outcome") else ""
        at = f" @{call['at_ms']}ms" if call.get("at_ms") is not None else ""
        print(f"{i:2d}. {call.get('tool')}{at}{outcome}")
        print(f"      args:   {_short(call.get('arguments'))}")
        print(f"      result: {_short(call.get('output'))}")
    print("-- final answer --")
    print(turn.answer or "<empty>")
    print("-- timings --")
    ttft = f"{turn.first_token_m - turn.m0:.1f}s" if turn.first_token_m else "n/a"
    print(
        f"first token: {ttft} | total: {turn.t_end - turn.t0:.1f}s | finish: {turn.finish or '-'}"
    )
    if turn.usage:
        print(f"usage: {_short(turn.usage, 200)}")
    print(f"prompt tokens: {turn.prompt_tokens} | peak prompt tokens: {peak.tokens}")
    print(
        f"job id: {details.get('job_id') or '-'} | status: {details.get('status') or '-'} | "
        f"lead citation: {details.get('citation') or '-'} | "
        f"case citation: {details.get('case_citation') or '-'}"
    )


def _turn_calls(turn: Turn, pipe_url: str, pipe_key: str, model: str) -> tuple[list[dict], str]:
    if turn.calls:
        return turn.calls, "exec_audit event in the OWUI stream"
    record = find_turn_trace(pipe_url, pipe_key, model, turn.t0) if pipe_key else None
    if record is not None:
        return calls_from_trace(record), "pipeline /v1/trace (fallback)"
    return [], "none — tool calls unobservable"


def _finish_turn(
    turn: Turn, passed: bool, reasons: list[str], source: str
) -> tuple[bool, list[str]]:
    if turn.error:
        passed = False
        reasons.append(f"the stream carried an error frame: {_short(turn.error, 200)}")
    if source.startswith("none"):
        passed = False
        reasons.append(
            "no exec_audit event reached the OWUI stream and no pipeline trace was readable "
            "(set PIPELINE_API_KEY; args additionally need PORTAL_TRACE_BODIES=1)"
        )
    return passed, reasons


def _print_verdict(passed: bool, reasons: list[str]) -> None:
    print("-- verdict --")
    print("PASS" if passed else "FAIL")
    for reason in reasons:
        print(f"  - {reason}")


def _progress_turn(
    args: argparse.Namespace, key: str, pipe_key: str, peak: PromptPeak
) -> dict[str, str] | None:
    prompt = f"Start a hunt on index {args.index} and tell me its status and stage."
    print(f">>> TURN 1: {prompt}", flush=True)
    try:
        turn = stream_turn(args.owui_url, key, args.model, prompt, args.idle_s)
    except Exception as exc:  # noqa: BLE001 — any transport failure is a FAIL receipt, not a traceback
        print(f"FAIL: the OWUI chat request failed: {exc}")
        return None
    calls, source = _turn_calls(turn, args.pipeline_url, pipe_key, args.model)
    peak.observe(turn)
    passed, reasons, details = grade_progress(calls, turn.answer)
    passed, reasons = _finish_turn(turn, passed, reasons, source)
    print_receipt("TURN 1", args.model, prompt, turn, calls, source, details, peak)
    if not passed:
        _print_verdict(False, reasons)
        return None
    return {"job_id": details["job_id"], "prompt": prompt, "answer": turn.answer}


def _results_turn(
    args: argparse.Namespace,
    key: str,
    pipe_key: str,
    progress: dict[str, str] | None,
    peak: PromptPeak,
) -> int:
    job_id = args.job_id or progress["job_id"]
    print("-- native MCP wait --")
    try:
        terminal = wait_for_terminal(args.review_mcp_url, job_id)
    except Exception as exc:  # noqa: BLE001 -- include the failed wait in the proof receipt
        print(f"FAIL: waiting for hunt {job_id} failed: {exc}")
        _print_verdict(
            False, ["the native MCP wait failed before the hunt reached a terminal status"]
        )
        return 1
    if str(terminal.get("job_id") or "") != job_id:
        _print_verdict(False, ["the native MCP wait returned a different job id"])
        return 1
    polls = terminal.get("polls") or []
    print(
        f"job id: {job_id} | terminal status: {terminal.get('status')} | "
        f"elapsed: {terminal.get('elapsed_s')}s | status calls: {len(polls)}"
    )
    prompt2 = f"Show me the hunt results for job {job_id}: the top leads and first case."
    messages = (
        [
            {"role": "user", "content": progress["prompt"]},
            {"role": "assistant", "content": progress["answer"]},
            {"role": "user", "content": prompt2},
        ]
        if progress
        else [{"role": "user", "content": prompt2}]
    )
    print(f">>> TURN 2: {prompt2}", flush=True)
    try:
        second = stream_turn(
            args.owui_url,
            key,
            args.model,
            prompt2,
            args.idle_s,
            messages=messages,
        )
    except Exception as exc:  # noqa: BLE001 -- this is the user's later results turn
        print(f"FAIL: the OWUI results request failed: {exc}")
        return 1
    calls2, source2 = _turn_calls(second, args.pipeline_url, pipe_key, args.model)
    peak.observe(second)
    passed2, reasons2, details2 = grade_results(calls2, second.answer, job_id, args.require_sources)
    passed2, reasons2 = _finish_turn(second, passed2, reasons2, source2)
    print_receipt("TURN 2", args.model, prompt2, second, calls2, source2, details2, peak)
    same_status = not details2.get("status") or details2.get("status") == terminal.get("status")
    if not same_status:
        reasons2.append("OWUI's terminal status differs from the native MCP wait receipt")
    passed = passed2 and same_status
    _print_verdict(passed, reasons2)
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default=DEFAULT_INDEX)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--owui-url", default=os.environ.get("OPENWEBUI_URL", "http://localhost:8080").rstrip("/")
    )
    ap.add_argument(
        "--pipeline-url",
        default=os.environ.get("PIPELINE_URL", "http://localhost:9099").rstrip("/"),
    )
    ap.add_argument(
        "--review-mcp-url",
        default=os.environ.get("REVIEW_MCP_URL", "http://localhost:8943/mcp"),
    )
    ap.add_argument("--job-id", help="resume an existing hunt at its current status")
    ap.add_argument(
        "--require-sources",
        action="store_true",
        help="also require the results turn to read hunt_sources",
    )
    ap.add_argument("--idle-s", type=float, default=240.0)
    args = ap.parse_args(argv)
    if args.job_id and not JOB_RE.fullmatch(args.job_id):
        ap.error("--job-id must be a hunt-r2-<12 lowercase hex> identifier")
    if args.idle_s <= 0:
        ap.error("--idle-s must be positive")
    key = env("OWUI_API_KEY")
    if not key:
        print("OWUI_API_KEY is not set (env or .env) — cannot authenticate to Open WebUI")
        return 2
    pipe_key = env("PIPELINE_API_KEY")
    peak = PromptPeak()
    if args.job_id:
        return _results_turn(args, key, pipe_key, None, peak)
    progress = _progress_turn(args, key, pipe_key, peak)
    return 1 if progress is None else _results_turn(args, key, pipe_key, progress, peak)


if __name__ == "__main__":
    sys.exit(main())
