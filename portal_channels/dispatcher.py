"""portal_channels/dispatcher.py

Shared pipeline call logic for all channel adapters (Telegram, Slack, future).
Provides both sync and async variants for use in different event loop contexts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://localhost:9099")
PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY") or "portal-pipeline"
if PIPELINE_API_KEY == "portal-pipeline" and not os.environ.get("PIPELINE_API_KEY"):
    import logging as _log

    _log.getLogger(__name__).warning(
        "PIPELINE_API_KEY not set — using insecure default. Set in .env."
    )
PIPELINE_TIMEOUT = float(os.environ.get("PIPELINE_TIMEOUT", "120"))
PIPELINE_RETRIES = int(os.environ.get("PIPELINE_RETRIES", "3"))
PIPELINE_RETRY_BASE = float(os.environ.get("PIPELINE_RETRY_BASE", "1.0"))

VALID_WORKSPACES = frozenset(
    {
        "auto",
        "auto-agentic",
        "auto-coding",
        "auto-spl",
        "auto-security",
        "auto-redteam",
        "auto-blueteam",
        "auto-creative",
        "auto-reasoning",
        "auto-documents",
        "auto-video",
        "auto-music",
        "auto-research",
        "auto-vision",
        "auto-data",
        "auto-compliance",
        "auto-mistral",
        "auto-math",
        # Coding capability benchmark workspaces (user-selected only)
        "bench-devstral",
        "bench-qwen3-coder-next",
        "bench-qwen3-coder-30b",
        "bench-llama33-70b",
        "bench-phi4",
        "bench-phi4-reasoning",
        "bench-dolphin8b",
        "bench-glm",
        "bench-gptoss",
    }
)


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
    """Call the Portal Pipeline asynchronously with retry on transient errors.

    Retries up to PIPELINE_RETRIES times with exponential backoff.
    Retries on: connection errors, timeouts, 5xx responses.
    Does NOT retry on: 4xx client errors, authentication failures.
    """
    messages = list(history or [])
    messages.append({"role": "user", "content": text})
    payload = _build_payload(messages, workspace)

    last_exc: Exception | None = None
    for attempt in range(PIPELINE_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=PIPELINE_TIMEOUT) as client:
                resp = await client.post(
                    f"{PIPELINE_URL}/v1/chat/completions",
                    json=payload,
                    headers=_auth_headers(),
                )
                if resp.status_code >= 500 and attempt < PIPELINE_RETRIES - 1:
                    wait = PIPELINE_RETRY_BASE * (2**attempt)
                    logger.warning(
                        "Pipeline returned %s on attempt %d/%d — retrying in %.1fs",
                        resp.status_code,
                        attempt + 1,
                        PIPELINE_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return str(resp.json()["choices"][0]["message"]["content"])

        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < PIPELINE_RETRIES - 1:
                wait = PIPELINE_RETRY_BASE * (2**attempt)
                logger.warning(
                    "Pipeline connection error on attempt %d/%d — retrying in %.1fs: %s",
                    attempt + 1,
                    PIPELINE_RETRIES,
                    wait,
                    e,
                )
                await asyncio.sleep(wait)
            else:
                raise

    raise last_exc or RuntimeError("Pipeline call failed after all retries")


def call_pipeline_sync(text: str, workspace: str) -> str:
    """Call the Portal Pipeline synchronously with retry on transient errors.

    Used by Slack bolt handlers which run in a thread pool.
    """
    messages = [{"role": "user", "content": text}]
    payload = _build_payload(messages, workspace)

    last_exc: Exception | None = None
    for attempt in range(PIPELINE_RETRIES):
        try:
            with httpx.Client(timeout=PIPELINE_TIMEOUT) as client:
                resp = client.post(
                    f"{PIPELINE_URL}/v1/chat/completions",
                    json=payload,
                    headers=_auth_headers(),
                )
                if resp.status_code >= 500 and attempt < PIPELINE_RETRIES - 1:
                    wait = PIPELINE_RETRY_BASE * (2**attempt)
                    logger.warning(
                        "Pipeline returned %s on attempt %d/%d — retrying in %.1fs",
                        resp.status_code,
                        attempt + 1,
                        PIPELINE_RETRIES,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return str(resp.json()["choices"][0]["message"]["content"])

        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < PIPELINE_RETRIES - 1:
                wait = PIPELINE_RETRY_BASE * (2**attempt)
                logger.warning(
                    "Pipeline connection error on attempt %d/%d — retrying in %.1fs: %s",
                    attempt + 1,
                    PIPELINE_RETRIES,
                    wait,
                    e,
                )
                time.sleep(wait)
            else:
                raise

    raise last_exc or RuntimeError("Pipeline call failed after all retries")


def is_valid_workspace(workspace: str) -> bool:
    """Return True if workspace is a recognised Portal workspace ID."""
    return workspace in VALID_WORKSPACES
