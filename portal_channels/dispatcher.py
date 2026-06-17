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
        "auto-daily",
        "auto-spl",
        "auto-security",
        "auto-redteam",
        "auto-purpleteam",
        "auto-purpleteam-deep",
        "auto-purpleteam-exec",
        "auto-pentest",
        "bench-vibethinker-3b",
        "bench-vibethinker-3b-ablated",
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
        "auto-phi4",
        "auto-audio",
        # Coding capability benchmark workspaces (user-selected only)
        "bench-qwen3-coder-next",
        "bench-qwen3-coder-30b",
        "bench-llama33-70b",
        "bench-phi4",
        "bench-phi4-reasoning",
        "bench-dolphin8b",
        "bench-glm",
        "bench-gptoss",
        "bench-laguna",
        "bench-granite41-8b",
        "bench-granite41-30b",
        "bench-qwen35-abliterated",
        # V6 candidate benches (TASK_MODEL_REFRESH_V6)
        "bench-qwen36-27b",
        "bench-qwen36-35b-a3b",
        "bench-omnicoder2",
        "bench-negentropy",
        "bench-olmo3-32b",
        # May 2026 additions (TASK_BENCH_COVERAGE_V1)
        "bench-nemotron-omni",
        # V7 adds (PHASE_PLAN_MODEL_REFRESH_V7_V2)
        "bench-olmocr2",
        "bench-nanonets-ocr2",
        "bench-lfm2-moe",
        "bench-foundation-sec",
        "bench-toolace25",
        # V7 catalog refresh (TASK_MODEL_REFRESH_V7)
        "bench-voxtral-realtime",
        "bench-voxtral-tts",
        "bench-granite-speech",
        "bench-qwen36-27b-ud",
        "bench-qwen36-35b-a3b-ud",
        "bench-qwen36-27b-mtp",
        # V8 quant-trueup (TASK_QUANT_TRUEUP_V1)
        "bench-qwen36-35b-a3b-dwq",
        "bench-qwen36-27b-optiq",
        "bench-gemma4-26b-optiq",
        "bench-huihui-qwen36-27b",
        "bench-huihui-qwen36-35b-a3b",
        # TASK_MODEL_FLEET_REFRESH_V2 Phase 4 adds
        "bench-qwen36-hauhaucs",
        "bench-gemma4-12b",
        "bench-phi4-mini",
        "bench-gemma4-e4b",
        # V8 model refresh (TASK_MODEL_REFRESH_V8)
        "bench-gemma4-e2b",
        "bench-gemma4-e4b-qat",
        "bench-gemma4-26b-qat",
        "bench-gemma4-31b-qat",
        "bench-phi4-mini-reasoning",
        "bench-lfm25-8b",
        "bench-starcoder2",
        "bench-devstral-small-2",
        "bench-mistral-small32",
        "bench-r1-0528-qwen3-8b",
        "bench-harness1",
        "bench-nex-n2-mini",
        # V8 uncensored candidates (TASK_MODEL_REFRESH_V8_UNCENSORED)
        "bench-lfm25-8b-uncensored",
        "bench-r1-0528-abliterated",
        "bench-qwen3-coder-next-abliterated",
        # V9 candidate benches (TASK_MODEL_EVAL_V9_CANDIDATES)
        "bench-qwopus-coder-mtp",
        "bench-gemma4-12b-coder",
        "bench-deepseek-coder-v2",
        # June 2026 new production workspaces
        "auto-bigfix",
        "auto-cad",
        # June 2026 bench candidates
        "bench-gemma4-31b-crack",
        "bench-devstral",
        "bench-fastcontext",
        "bench-magistral",
        "bench-apriel-nemotron",
        "bench-qwopus-coder-mtp-v2",
        "bench-c3d-v0",
        "bench-wrn8b",
        "bench-lily-cybersec",
        "bench-dolphin-r1",
        "bench-supergemma4-sec",
        "bench-xploiter-pentester",
        # June 2026 security candidate round 2
        "bench-foundation-sec-abliterated",
        "bench-sylink",
        "bench-dolphin3-cyber",
        # June 2026 new production security workspaces
        "auto-redteam-deep",
        # June 2026 AppSec bench candidate
        "bench-vulnllm-r7b",
        # June 2026 diffusion research bench
        "bench-diffusiongemma",
        # May 2026 specialist MLX production workspaces
        "tools-specialist",
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
