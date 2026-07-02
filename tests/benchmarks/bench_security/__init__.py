"""bench_security — auto-register ported oracles on import."""

from __future__ import annotations

import json
import time

import httpx

from .ability_port import register_ported_oracles

register_ported_oracles()


def _candidate_urls() -> list[str]:
    """Deduped, order-preserving list of pipeline URLs to try, host-side first."""
    import os

    url = os.environ.get("PIPELINE_URL", "http://localhost:9099")
    return list(dict.fromkeys([url, "http://host.docker.internal:9099", "http://localhost:9099"]))


def _pipeline_headers() -> dict[str, str]:
    import os

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _idle_timeout(workspace: str) -> float:
    return PER_WORKSPACE_TIMEOUT.get(workspace, min(REQUEST_TIMEOUT, 120.0))


def call_pipeline(workspace: str, prompt: str, **kwargs) -> tuple[str, float]:
    """Call a pipeline workspace and return (response_text, elapsed_seconds).

    Streams the response (stream=true) and applies a per-chunk idle timeout
    rather than a fixed cap on total response time. A non-streamed call gives
    httpx nothing to reset its read-timeout clock on — the backend buffers the
    whole completion before sending any bytes — so a fixed timeout there is
    indistinguishable from an overall duration cap and false-fails slow-but-
    progressing generations. Streaming makes the wait genuinely event-driven:
    it only times out when no token has arrived for `idle_timeout` seconds.
    """
    headers = _pipeline_headers()
    idle_timeout = _idle_timeout(workspace)
    t0 = time.monotonic()
    last_exc: Exception | None = None
    for candidate in _candidate_urls():
        try:
            parts: list[str] = []
            timeout = httpx.Timeout(idle_timeout, connect=5.0, write=10.0, pool=10.0)
            with httpx.stream(
                "POST",
                f"{candidate}/v1/chat/completions",
                headers=headers,
                json={
                    "model": workspace,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
                timeout=timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line == "data: [DONE]":
                        break
                    if line.startswith("data: "):
                        try:
                            delta = json.loads(line[6:])["choices"][0]["delta"]
                            content_piece = delta.get("content") or ""
                            if content_piece:
                                parts.append(content_piece)
                        except Exception:
                            pass
            return "".join(parts), time.monotonic() - t0
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            # The candidate host was reached — a fallback to a different host
            # can't fix a slow/erroring backend, and would only mask the real
            # cause with an unrelated connect failure. Report it directly.
            return f"[error: {e}]", time.monotonic() - t0
        except Exception as e:
            last_exc = e
            continue
    return f"[error: {last_exc}]", time.monotonic() - t0


def call_pipeline_exec(workspace: str, prompt: str, **kwargs) -> tuple[str, list, float]:
    """Call a pipeline workspace with tools enabled, return (content, tool_calls, elapsed).

    Sends exec_audit=true — the pipeline dispatches tool calls itself and emits
    a trailing SSE event (``type: exec_audit``) listing every tool call made
    (name + arguments), after the ``[DONE]`` marker. Mirrors the proven pattern
    in exec_chain.py's ``_call_via_pipeline``; tool_calls use the same
    ``{tool, arguments}`` schema expected by ``score_execution``.
    """
    headers = _pipeline_headers()
    idle_timeout = _idle_timeout(workspace)
    t0 = time.monotonic()
    last_exc: Exception | None = None
    for candidate in _candidate_urls():
        try:
            parts: list[str] = []
            tool_calls: list[dict] = []
            timeout = httpx.Timeout(idle_timeout, connect=5.0, write=10.0, pool=10.0)
            with httpx.stream(
                "POST",
                f"{candidate}/v1/chat/completions",
                headers=headers,
                json={
                    "model": workspace,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "exec_audit": True,
                },
                timeout=timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        # Don't break — the pipeline emits exec_audit after [DONE].
                        continue
                    try:
                        obj = json.loads(raw)
                    except Exception:
                        continue
                    if obj.get("type") == "exec_audit":
                        for tc in obj.get("tool_calls", []):
                            name = tc.get("tool", "")
                            args_raw = tc.get("arguments", "")
                            try:
                                args = (
                                    json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                                )
                            except Exception:
                                args = {"_raw": args_raw}
                            if name:
                                tool_calls.append({"tool": name, "arguments": args})
                        continue
                    delta = (obj.get("choices") or [{}])[0].get("delta", {})
                    content_piece = delta.get("content") or ""
                    if content_piece:
                        parts.append(content_piece)
            return "".join(parts), tool_calls, time.monotonic() - t0
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            return f"[error: {e}]", [], time.monotonic() - t0
        except Exception as e:
            last_exc = e
            continue
    return f"[error: {last_exc}]", [], time.monotonic() - t0


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
