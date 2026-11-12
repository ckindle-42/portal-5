"""The Portal Pipeline is the only model path: endpoint, workspace and key all come from env."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from ..judge import DEFAULT_KEY_ENV, JudgeClient, OpenAICompatibleClient, chat_completions_endpoint


def model_from_env() -> tuple[JudgeClient, str] | None:
    """Read the Pipeline model once; no URL, workspace or key literal lives in code."""
    url = os.environ.get("PORTAL_HUNT_JUDGE_URL")
    model = os.environ.get("PORTAL_HUNT_JUDGE_MODEL")
    if not url or not model:
        return None
    key_env = os.environ.get("PORTAL_HUNT_JUDGE_KEY_ENV", DEFAULT_KEY_ENV)
    api_key = os.environ.get(key_env) if key_env else None
    return OpenAICompatibleClient(chat_completions_endpoint(url), api_key), model


def model_requirement() -> str:
    return (
        "the Portal Pipeline workspace URL and workspace id are required: set "
        "PORTAL_HUNT_JUDGE_URL and PORTAL_HUNT_JUDGE_MODEL (and the key variable named "
        "by PORTAL_HUNT_JUDGE_KEY_ENV, default " + DEFAULT_KEY_ENV + ")"
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
