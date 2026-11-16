#!/usr/bin/env python3
"""Live proof: one Open WebUI chat turn runs a hunt through the review MCP tools.

Product path: OWUI :8080 -> Pipeline :9099 -> security-reviewer workspace model ->
hunt_* tool calls on the review MCP (:8943). Sends one prompt, follows the streamed
turn until the model answers or a deadline passes, and prints a receipt: every tool
call (name, args, short result), the final answer, the timings, and PASS/FAIL.

Tool-call evidence: the pipeline's trailing ``exec_audit`` SSE event when the request
reaches it; otherwise the pipeline's ``/v1/trace`` record for the turn (args need
PORTAL_TRACE_BODIES=1). Credentials: OWUI_API_KEY (and PIPELINE_API_KEY for the trace
fallback) from the environment or the repo .env, the same source the UAT and WFE
harnesses read; never printed.

    python3 scripts/proofs/owui_hunt_chat.py [--index hb_kyoushi_s1] [--deadline-s 1500]

Exit codes: 0 PASS, 1 FAIL, 2 setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = "hb_kyoushi_s1"
DEFAULT_MODEL = "security-reviewer"
JOB_RE = re.compile(r"(?<![\w-])hunt-[0-9a-f]{12}(?![\w-])")
RESULT_CHARS = 300


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
    timed_out: bool = False
    t0: float = 0.0
    t_end: float = 0.0
    m0: float = 0.0
    first_token_m: float | None = None

    @property
    def answer(self) -> str:
        return "".join(self.content)


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
    owui_url: str, key: str, model: str, prompt: str, deadline_s: float, idle_s: float
) -> Turn:
    """POST one streaming chat turn to OWUI and follow it to [DONE] or the deadline."""
    body = json.dumps(
        {
            "model": model,
            "stream": True,
            "exec_audit": True,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        f"{owui_url}/api/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    turn = Turn(t0=time.time(), m0=time.monotonic())
    deadline = turn.m0 + deadline_s
    with urllib.request.urlopen(req, timeout=idle_s) as resp:  # noqa: S310
        for raw in resp:
            if time.monotonic() > deadline:
                turn.timed_out = True
                break
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data: "):
                fold_payload(turn, line[6:].strip())
    turn.t_end = time.time()
    return turn


def http_json(url: str, key: str = "", timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.load(resp)


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


def answer_cites_leads(calls: list[dict], answer: str, job_id: str) -> tuple[bool, str]:
    """Whether the final answer cites the leads the hunt returned."""
    if not answer.strip():
        return False, "the answer is empty"
    notable_ids: list[str] = []
    for call in calls:
        if call.get("tool") == "hunt_leads":
            out = _output_obj(call)
            for lead in (out or {}).get("leads") or []:
                if isinstance(lead, dict) and lead.get("notable_id"):
                    notable_ids.append(str(lead["notable_id"]))
    cited = [nid for nid in notable_ids if nid in answer]
    if cited:
        return True, f"cites notable id(s): {', '.join(cited[:3])}"
    if notable_ids:
        return False, f"none of the {len(notable_ids)} notable ids appear in the answer"
    if job_id and job_id in answer and re.search(r"lead", answer, re.I):
        return True, "cites the job id and names leads (lead outputs were not observable)"
    if re.search(r"lead", answer, re.I):
        return False, "mentions leads but cites no notable id and no job id"
    return False, "no lead citation found in the answer"


def _grade_followup(
    calls: list[dict], names: list[str], tool: str, start_i: int, job_id: str
) -> list[str]:
    """Grade one post-start tool: called after hunt_start, carrying the real job id."""
    if tool not in names:
        return [f"{tool} was never called"]
    i = names.index(tool)
    reasons = []
    if start_i >= 0 and i < start_i:
        reasons.append(f"{tool} was called before hunt_start")
    call = calls[i]
    if call.get("arguments") is None:
        return reasons + [
            f"{tool} arguments were not observable (no exec_audit; trace bodies need PORTAL_TRACE_BODIES=1)"
        ]
    arg_job = str(_args(call).get("job_id") or "")
    if not JOB_RE.fullmatch(arg_job):
        reasons.append(f"{tool} did not carry a real job id (job_id={arg_job!r})")
    elif job_id and arg_job != job_id:
        reasons.append(f"{tool} used job id {arg_job}, not the started job {job_id}")
    return reasons


def grade(calls: list[dict], answer: str) -> tuple[bool, list[str], dict[str, Any]]:
    """PASS: hunt_start, then hunt_leads and hunt_case with the real job id, answer cites leads."""
    names = [str(c.get("tool") or "") for c in calls]
    reasons: list[str] = []
    start_i = names.index("hunt_start") if "hunt_start" in names else -1
    if start_i < 0:
        reasons.append("hunt_start was never called")
    job_id = _start_job_id(calls, answer)
    for tool in ("hunt_leads", "hunt_case"):
        reasons.extend(_grade_followup(calls, names, tool, start_i, job_id))
    cites, how = answer_cites_leads(calls, answer, job_id)
    if not cites:
        reasons.append(f"the answer does not cite leads: {how}")
    details = {"job_id": job_id, "citation": how, "tools_called": names}
    return (not reasons), reasons, details


def _short(value: Any, limit: int = RESULT_CHARS) -> str:
    if value is None:
        return "-"
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else f"{text[:limit]}…[{len(text)} chars]"


def print_receipt(
    model: str, prompt: str, turn: Turn, calls: list[dict], source: str, details: dict
) -> None:
    print("== OWUI hunt chat proof ==")
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
    print(f"job id: {details.get('job_id') or '-'} | lead citation: {details.get('citation')}")


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
    ap.add_argument("--deadline-s", type=float, default=1500.0)
    ap.add_argument("--idle-s", type=float, default=240.0)
    args = ap.parse_args(argv)
    if args.deadline_s <= 0 or args.idle_s <= 0:
        ap.error("--deadline-s and --idle-s must be positive")
    key = env("OWUI_API_KEY")
    if not key:
        print("OWUI_API_KEY is not set (env or .env) — cannot authenticate to Open WebUI")
        return 2
    prompt = f"Start a hunt on index {args.index} and show me the top leads and the first case."
    print(f">>> {prompt}", flush=True)
    try:
        turn = stream_turn(args.owui_url, key, args.model, prompt, args.deadline_s, args.idle_s)
    except Exception as exc:  # noqa: BLE001 — any transport failure is a FAIL receipt, not a traceback
        print(f"FAIL: the OWUI chat request failed: {exc}")
        return 1
    calls, source = turn.calls, "exec_audit event in the OWUI stream"
    if not calls:
        pipe_key = env("PIPELINE_API_KEY")
        record = (
            find_turn_trace(args.pipeline_url, pipe_key, args.model, turn.t0) if pipe_key else None
        )
        if record is not None:
            calls, source = calls_from_trace(record), "pipeline /v1/trace (fallback)"
        else:
            source = "none — tool calls unobservable"
    passed, reasons, details = grade(calls, turn.answer)
    if turn.timed_out:
        passed = False
        reasons.insert(0, f"the deadline of {args.deadline_s:.0f}s passed before the turn finished")
    if turn.error:
        passed = False
        reasons.append(f"the stream carried an error frame: {_short(turn.error, 200)}")
    if source.startswith("none"):
        passed = False
        reasons.append(
            "no exec_audit event reached the OWUI stream and no pipeline trace was readable "
            "(set PIPELINE_API_KEY; args additionally need PORTAL_TRACE_BODIES=1)"
        )
    print_receipt(args.model, prompt, turn, calls, source, details)
    print("-- verdict --")
    print("PASS" if passed else "FAIL")
    for reason in reasons:
        print(f"  - {reason}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
