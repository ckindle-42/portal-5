#!/usr/bin/env python3
"""Pipeline tool probe for one kit seat. Does not pick the model; the seat id does.

The orchestrator runs this. A --dry-run prints the request and does not connect.
Requires PIPELINE_API_KEY in the environment for a live run. Never prints the key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

PIPELINE = os.environ.get("PIPELINE_URL", "http://localhost:9099")

NESTED_TOOL = {
    "type": "function",
    "function": {
        "name": "kit_nested_probe",
        "description": "Record one host fact. spec.limits is an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "limits": {
                            "type": "object",
                            "properties": {"timeout_s": {"type": "integer"}},
                            "required": ["timeout_s"],
                        },
                    },
                    "required": ["command", "limits"],
                }
            },
            "required": ["spec"],
        },
    },
}

PROSE_THEN_CALL = (
    "Write one short sentence that names the machine, then call kit_nested_probe. "
    "spec.command must be the string uname. spec.limits must be an object whose "
    "timeout_s is the integer 5. Do not describe the call instead of making it."
)


def _auth_header() -> dict[str, str]:
    key = os.environ.get("PIPELINE_API_KEY", "")
    if not key:
        sys.exit("PIPELINE_API_KEY is unset")
    return {"Authorization": f"Bearer {key}"}


def _post(path: str, body: dict, correlation: str, timeout: int) -> tuple[int, dict, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{PIPELINE}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            **_auth_header(),
            "X-Correlation-ID": correlation,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, dict(resp.headers), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        return exc.code, dict(exc.headers), {"error": detail}


def _get(path: str, timeout: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{PIPELINE}{path}",
        headers=_auth_header(),
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode(errors="replace")}


def _message(payload: dict) -> dict:
    choices = payload.get("choices") or []
    if not choices:
        return {}
    return choices[0].get("message") or {}


def _args(call: dict) -> dict:
    fn = call.get("function") or {}
    raw = fn.get("arguments")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _nested_ok(call: dict) -> bool:
    if (call.get("function") or {}).get("name") != "kit_nested_probe":
        return False
    spec = _args(call).get("spec")
    if not isinstance(spec, dict):
        return False
    limits = spec.get("limits")
    return (
        spec.get("command") == "uname" and isinstance(limits, dict) and limits.get("timeout_s") == 5
    )


def _think_body(think: bool) -> dict:
    return {
        "think": think,
        "chat_template_kwargs": {"enable_thinking": think},
    }


def build_nested(seat: str, think: bool) -> dict:
    body = {
        "model": seat,
        "stream": False,
        "messages": [{"role": "user", "content": PROSE_THEN_CALL}],
        "tools": [NESTED_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "kit_nested_probe"}},
        "portal_client_tools_only": True,
    }
    body.update(_think_body(think))
    return body


def build_followup(seat: str, think: bool, call: dict) -> dict:
    body = {
        "model": seat,
        "stream": False,
        "messages": [
            {"role": "user", "content": PROSE_THEN_CALL},
            {"role": "assistant", "content": None, "tool_calls": [call]},
            {
                "role": "tool",
                "tool_call_id": call.get("id") or "kit-call",
                "content": "Darwin arm64",
            },
            {
                "role": "user",
                "content": "Using only the tool result, reply with the operating system name.",
            },
        ],
        "portal_client_tools_only": True,
    }
    body.update(_think_body(think))
    return body


def build_bash(seat: str, think: bool) -> dict:
    body = {
        "model": seat,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": "Call execute_bash to run exactly: echo portal5-kit",
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "execute_bash"}},
    }
    body.update(_think_body(think))
    return body


def build_reasoning(seat: str) -> dict:
    """Qwen3.8 spot probe. medium becomes max_tokens 16384 for the whole reply."""
    body = build_nested(seat, True)
    body["reasoning_effort"] = "medium"
    body["chat_template_kwargs"]["preserve_thinking"] = True
    return body


def _nested_phase(args: argparse.Namespace, nested: dict) -> dict | None:
    cid = f"kit-{uuid.uuid4().hex[:12]}"
    status, headers, payload = _post("/v1/chat/completions", nested, cid, args.timeout)
    route = headers.get("x-portal-route") or headers.get("X-Portal-Route")
    echoed = headers.get("X-Correlation-ID") or headers.get("x-correlation-id") or cid
    message = _message(payload)
    calls = message.get("tool_calls") or []
    content = message.get("content") or ""
    print(f"phase=nested status={status} route={route} correlation={echoed}")
    print(f"tool_calls={len(calls)} content_chars={len(content)}")
    ok = status == 200 and any(_nested_ok(c) for c in calls)
    print(f"nested_ok={ok}")
    if not ok:
        print(json.dumps(payload)[:2000])
        return None
    return next(c for c in calls if _nested_ok(c))


def _followup_phase(args: argparse.Namespace, think: bool, call: dict) -> bool:
    cid2 = f"kit-{uuid.uuid4().hex[:12]}"
    status2, headers2, payload2 = _post(
        "/v1/chat/completions", build_followup(args.seat, think, call), cid2, args.timeout
    )
    follow = _message(payload2).get("content") or ""
    print(f"phase=followup status={status2} route={headers2.get('x-portal-route')}")
    print(f"followup_mentions_darwin={'Darwin' in follow}")
    if status2 != 200 or "Darwin" not in follow:
        print(follow[:1000])
        return False
    return True


def _bash_phase(args: argparse.Namespace, think: bool) -> bool:
    cid3 = f"kit-{uuid.uuid4().hex[:12]}"
    status3, headers3, payload3 = _post(
        "/v1/chat/completions", build_bash(args.seat, think), cid3, args.timeout
    )
    bash_msg = _message(payload3)
    bash_calls = bash_msg.get("tool_calls") or []
    bash_text = bash_msg.get("content") or ""
    tstatus, trace = _get(f"/v1/trace/{headers3.get('X-Correlation-ID') or cid3}")
    trace_text = json.dumps(trace)
    bash_hit = (
        any((c.get("function") or {}).get("name") == "execute_bash" for c in bash_calls)
        or "portal5-kit" in bash_text
        or "execute_bash" in trace_text
    )
    print(f"phase=execute_bash status={status3} route={headers3.get('x-portal-route')}")
    print(f"execute_bash_seen={bash_hit} trace_status={tstatus}")
    if not bash_hit:
        print(bash_text[:1000])
        print(trace_text[:2000])
        return False
    return True


def _reasoning_phase(args: argparse.Namespace) -> bool:
    cid4 = f"kit-{uuid.uuid4().hex[:12]}"
    status4, headers4, payload4 = _post(
        "/v1/chat/completions", build_reasoning(args.seat), cid4, args.timeout
    )
    echoed4 = headers4.get("X-Correlation-ID") or cid4
    tstatus4, trace4 = _get(f"/v1/trace/{echoed4}")
    applied = json.dumps(trace4)
    print(f"phase=reasoning_effort status={status4} trace_status={tstatus4}")
    print("expect output_limit 16384. preserve_thinking is not a trace field.")
    print("oMLX copies the label onto chat_template_kwargs and drops top-level reasoning_effort.")
    print("Ollama native transport drops chat_template_kwargs, including preserve_thinking.")
    limit_ok = "16384" in applied
    print(f"trace_mentions_16384={limit_ok}")
    print(applied[:2500])
    if status4 != 200:
        print(json.dumps(payload4)[:1500])
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("seat", help="auto-coding::kit-... or a persona slug")
    parser.add_argument("--think", choices=("true", "false"), default="true")
    parser.add_argument(
        "--qwen38", action="store_true", help="also send the reasoning_effort probe"
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    think = args.think == "true"
    nested = build_nested(args.seat, think)
    if args.dry_run:
        print(json.dumps({"nested": nested, "bash": build_bash(args.seat, think)}, indent=2))
        if args.qwen38:
            print(json.dumps({"reasoning": build_reasoning(args.seat)}, indent=2))
        print("dry-run: no request sent")
        return 0
    call = _nested_phase(args, nested)
    if call is None or not _followup_phase(args, think, call) or not _bash_phase(args, think):
        return 1
    if args.qwen38:
        if not _reasoning_phase(args):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
