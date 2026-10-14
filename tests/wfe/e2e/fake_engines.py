"""Fake Ollama and oMLX for the WFE end-to-end rig (tests/wfe/e2e/rig.py): scripted,
deterministic models; failure switches are files in the flags directory."""

import asyncio
import hashlib
import json
import os
import re
import sys
import time

import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

B = yaml.safe_load(open(sys.argv[1]))
OLLAMA_PORT, OMLX_PORT, FLAGS = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
EG2_PORT = int(sys.argv[5]) if len(sys.argv) > 5 else 0
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
                "text": json.dumps((body or {}).get("messages") or [])[:20000],
            }
        )
        + "\n"
    )
    LOG.flush()


def _data_flow(names, n, messages):
    """attach_source, then run_sql, then answer with the total."""
    if "attach_source" in names and n == 0:
        args = {"session_id": "model_picked", "path": "sales.csv", "table": "sales"}
        return None, {"name": "attach_source", "arguments": args}
    if "run_sql" in names and n == 1:
        sql = "SELECT sum(amount) AS total FROM sales"
        return None, {"name": "run_sql", "arguments": {"session_id": "model_picked", "sql": sql}}
    if "run_sql" in names and n >= 2:
        total = "15" if "15" in str(messages[-1].get("content", "")) else "unknown"
        return json.dumps({"total_amount": total}), None
    return None


def _kb_flow(names, n, messages):
    """kb_search on the operator's KB id (a scope must force it onto the run's KB), then answer."""
    if "kb_search" not in names:
        return None
    if n == 0:
        return None, {
            "name": "kb_search",
            "arguments": {"kb_id": "opkb", "query": "relay setpoint amps"},
        }
    found = re.findall(r"\d+ amps", str(messages[-1].get("content", "")))
    return json.dumps({"setpoint": found[0] if found else "unknown"}), None


def _compliance_flow(names, n, messages):
    """nerc_cip_requirement for CIP-007-6 R2 Part 2.2, then answer with the interval it states."""
    if "nerc_cip_requirement" not in names:
        return None
    if n == 0:
        return None, {
            "name": "nerc_cip_requirement",
            "arguments": {"req_id": "CIP-007-6 R2 Part 2.2"},
        }
    found = re.findall(r"\d+ calendar days", str(messages[-1].get("content", "")))
    return json.dumps({"interval": found[0] if found else "unknown"}), None


def script(model, messages, tools):
    """Deterministic scripted model: a tool flow when its tools are offered, else an answer."""
    names = [t.get("function", {}).get("name") for t in tools or []]
    n = sum(1 for m in messages if m.get("role") == "tool")
    if "file_read" in names and n == 0:
        return None, {"name": "file_read", "arguments": {"path": "packet.json"}}
    for flow in (_data_flow, _kb_flow, _compliance_flow):
        out = flow(names, n, messages)
        if out:
            return out
    if "create_word_document" in names and n == 0:
        doc = {"title": "Rig report", "content": "# Findings\nAll checks passed."}
        return None, {"name": "create_word_document", "arguments": doc}
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
async def mstatus():  # what load_guard reads: a real ceiling, nothing loaded
    return {"models": [], "final_ceiling": 400e9, "current_model_memory": 0}


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


eg2 = FastAPI()
EG2_IDENTITY = {
    "model": "fake-eg2",
    "revision": "r1",
    "native_dim": 768,
    "dtype": "f32",
    "device": "cpu",
    "backend": "fake",
}


def _bow(text: str, dim: int) -> list[float]:
    v = [0.0] * dim
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % dim] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@eg2.get("/ready")
async def eg2_ready():
    return {"ready": True, "identity": EG2_IDENTITY}


@eg2.post("/embed")
async def eg2_embed(req: Request):
    b = await req.json()
    dim = int(b.get("dim") or 768)
    return {
        "embeddings": [
            _bow(t.get("text") or "" if isinstance(t, dict) else t, dim)
            for t in b.get("inputs") or []
        ],
        "model": EG2_IDENTITY["model"],
    }


@eg2.get("/vl/health")
async def vl_health():
    return {"status": "ok", "embed_model": "fake-vl", "embedding_dim": 768}


@eg2.get("/vl/ready")
async def vl_ready():
    return {"ready": True}


@eg2.post("/vl/embed_batch")
async def vl_embed_batch(req: Request):
    b = await req.json()
    return {"embeddings": [_bow(it.get("text") or "", 768) for it in b.get("items") or []]}


@eg2.post("/vl/rerank")
async def vl_rerank(req: Request):
    b = await req.json()
    n = min(int(b.get("top_n", 5)), len(b.get("candidates") or []))
    return {"results": [{"index": i, "score": 0.5} for i in range(n)]}


async def main():
    s1 = uvicorn.Server(uvicorn.Config(ol, host="127.0.0.1", port=OLLAMA_PORT, log_level="warning"))
    s2 = uvicorn.Server(uvicorn.Config(om, host="127.0.0.1", port=OMLX_PORT, log_level="warning"))
    servers = [s1.serve(), s2.serve()]
    if EG2_PORT:
        cfg = uvicorn.Config(eg2, host="127.0.0.1", port=EG2_PORT, log_level="warning")
        servers.append(uvicorn.Server(cfg).serve())
    await asyncio.gather(*servers)


asyncio.run(main())
