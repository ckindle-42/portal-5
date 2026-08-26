"""OpenAI-compatible model socket. The model is interchangeable; extra_body carries num_ctx."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = "local"
    model: str = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M"
    temperature: float = 0.2
    max_tokens: int = 4096
    extra_body: dict[str, Any] = field(default_factory=dict)
    timeout: float = 600.0


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def complete(
    config: LLMConfig, messages: list[dict], tools: list[dict] | None = None
) -> LLMResponse:
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}
    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if config.extra_body:
        body.update(config.extra_body)

    with httpx.Client(timeout=config.timeout) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    message = data.get("choices", [{}])[0].get("message", {})
    parsed_calls: list[ToolCall] = []
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        args_raw = fn.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
        else:
            args = args_raw
        parsed_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))

    return LLMResponse(
        content=message.get("content"),
        tool_calls=parsed_calls,
        raw=data,
        usage=data.get("usage", {}),
    )
