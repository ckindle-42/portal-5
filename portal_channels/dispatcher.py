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
        "auto-coding-agentic",
        "auto-glm",
        "auto-glm-thinking",
        "auto-gemma-fast",
        "auto-gemma-e4b",
        "auto-devstral",
        "auto-gemma-vision",
        "auto-daily",
        "auto-spl",
        "auto-security",
        "auto-redteam",
        "auto-purpleteam",
        "auto-purpleteam-deep",
        "auto-purpleteam-exec",
        "auto-pentest",
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
        "bench-glm",
        "bench-glm-reap",
        "bench-glm-z1-rumination",
        "bench-gptoss",
        "bench-laguna",
        "bench-granite41-8b",
        "bench-granite41-30b",
        "bench-qwen35-abliterated",
        # V6 candidate benches (TASK_MODEL_REFRESH_V6)
        "bench-qwen36-27b",
        "bench-qwen36-35b-a3b",
        "bench-omnicoder2",
        # May 2026 additions (TASK_BENCH_COVERAGE_V1)
        # V7 adds (PHASE_PLAN_MODEL_REFRESH_V7_V2)
        # V7 catalog refresh (TASK_MODEL_REFRESH_V7)
        "bench-qwen36-27b-ud",
        "bench-qwen36-35b-a3b-ud",
        "bench-qwen36-27b-mtp",
        # V8 quant-trueup (TASK_QUANT_TRUEUP_V1)
        "bench-qwen36-27b-optiq",
        "bench-gemma4-26b-optiq",
        "bench-huihui-qwen36-27b",
        "bench-huihui-qwen36-35b-a3b",
        # TASK_MODEL_FLEET_REFRESH_V2 Phase 4 adds
        "bench-qwen36-hauhaucs",
        "bench-gemma4-12b",
        "bench-gemma4-e4b",
        # V8 model refresh (TASK_MODEL_REFRESH_V8)
        "bench-gemma4-e2b",
        "bench-gemma4-e4b-qat",
        "bench-gemma4-26b-qat",
        "bench-gemma4-31b-qat",
        "bench-lfm25-8b",
        "bench-devstral-small-2",
        "bench-nex-n2-mini",
        # V8 uncensored candidates (TASK_MODEL_REFRESH_V8_UNCENSORED)
        "bench-lfm25-8b-uncensored",
        "bench-qwen3-coder-next-abliterated",
        # V9 candidate benches (TASK_MODEL_EVAL_V9_CANDIDATES)
        "bench-qwable-35b",
        "bench-e2b-pentest",
        # June 2026 new production workspaces
        "auto-bigfix",
        "auto-cad",
        # June 2026 bench candidates
        "bench-gemma4-31b-crack",
        "bench-devstral",
        "bench-fastcontext",
        "bench-qwopus-coder-mtp-v2",
        "bench-supergemma4-sec",
        # June 2026 security candidate round 2
        "bench-sylink",
        # June 2026 new production security workspaces
        "auto-redteam-deep",
        # June 2026 uncensored coding + stranded-model lanes (TASK_CODING_UNCENSORED_LANES_V1)
        "auto-coding-uncensored",
        "auto-coding-uncensored-agentic",
        "auto-extract-uncensored",
        "auto-general-uncensored",
        "auto-security-uncensored",
        # June 2026 AppSec bench candidate
        "bench-vulnllm-r7b",
        # June 2026 diffusion research bench
        # May 2026 specialist MLX production workspaces
        "tools-specialist",
        # June 2026 security bench exec-chain workspaces (pipeline-routed)
        "bench-exec-recon",
        "bench-exec-reasoning",
        "bench-exec-exploit",
        # TASK_LFM_AGENTWORLD_ROUTER_V1
        "bench-lfm-micro-230m",
        "bench-lfm-micro-350m",
        "bench-lfm-micro-1p2b",
        "bench-agentworld",
        # TASK_MODEL_EVAL_V10_CANDIDATES
        "bench-ornith-9b",
        "bench-ornith-35b",
        "bench-north-mini-code",
        "bench-qwythos-9b",
        "bench-glm47f-claude-distill",
        "auto-agentic-lite",
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
