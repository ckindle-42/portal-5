"""Reading-seat triage: the same compliance-reading turn, direct to each engine
and through the pipeline, under named sampling arms.

Why: a loop or an empty answer seen through the pipeline is either the engine
(template, parser, sampling) or the pipeline's handling of it. The DIRECT arms
run the pipeline's own tool loop outside it — the workspace's
``system_prompt_append`` as the system message, the workspace's tools as served
by the compliance MCP, results JSON-encoded into ``tool`` messages, the
assistant tool turn with no content — against oMLX ``/v1`` and Ollama's native
``/api/chat`` (what ``OllamaNativeTransport`` sends). The PIPELINE arm sends the
turn as a client does. A failure present direct is the engine's; a failure
present only through the pipeline is the pipeline's.

    uv run python scripts/compliance/reading_loop_triage.py \\
        --out reports/.../triage.json --arms omlx:current,ollama:current,pipeline:ws \\
        --questions path/to/questions.json

A question file is ``[{"key": ..., "question": ...}]``. Arms are
``<route>:<sampling>`` — route ``omlx`` | ``ollama`` | ``pipeline``; sampling
``current`` (the workspace's declared values with the harness's historical
temperature 0.0), ``ws`` (the workspace's declared values, nothing overridden —
pipeline only: the request carries no sampling) or ``card`` (the model card's
published values).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

_REPO = Path(__file__).resolve().parents[2]
PIPELINE = os.environ.get("PIPELINE_URL", "http://localhost:9099")
OMLX = os.environ.get("OMLX_URL", "http://localhost:8085")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MCP = os.environ.get("COMPLIANCE_MCP_URL", "http://localhost:8937")
WORKSPACE = "compliance-reading"
MAX_HOPS = 20
#: Per-hop output cap for the direct arms — enough for any real answer; a
#: runaway reaches it and is recorded as one, instead of burning 900 s.
HOP_TOKENS = 6000


def _pipeline_key() -> str:
    for line in (_REPO / ".env").read_text().splitlines():
        if line.startswith("PIPELINE_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def _workspace() -> dict[str, Any]:
    cfg = yaml.safe_load((_REPO / "config" / "portal.yaml").read_text())
    return cfg["workspaces"][WORKSPACE]


def _alias_target(hint: str) -> str:
    be = yaml.safe_load((_REPO / "config" / "backends.yaml").read_text())
    for backend in be.get("backends") or []:
        if backend.get("type") == "omlx" and hint in (backend.get("aliases") or {}):
            return str(backend["aliases"][hint])
    raise SystemExit(f"no oMLX alias for {hint}")


def _sampling(ws: dict[str, Any], arm: str) -> dict[str, Any]:
    if arm == "card":
        # google/gemma-4 model card + unsloth: temperature 1.0, top_p 0.95,
        # top_k 64; no repetition penalty is published.
        return {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "min_p": 0.0}
    out = {k: ws[k] for k in ("temperature", "top_p", "top_k", "min_p") if k in ws}
    if "repeat_penalty" in ws:
        out["repeat_penalty"] = ws["repeat_penalty"]
    if arm == "current":
        out["temperature"] = 0.0
    return out


def _tools(client: httpx.Client, names: list[str]) -> list[dict[str, Any]]:
    # In the workspace's declared order — the order the pipeline offers them.
    # At greedy decoding the order alone flipped a turn from a full answer to
    # a two-token fragment (PIPELINE_ALIGNMENT_V1 §13), so fidelity matters.
    served = {
        t["function"]["name"]: t for t in client.get(f"{MCP}/tools", timeout=30).json()["tools"]
    }
    return [served[n] for n in names if n in served]


def _dispatch(client: httpx.Client, call: dict[str, Any]) -> str:
    fn = call["function"]
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid JSON arguments: {args[:200]}"})
    r = client.post(f"{MCP}/tools/{fn['name']}", json={"arguments": args}, timeout=600)
    try:
        result = r.json()
    except ValueError:
        return r.text
    return json.dumps(result) if isinstance(result, (dict, list)) else str(result)


def _looping(text: str) -> bool:
    """A runaway repeats itself: some 120-char window recurs 3+ times."""
    if len(text) < 8000:
        return False
    tail = text[-120:]
    return text.count(tail) >= 3


def _direct(
    client: httpx.Client,
    route: str,
    model: str,
    system: str,
    question: str,
    tools: list[dict[str, Any]],
    sampling: dict[str, Any],
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    hops: list[dict[str, Any]] = []
    started = time.monotonic()
    for _hop in range(MAX_HOPS):
        if route == "omlx":
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "max_tokens": HOP_TOKENS,
                "chat_template_kwargs": {"enable_thinking": False},
                **{k: v for k, v in sampling.items() if k != "repeat_penalty"},
            }
            if "repeat_penalty" in sampling:
                body["repetition_penalty"] = sampling["repeat_penalty"]
            data = client.post(f"{OMLX}/v1/chat/completions", json=body, timeout=1200).json()
            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            thinking = msg.get("reasoning_content") or msg.get("reasoning") or ""
            calls = msg.get("tool_calls") or []
            finish = choice.get("finish_reason")
            usage = data.get("usage") or {}
            out_tokens = usage.get("completion_tokens")
        else:
            native_msgs = []
            for m in messages:
                m = dict(m)
                if m.get("tool_calls"):
                    m["tool_calls"] = [
                        {
                            "function": {
                                "name": c["function"]["name"],
                                "arguments": json.loads(c["function"]["arguments"] or "{}"),
                            }
                        }
                        for c in m["tool_calls"]
                    ]
                if m.get("content") is None:
                    m["content"] = ""
                native_msgs.append(m)
            body = {
                "model": model,
                "messages": native_msgs,
                "tools": tools,
                "stream": False,
                "think": False,
                "options": {**sampling, "num_predict": HOP_TOKENS},
            }
            data = client.post(f"{OLLAMA}/api/chat", json=body, timeout=1200).json()
            msg = data.get("message") or {}
            content = msg.get("content") or ""
            thinking = msg.get("thinking") or ""
            calls = [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": c["function"]["name"],
                        "arguments": json.dumps(c["function"].get("arguments") or {}),
                    },
                }
                for i, c in enumerate(msg.get("tool_calls") or [])
            ]
            finish = "tool_calls" if calls else data.get("done_reason")
            out_tokens = data.get("eval_count")
        hops.append(
            {
                "content_chars": len(content),
                "thinking_chars": len(thinking),
                "tool_calls": [c["function"]["name"] for c in calls],
                "finish": finish,
                "completion_tokens": out_tokens,
            }
        )
        if not calls:
            return {
                "answer": content,
                "thinking": thinking[:4000],
                "hops": hops,
                "wall_s": round(time.monotonic() - started, 1),
            }
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": c.get("id") or f"call_{i}",
                        "type": "function",
                        "function": c["function"],
                    }
                    for i, c in enumerate(calls)
                ],
            }
        )
        hops[-1]["calls"] = []
        for i, c in enumerate(calls):
            result = _dispatch(client, c)
            hops[-1]["calls"].append(
                {"arguments": str(c["function"].get("arguments"))[:300], "result": result[:300]}
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": c.get("id") or f"call_{i}",
                    "name": c["function"]["name"],
                    "content": result,
                }
            )
    return {
        "answer": "",
        "hops": hops,
        "error": "hop limit",
        "wall_s": round(time.monotonic() - started, 1),
    }


def _pipeline_body(sampling_arm: str, sampling: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": WORKSPACE,
        "stream": True,
        "messages": [{"role": "user", "content": ""}],
    }
    if sampling_arm != "ws":
        body.update({key: value for key, value in sampling.items() if key != "repeat_penalty"})
        if "repeat_penalty" in sampling:
            body["repeat_penalty"] = sampling["repeat_penalty"]
            body["repetition_penalty"] = sampling["repeat_penalty"]
    return body


def _stream_state(started: float) -> dict[str, Any]:
    return {
        "started": started,
        "parts": [],
        "reasoning": [],
        "raw_sse_lines": [],
        "route": "",
        "correlation_id": "",
        "finish_reason": "",
        "usage": {},
        "status_code": None,
        "terminal_frames": 0,
    }


def _consume_sse_line(line: str, state: dict[str, Any]) -> bool:
    state["raw_sse_lines"].append(line)
    if time.monotonic() - state["started"] > 900:
        state["error"] = "900s budget"
        state["wall_s"] = 900.0
        return True
    if not line.startswith("data: "):
        return False
    if line.strip() == "data: [DONE]":
        state["terminal_frames"] += 1
        return False
    try:
        event = json.loads(line[6:])
    except ValueError:
        return False
    choice = (event.get("choices") or [{}])[0] or {}
    delta = choice.get("delta") or {}
    if delta.get("content"):
        state["parts"].append(delta["content"])
    state["reasoning"].extend(
        str(delta[channel])
        for channel in ("reasoning_content", "reasoning", "thinking")
        if delta.get(channel)
    )
    state["finish_reason"] = choice.get("finish_reason") or state["finish_reason"]
    state["usage"] = event.get("usage") or state["usage"]
    return False


def _stream_result(state: dict[str, Any], error: str = "") -> dict[str, Any]:
    result = {
        "answer": "".join(state["parts"]),
        "reasoning": "".join(state["reasoning"]),
        "raw_sse_lines": state["raw_sse_lines"],
        "route": state["route"],
        "correlation_id": state["correlation_id"],
        "status_code": state["status_code"],
        "finish_reason": state["finish_reason"],
        "usage": state["usage"],
        "terminal_frames": state["terminal_frames"],
        "wall_s": state.get("wall_s", round(time.monotonic() - state["started"], 1)),
    }
    if error or state.get("error"):
        result["error"] = error or state["error"]
    return result


def _pipeline_trace(client: httpx.Client, correlation_id: str) -> dict[str, Any] | None:
    if not correlation_id:
        return None
    try:
        from portal.modules.compliance.core.transport_dialects import _pipeline_api_key

        response = client.get(
            f"{PIPELINE}/v1/trace/{correlation_id}",
            headers={"Authorization": f"Bearer {_pipeline_api_key()}"},
            timeout=15,
        )
        return response.json() if response.is_success else None
    except Exception:
        return None


def _pipeline(
    client: httpx.Client, question: str, sampling_arm: str, sampling: dict[str, Any]
) -> dict[str, Any]:
    body = _pipeline_body(sampling_arm, sampling)
    body["messages"][0]["content"] = question
    started = time.monotonic()
    state = _stream_state(started)
    try:
        with client.stream(
            "POST",
            f"{PIPELINE}/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {_pipeline_key()}"},
            timeout=httpx.Timeout(900, connect=10),
        ) as response:
            state["status_code"] = response.status_code
            state["route"] = response.headers.get("x-portal-route", "")
            state["correlation_id"] = (
                response.headers.get("x-correlation-id")
                or response.headers.get("x-portal-correlation-id")
                or ""
            )
            for line in response.iter_lines():
                if _consume_sse_line(line, state):
                    return _stream_result(state)
    except httpx.HTTPError as exc:
        return _stream_result(state, repr(exc))
    trace = _pipeline_trace(client, state["correlation_id"])
    return {**_stream_result(state), "trace": trace}


def _classify(result: dict[str, Any]) -> str:
    answer = result.get("answer") or ""
    if result.get("error"):
        return "error:" + str(result["error"])[:40]
    if not answer.strip() or "Model returned an empty response" in answer:
        return "empty"
    # a 2-token fragment ("\n}\n") or the pipeline's hop-limit notice is not an answer
    if len(answer.strip()) < 200 or "Tool-use limit" in answer:
        return "degenerate"
    if _looping(answer) or len(answer) > 30000:
        return "runaway"
    return "answered"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--arms", default="omlx:current,ollama:current,pipeline:current")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--private-out",
        type=Path,
        default=None,
        help="permission-restricted JSONL for questions, answers, raw SSE, and trace bodies",
    )
    return parser.parse_args()


def _private_path(args: argparse.Namespace) -> Path:
    if args.private_out is not None:
        return args.private_out
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return (
        _REPO
        / "portal/modules/compliance/data/private/reading_loop_triage"
        / stamp
        / f"{args.out.stem}.jsonl"
    )


def _load_private(path: Path) -> tuple[list[dict[str, Any]], set[tuple[str, str, int]]]:
    rows: list[dict[str, Any]] = []
    completed: set[tuple[str, str, int]] = set()
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                rows.append(row)
                completed.add((row["arm"], row["key"], int(row["repeat"])))
    return rows, completed


def _public_row(row: dict[str, Any], private_path: Path) -> dict[str, Any]:
    result = row["result"]
    trace = result.get("trace") or {}
    return {
        "arm": row["arm"],
        "key": row["key"],
        "repeat": row["repeat"],
        "verdict": row["verdict"],
        "answer_chars": len(result.get("answer") or ""),
        "route": result.get("route", ""),
        "route_backend": trace.get("backend", ""),
        "served_model": trace.get("served_model", ""),
        "correlation_id": result.get("correlation_id", ""),
        "finish_reason": result.get("finish_reason", ""),
        "status_code": result.get("status_code"),
        "usage": result.get("usage") or {},
        "options_applied": trace.get("options_applied"),
        "wall_s": result.get("wall_s"),
        "error_type": "HTTPError" if result.get("error") else "",
        "terminal_frames": result.get("terminal_frames"),
        "private_receipt": str(private_path),
    }


def _write_public(
    args: argparse.Namespace, question_count: int, private_rows: list[dict[str, Any]]
) -> None:
    rows = [_public_row(row, args.private_out) for row in private_rows]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "arms": args.arms,
        "question_count": question_count,
        "repeats": args.repeats,
        "attempted": len(rows),
        "answered": sum(row["verdict"] == "answered" for row in rows),
        "private_receipt": str(args.private_out),
        "rows": rows,
    }
    args.out.write_text(json.dumps(summary, indent=1))


def _attempt(
    client: httpx.Client,
    route: str,
    sampling_arm: str,
    sampling: dict[str, Any],
    question: dict[str, Any],
    ws: dict[str, Any],
    hint: str,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    if route == "pipeline":
        return _pipeline(client, question["question"], sampling_arm, sampling)
    model = _alias_target(hint) if route == "omlx" else os.environ.get("TRIAGE_OLLAMA_MODEL", hint)
    return _direct(
        client, route, model, str(ws["system_prompt_append"]), question["question"], tools, sampling
    )


def _save_attempt(
    args: argparse.Namespace,
    row: dict[str, Any],
    private_rows: list[dict[str, Any]],
    completed: set[tuple[str, str, int]],
    question: dict[str, Any],
    question_count: int,
) -> None:
    with args.private_out.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    args.private_out.chmod(0o600)
    private_rows.append(row)
    completed.add((row["arm"], row["key"], row["repeat"]))
    result = row["result"]
    print(
        f"{row['arm']:18s} {question['key']:32s} r{row['repeat']} {row['verdict']:10s} "
        f"{len(result.get('answer') or ''):6d} chars {result.get('wall_s')}s",
        flush=True,
    )
    _write_public(args, question_count, private_rows)


def _run_campaign(
    args: argparse.Namespace,
    client: httpx.Client,
    ws: dict[str, Any],
    hint: str,
    questions: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    private_rows: list[dict[str, Any]],
    completed: set[tuple[str, str, int]],
) -> None:
    for arm in args.arms.split(","):
        route, sampling_arm = arm.split(":")
        sampling = _sampling(ws, sampling_arm)
        for question in questions:
            for repeat in range(args.repeats):
                key = (arm, question["key"], repeat)
                if key in completed:
                    continue
                result = _attempt(client, route, sampling_arm, sampling, question, ws, hint, tools)
                row = {
                    "arm": arm,
                    "sampling": sampling,
                    "key": question["key"],
                    "repeat": repeat,
                    "question": question["question"],
                    "verdict": _classify(result),
                    "result": result,
                }
                _save_attempt(args, row, private_rows, completed, question, len(questions))


def main() -> int:
    args = _arguments()
    ws = _workspace()
    hint = str(ws["model_hint"])
    questions = json.loads(args.questions.read_text())
    args.private_out = _private_path(args)
    args.private_out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.private_out.parent.chmod(0o700)
    private_rows, completed = _load_private(args.private_out)
    with httpx.Client() as client:
        tools = _tools(client, list(ws.get("tools") or []))
        _run_campaign(args, client, ws, hint, questions, tools, private_rows, completed)
    _write_public(args, len(questions), private_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
