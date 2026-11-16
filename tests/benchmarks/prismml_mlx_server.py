#!/usr/bin/env python3
"""Small local OpenAI-compatible adapter for PrismML MLX model packs.

The v2 pack's quickstart is intentionally a one-shot example, not a server.
This adapter follows its loader, Jinja template, sampler, and stop-token path,
then exposes the same single-flight API shape the h2h harness uses elsewhere.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
_PACK: Path
_MODEL: Any
_MODEL_API: str
_TOKENIZER: Any
_CONFIG: dict
_GENERATION: dict
_CHAT_TEMPLATE: str
_CTX: int


def _json_file(name: str, default: dict) -> dict:
    path = _PACK / name
    return json.loads(path.read_text()) if path.is_file() else default


def _render(messages: list[dict], enable_thinking: bool, tools: list[dict] | None) -> str:
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    source = _CHAT_TEMPLATE
    return (
        ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
        .from_string(source)
        .render(
            messages=messages,
            tools=tools,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
    )


def _load_pack(path: Path) -> None:
    global _PACK, _MODEL, _MODEL_API, _TOKENIZER, _CONFIG, _GENERATION, _CHAT_TEMPLATE
    _PACK = path.resolve()
    _CONFIG = _json_file("config.json", {})
    _GENERATION = _json_file("generation_config.json", {})
    model_type = _CONFIG.get("model_type", "")
    if model_type == "prism_hadamard_qwen35":
        import sys

        sys.path.insert(0, str(_PACK / "runtime"))
        if _CONFIG.get("components", {}).get("vision"):
            from vision_artifact import load_vl_model

            packed_model, _, _ = load_vl_model(_PACK, load_processor=False)
            _MODEL = packed_model.language_model
            _MODEL_API = "packed_language"
        else:
            from artifact import load_model

            _MODEL, _ = load_model(_PACK)
            _MODEL_API = "packed_language"
    else:
        from mlx_lm import load

        _MODEL, _ = load(str(_PACK))
        _MODEL_API = "mlx_lm"

    from tokenizers import Tokenizer

    _TOKENIZER = Tokenizer.from_file(str(_PACK / "tokenizer.json"))
    _CHAT_TEMPLATE = (
        (_PACK / "chat_template.jinja").read_text()
        if (_PACK / "chat_template.jinja").is_file()
        else _json_file("tokenizer_config.json", {}).get("chat_template", "")
    )


def _make_cache():
    if _MODEL_API == "packed_language":
        return _MODEL.make_cache()
    from mlx_lm.models.cache import make_prompt_cache

    return make_prompt_cache(_MODEL)


def _next_logits(tokens, cache):
    if _MODEL_API == "mlx_lm":
        return _MODEL(tokens, cache=cache)[:, -1, :]
    return _MODEL.lm_head(_MODEL.model(tokens, cache=cache)[:, -1:, :])[:, -1, :]


def _stop_ids() -> set[int]:
    configured = _GENERATION.get("eos_token_id")
    ids = set(
        configured if isinstance(configured, list) else [] if configured is None else [configured]
    )
    ids.update(
        token
        for token in (
            _TOKENIZER.token_to_id("<|im_end|>"),
            _TOKENIZER.token_to_id("<|endoftext|>"),
            _TOKENIZER.token_to_id("<|fim_suffix|>"),
        )
        if token is not None
    )
    return ids


def _generate(payload: dict):
    import mlx.core as mx
    from mlx_lm.sample_utils import make_logits_processors, make_sampler

    kwargs = payload.get("chat_template_kwargs") or {}
    prompt = _render(
        payload.get("messages") or [],
        enable_thinking=bool(kwargs.get("enable_thinking", payload.get("think", True))),
        tools=payload.get("tools"),
    )
    ids = _TOKENIZER.encode(prompt, add_special_tokens=False).ids
    limit = int(payload.get("max_tokens") or 256)
    if len(ids) + limit > int(payload.get("max_context") or _CTX):
        raise ValueError(f"prompt ({len(ids)} tokens) plus completion ({limit}) exceeds context")
    seed = payload.get("seed")
    if seed is not None:
        mx.random.seed(int(seed))

    temperature = float(payload.get("temperature", _GENERATION.get("temperature", 1.0)))
    top_p = float(payload.get("top_p", _GENERATION.get("top_p", 0.95)))
    top_k = int(payload.get("top_k", _GENERATION.get("top_k", 20)))
    min_p = float(payload.get("min_p", _GENERATION.get("min_p", 0.0)))
    sampler = make_sampler(temp=temperature, top_p=top_p, top_k=top_k, min_p=min_p)
    processors = make_logits_processors(
        repetition_penalty=payload.get("repetition_penalty", _GENERATION.get("repetition_penalty"))
    )
    cache = _make_cache()
    x = mx.array([ids])
    generated: list[int] = []
    last_text = ""
    for _ in range(limit):
        logits = _next_logits(x, cache)
        if payload.get("presence_penalty"):
            for token in set(generated):
                logits[:, token] -= float(payload["presence_penalty"])
        for processor in processors:
            logits = processor(mx.array(generated), logits)
        x = sampler(logits)[:, None]
        mx.eval(x)
        token = int(x.item())
        if token in _stop_ids():
            break
        generated.append(token)
        decoded = _TOKENIZER.decode(generated)
        delta = decoded[len(last_text) :]
        last_text = decoded
        if delta:
            yield delta
    yield {"usage": {"prompt_tokens": len(ids), "completion_tokens": len(generated)}}


def _tool_calls(text: str) -> list[dict]:
    calls = []
    for number, match in enumerate(
        re.finditer(
            r"<tool_call>\s*<function=([\w.-]+)>(.*?)</function>\s*</tool_call>", text, re.S
        )
    ):
        params = {
            key: value.strip()
            for key, value in re.findall(
                r"<parameter=([\w.-]+)>(.*?)</parameter>", match.group(2), re.S
            )
        }
        calls.append(
            {
                "id": f"call_{number}_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": match.group(1), "arguments": json.dumps(params)},
            }
        )
    return calls


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/models")
def models() -> dict:
    name = _PACK.name
    return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "prismml"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    request_id = f"chatcmpl-{uuid.uuid4().hex}"
    model_name = _PACK.name
    is_stream = bool(payload.get("stream"))

    if is_stream:

        async def events():
            # MLX streams are thread-local. The pack is loaded on Uvicorn's
            # event-loop thread, so keep generation there instead of letting
            # Starlette move a synchronous iterator into its worker pool.
            usage = {}
            for piece in _generate(payload):
                if isinstance(piece, dict):
                    usage.update(piece.get("usage") or {})
                    continue
                event = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(event)}\n\n"
            usage_event = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [],
                "usage": usage,
            }
            yield f"data: {json.dumps(usage_event)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    pieces, usage = [], {}
    try:
        for piece in _generate(payload):
            if isinstance(piece, dict):
                usage = piece["usage"]
            else:
                pieces.append(piece)
    except ValueError as exc:
        return JSONResponse(
            {"error": {"message": str(exc), "type": "invalid_request_error"}}, status_code=400
        )
    content = "".join(pieces)
    calls = _tool_calls(content) if payload.get("tools") else []
    message = {"role": "assistant", "content": content, "tool_calls": calls or None}
    finish = "tool_calls" if calls else "stop"
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage,
    }


def main() -> None:
    global _CTX
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--ctx", type=int, default=32768)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("PrismML MLX probe server must bind to loopback")
    _load_pack(args.model_dir)
    _CTX = args.ctx
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
