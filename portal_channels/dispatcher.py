"""portal_channels/dispatcher.py

Shared pipeline call logic for all channel adapters (Telegram, Slack, future).
Provides both sync and async variants for use in different event loop contexts.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
PIPELINE_TIMEOUT = float(os.environ.get("PIPELINE_TIMEOUT", "120"))

VALID_WORKSPACES = frozenset({
    "auto", "auto-coding", "auto-security", "auto-redteam", "auto-blueteam",
    "auto-creative", "auto-reasoning", "auto-documents", "auto-video",
    "auto-music", "auto-research", "auto-vision", "auto-data",
})


def _build_payload(messages: list[dict], workspace: str) -> dict:
    """Build the OpenAI-compatible chat completion payload."""
    return {
        "model": workspace,
        "messages": messages,
        "stream": False,
    }


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PIPELINE_API_KEY}"}


async def call_pipeline_async(
    text: str,
    workspace: str,
    history: list[dict] | None = None,
) -> str:
    """Call the Portal Pipeline asynchronously. Returns the assistant reply.

    Args:
        text:      The user's message text
        workspace: Workspace ID (e.g. 'auto', 'auto-coding')
        history:   Optional conversation history (list of role/content dicts)

    Returns:
        The assistant's reply string.

    Raises:
        httpx.HTTPStatusError: On non-2xx response from Pipeline
        httpx.RequestError:    On connection failure
    """
    messages = list(history or [])
    messages.append({"role": "user", "content": text})

    async with httpx.AsyncClient(timeout=PIPELINE_TIMEOUT) as client:
        resp = await client.post(
            f"{PIPELINE_URL}/v1/chat/completions",
            json=_build_payload(messages, workspace),
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def call_pipeline_sync(text: str, workspace: str) -> str:
    """Call the Portal Pipeline synchronously (for use in Slack bolt handlers).

    Args:
        text:      The user's message text
        workspace: Workspace ID

    Returns:
        The assistant's reply string.

    Raises:
        httpx.HTTPStatusError: On non-2xx response from Pipeline
        httpx.RequestError:    On connection failure
    """
    messages = [{"role": "user", "content": text}]
    with httpx.Client(timeout=PIPELINE_TIMEOUT) as client:
        resp = client.post(
            f"{PIPELINE_URL}/v1/chat/completions",
            json=_build_payload(messages, workspace),
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def is_valid_workspace(workspace: str) -> bool:
    """Return True if workspace is a recognised Portal workspace ID."""
    return workspace in VALID_WORKSPACES
