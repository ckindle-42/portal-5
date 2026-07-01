"""bench_security — auto-register ported oracles on import."""

from __future__ import annotations

import time

import httpx

from .ability_port import register_ported_oracles

register_ported_oracles()


def call_pipeline(workspace: str, prompt: str, **kwargs) -> tuple[str, float]:
    """Call a pipeline workspace and return (response_text, elapsed_seconds)."""
    import os

    url = os.environ.get("PIPELINE_URL", "http://localhost:9099")
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.monotonic()
    try:
        r = httpx.post(
            f"{url}/v1/chat/completions",
            headers=headers,
            json={
                "model": workspace,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=120.0,
        )
        data = r.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content, time.monotonic() - t0
    except Exception:
        # Try host.docker.internal as fallback
        try:
            r = httpx.post(
                "http://host.docker.internal:9099/v1/chat/completions",
                headers=headers,
                json={
                    "model": workspace,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=120.0,
            )
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content, time.monotonic() - t0
        except Exception as e:
            return f"[error: {e}]", time.monotonic() - t0


def call_pipeline_exec(workspace: str, prompt: str, **kwargs) -> tuple[str, list, float]:
    """Call a pipeline workspace with tools enabled, return (content, tool_calls, elapsed)."""
    content, elapsed = call_pipeline(workspace, prompt, **kwargs)
    # Tool calls would come from streaming — for now return empty
    return content, [], elapsed


def call_theory_direct(model: str, prompt: str, **kwargs) -> tuple[str, float]:
    """Call Ollama directly for theory scoring, return (content, elapsed)."""
    import os

    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    t0 = time.monotonic()
    try:
        r = httpx.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=120.0,
        )
        data = r.json()
        content = data.get("message", {}).get("content", "")
        return content, time.monotonic() - t0
    except Exception as e:
        return f"[error: {e}]", time.monotonic() - t0


# Re-export public API for __main__ entry point and backward-compat shim
from ._config import BenchConfig  # noqa: F401, E402
from ._data import (  # noqa: F401, E402
    CHAIN_INHERITANCE,
    DEFAULT_WORKSPACES,
    DISCLAIMER_PATTERNS,
    EXEC_SEQUENCES,
    EXECUTION_WORKSPACES,
    MITRE_PATTERN,
    PER_WORKSPACE_TIMEOUT,
    PIPELINE_API_KEY,
    PIPELINE_URL,
    PROMPT_MAX_TOKENS,
    PROMPTS,
    REQUEST_TIMEOUT,
    RESULTS_DIR,
)
from .cli import main  # noqa: F401, E402
from .scoring import (  # noqa: F401, E402
    score_execution,
    score_handoff_quality,
    score_response,
)
