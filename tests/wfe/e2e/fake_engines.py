"""Fake Ollama and oMLX for the WFE end-to-end rig (tests/wfe/e2e/rig.py): scripted,
deterministic models; failure switches are files in the flags directory."""

import asyncio
import hashlib
import json
import os
import sys
import time

import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

B = yaml.safe_load(open(sys.argv[1]))
OLLAMA_PORT, OMLX_PORT, FLAGS = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
OLLAMA_IDS, OMLX_IDS = [], []
for be in B["backends"]:
    ids = [m["id"] if isinstance(m, dict) else m for m in be.get("models") or []] + list(
        (be.get("aliases") or {}).values()
    )
    (OLLAMA_IDS if be["type"] == "ollama" else OMLX_IDS).extend(ids)
LOG = open(os.path.join(FLAGS, "engine.log"), "a")


def log(engine, path, body):
    LOG.write(
        json.dumps(
            {
                "t": time.time(),
                "engine": engine,
                "path": path,
                "model": (body or {}).get("model"),
                "n_msgs": len((body or {}).get("messages") or []),
                "tools": [
                    t.get("function", {}).get("name") for t in (body or {}).get("tools") or []
                ],
            }
        )
        + "\n"
    )
    LOG.flush()


def script(model, messages, tools):
    """First turn with a file_read tool: read packet.json. After a tool result: answer."""
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    names = [t.get("function", {}).get("name") for t in tools or []]
    if "file_read" in names and not has_tool_result:
        return None, {"name": "file_read", "arguments": {"path": "packet.json"}}
    n_results = sum(1 for m in messages if m.get("role") == "tool")
    if "attach_source" in names and n_results == 0:
        return None, {
            "name": "attach_source",
            "arguments": {"session_id": "model_picked", "path": "sales.csv", "table": "sales"},
        }
    if "run_sql" in names and n_results == 1:
        return None, {
            "name": "run_sql",
            "arguments": {
                "session_id": "model_picked",
                "sql": "SELECT sum(amount) AS total FROM sales",
            },
        }
    if "run_sql" in names and n_results >= 2:
        last = str(messages[-1].get("content", ""))
        total = "15" if "15" in last else "unknown"
        return json.dumps({"total_amount": total}), None
    if "create_word_document" in names and not has_tool_result:
        return None, {
            "name": "create_word_document",
            "arguments": {"title": "Rig report", "content": "# Findings\nAll checks passed."},
        }
    det = ["SUPPORTED", "CONTRADICTED", "ABSENT", "ABSTAIN", "PARTIAL"][
        int(hashlib.sha256((model + json.dumps(messages[-1:])).encode()).hexdigest(), 16) % 5
    ]
    if "granite" not in model:
        det = "SUPPORTED"
    return json.dumps({"determination": det, "cited_refs": ["CIP-007-6 R2"]}), None


ol = FastAPI()


@ol.get("/api/version")
async def v():
    return {"version": "0.0.0-fake"}


@ol.get("/api/tags")
async def tags():
    return {
        "models": [
            {
                "name": i,
                "model": i,
                "size": 5_000_000_000,
                "digest": hashlib.sha256(i.encode()).hexdigest(),
            }
            for i in OLLAMA_IDS
        ]
    }


@ol.get("/api/ps")
async def ps():
    return {"models": []}


@ol.post("/api/show")
async def show(req: Request):
    b = await req.json()
    log("ollama", "/api/show", b)
    return {
        "capabilities": ["completion", "tools", "thinking"],
        "parameters": "num_ctx 32768",
        "template": "",
        "model_info": {},
    }


@ol.post("/api/generate")
async def gen(req: Request):
    b = await req.json()
    log("ollama", "/api/generate", b)
    return {"done": True}


@ol.post("/api/chat")
async def chat(req: Request):
    b = await req.json()
    log("ollama", "/api/chat", b)

    if os.path.exists(os.path.join(FLAGS, "fail_ollama")):
        return JSONResponse({"error": "fake failure"}, status_code=500)
    text, call = script(b["model"], b.get("messages") or [], b.get("tools"))

    async def gen():
        if call:
            yield (
                json.dumps(
                    {
                        "model": b["model"],
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{"function": call}],
                        },
                        "done": False,
                    }
                )
                + "\n"
            )
        else:
            for i in range(0, len(text), 20):
                yield (
                    json.dumps(
                        {
                            "model": b["model"],
                            "message": {"role": "assistant", "content": text[i : i + 20]},
                            "done": False,
                        }
                    )
                    + "\n"
                )
        yield (
            json.dumps(
                {
                    "model": b["model"],
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 500,
                    "eval_count": 40,
                }
            )
            + "\n"
        )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


om = FastAPI()


@om.get("/health")
async def h():
    return {"status": "ok"}


@om.get("/v1/models")
async def models():
    return {"data": [{"id": i, "object": "model"} for i in OMLX_IDS]}


@om.get("/v1/models/status")
async def mstatus():
    return {"models": []}


@om.get("/api/status")
async def st():
    return {"models": [], "memory": {"total": 512e9, "used": 64e9}}


@om.post("/admin/api/login")
async def login():
    return {"ok": True}


@om.get("/admin/api/models")
async def amodels():
    return []


USAGE = {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540}
SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repetition_penalty", "max_tokens")


def _tool_call(call: dict, index: int | None = None) -> dict:
    tc = {
        "id": "call_1",
        "type": "function",
        "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
    }
    return {"index": index, **tc} if index is not None else tc


def _sse(model: str, delta: dict | None, finish=None, usage=None) -> str:
    body = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [] if usage else [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage:
        body["usage"] = usage
    return "data: " + json.dumps(body) + "\n\n"


async def _omlx_stream(model: str, text: str | None, call: dict | None):
    if call:
        yield _sse(model, {"role": "assistant", "tool_calls": [_tool_call(call, 0)]})
        yield _sse(model, {}, "tool_calls")
    else:
        for i in range(0, len(text), 20):
            yield _sse(model, {"content": text[i : i + 20]})
        yield _sse(model, {}, "stop")
    yield _sse(model, None, usage=USAGE)
    yield "data: [DONE]\n\n"


def _omlx_message(model: str, text: str | None, call: dict | None) -> dict:
    msg = {"role": "assistant", "content": text or ""}
    if call:
        msg["tool_calls"] = [_tool_call(call)]
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "model": model,
        "usage": USAGE,
        "choices": [
            {"index": 0, "message": msg, "finish_reason": "tool_calls" if call else "stop"}
        ],
    }


@om.post("/v1/chat/completions")
async def ochat(req: Request):
    b = await req.json()
    log("omlx", "/v1/chat/completions", b)
    if os.path.exists(os.path.join(FLAGS, "fail_omlx")):
        return JSONResponse({"error": {"message": "fake failure"}}, status_code=500)
    LOG.write(
        json.dumps(
            {
                "engine": "omlx",
                "model": b["model"],
                "sampling": {k: b.get(k) for k in SAMPLING_KEYS},
            }
        )
        + "\n"
    )
    LOG.flush()
    text, call = script(b["model"], b.get("messages") or [], b.get("tools"))
    if not b.get("stream"):
        return _omlx_message(b["model"], text, call)
    return StreamingResponse(_omlx_stream(b["model"], text, call), media_type="text/event-stream")


async def main():
    s1 = uvicorn.Server(uvicorn.Config(ol, host="127.0.0.1", port=OLLAMA_PORT, log_level="warning"))
    s2 = uvicorn.Server(uvicorn.Config(om, host="127.0.0.1", port=OMLX_PORT, log_level="warning"))
    await asyncio.gather(s1.serve(), s2.serve())


asyncio.run(main())
