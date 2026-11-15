"""The Portal Pipeline is the only model path: endpoint, workspace and key all come from env."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from ..judge import DEFAULT_KEY_ENV, JudgeClient, OpenAICompatibleClient, chat_completions_endpoint

DEFAULT_JUDGE_BACKEND = "omlx-general"


@dataclass(frozen=True)
class PreflightRejected:
    model: str
    backend: str
    status_code: int
    detail: str


class BackendPinnedClient:
    """Pin hunt reasoning requests to the backend selected for its parallel seat."""

    def __init__(self, inner: JudgeClient, backend: str) -> None:
        self.inner = inner
        self.backend = backend

    def complete(self, **request: Any) -> Mapping[str, Any]:
        request["portal_backend"] = self.backend
        return self.inner.complete(**request)


def preflight(client: JudgeClient, model: str) -> PreflightRejected | None:
    backend = str(getattr(client, "backend", DEFAULT_JUDGE_BACKEND))
    try:
        client.complete(
            model=model,
            messages=[{"role": "user", "content": "probe"}],
            tool_choice="none",
            max_tokens=1,
            temperature=0,
            stream=False,
        )
    except httpx.HTTPStatusError as exc:
        return PreflightRejected(model, backend, exc.response.status_code, exc.response.text[:200])
    except httpx.RequestError as exc:
        return PreflightRejected(model, backend, 0, str(exc)[:200])
    return None


def model_from_env() -> tuple[JudgeClient, str] | None:
    """Read the Pipeline model once; no URL, workspace or key literal lives in code."""
    url = os.environ.get("PORTAL_HUNT_JUDGE_URL")
    model = os.environ.get("PORTAL_HUNT_JUDGE_MODEL")
    if not url or not model:
        return None
    key_env = os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", DEFAULT_KEY_ENV)
    api_key = os.environ.get(key_env) if key_env else None
    backend = os.environ.get("PORTAL_HUNT_JUDGE_BACKEND", DEFAULT_JUDGE_BACKEND)
    client = OpenAICompatibleClient(chat_completions_endpoint(url), api_key)
    return BackendPinnedClient(client, backend), model


def model_requirement() -> str:
    return (
        "the Portal Pipeline workspace URL and workspace id are required: set "
        "PORTAL_HUNT_JUDGE_URL and PORTAL_HUNT_JUDGE_MODEL (and the key variable named "
        "by PORTAL_HUNT_JUDGE_KEY_ENV, default " + DEFAULT_KEY_ENV + "); "
        "PORTAL_HUNT_JUDGE_BACKEND defaults to " + DEFAULT_JUDGE_BACKEND
    )


def content_of(response: Mapping[str, Any]) -> str:
    """The assistant's text from one chat-completion response."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ""
    return str(message.get("content") or "")
