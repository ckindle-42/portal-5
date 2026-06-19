"""Core TPS measurement: shared client, pipeline warmup, streaming bench loop.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py except:
  - the two lazy sys.path inserts for quality_signals/expected_models now
    resolve via PROJECT_ROOT (this file is one level deeper than the
    original), and
  - close_bench_client() is new — it replaces the `global _bench_client`
    teardown that previously lived in main().
"""

import time

import httpx

from tests.lib.stream_wait import IDLE_GAP_S as _IDLE_GAP_S  # idle-gap = primary stall signal

from .config import (
    _NOTHINK_PATTERNS,
    MATH_MAX_TOKENS,
    MAX_TOKENS,
    PIPELINE_API_KEY,
    PIPELINE_URL,
    PROJECT_ROOT,
    REASONING_MAX_TOKENS,
    REQUEST_TIMEOUT,
    WARMUP_TIMEOUT,
    _is_reasoning_model,
)

# ──Core benchmark ───────────────────────────────────────────────────────────


# P7-PERF: Module-level reusable httpx client for benchmarks
_bench_client: httpx.Client | None = None


def _get_bench_client() -> httpx.Client:
    """Get or create the shared benchmark httpx client."""
    global _bench_client
    if _bench_client is None:
        _bench_client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _bench_client


def _warmup_pipeline_model(
    model_id: str,
    timeout_s: float = WARMUP_TIMEOUT,
) -> bool:
    """Fire a 1-token request through the pipeline and block until it responds.

    The HTTP response IS the "model loaded" event — no timers, no sleep loops.
    Returns True when the pipeline replies (model is ready for timed runs).
    Returns False only if the pipeline never responds within timeout_s (failsafe).

    After this returns True, bench_tps should use INFERENCE_TIMEOUT (or
    PIPELINE_INACTIVITY_TIMEOUT for reasoning workspaces), not WARMUP_TIMEOUT,
    because the model is already loaded.
    """
    headers: dict[str, str] = {}
    if PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            with httpx.Client(timeout=min(remaining, 30.0)) as c:
                r = c.post(
                    f"{PIPELINE_URL}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if r.status_code == 200:
                    return True
                if r.status_code in (503, 502) and attempt < 5:
                    time.sleep(3)
                    continue
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            if time.time() < deadline:
                time.sleep(3)
            continue
        except Exception:
            break
    return False


def bench_tps(
    base_url: str,
    model: str,
    prompt: str,
    runs: int = 3,
    label: str = "",
    prompt_category: str = "",
    request_timeout: float = REQUEST_TIMEOUT,
) -> dict:
    """Benchmark TPS for a single model/endpoint. Returns summary dict.

    Uses streaming to capture time-to-first-token (TTFT) alongside TPS.

    P7-PERF: Reuses a shared httpx client to avoid TCP connection overhead
    between runs. This gives a more accurate measurement of actual inference
    time vs connection setup time.
    """
    import json as _json

    _reasoning = _is_reasoning_model(model, label)
    _nothink = any(p in model for p in _NOTHINK_PATTERNS)
    content = "/nothink\n" + prompt if _nothink else prompt
    # Math prompts (3 problems) require more tokens than the standard reasoning budget.
    _max_tokens = (
        MATH_MAX_TOKENS
        if prompt_category == "math"
        else (REASONING_MAX_TOKENS if _reasoning else MAX_TOKENS)
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
        "max_tokens": _max_tokens,
    }

    headers: dict[str, str] = {}
    if base_url == PIPELINE_URL and PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"

    client = _get_bench_client()
    run_results = []

    def _stream_one_run(run_num: int) -> dict:
        """Execute one streaming inference run and return its result dict."""
        t0 = time.perf_counter()
        t_first_token: float | None = None
        completion_tokens = 0
        prompt_tokens = 0
        response_text = ""
        reasoning_text = ""
        response_model = ""

        try:
            # Idle gap (read) is the primary stall signal; request_timeout becomes the
            # overall connect/pool bound. A model streaming steadily never trips `read`.
            _stream_timeout = httpx.Timeout(
                connect=min(request_timeout, 10.0),
                read=_IDLE_GAP_S,
                write=10.0,
                pool=10.0,
            )
            _ceiling = time.perf_counter() + request_timeout
            with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=_stream_timeout,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read()[:200].decode(errors="replace")
                    return {
                        "run": run_num,
                        "error": f"HTTP {resp.status_code}: {body[:80]}",
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                    }
                for raw_line in resp.iter_lines():
                    if time.perf_counter() > _ceiling:
                        # Overall ceiling (last resort) — healthy streams never reach it.
                        break
                    line = (
                        raw_line.strip()
                        if isinstance(raw_line, str)
                        else raw_line.decode(errors="replace").strip()
                    )
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = _json.loads(data_str)
                    except Exception:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    chunk_text = delta.get("content") or ""
                    reasoning_chunk = delta.get("reasoning") or ""
                    # Capture tool_calls delta: workspaces with tools (auto-agentic,
                    # tools-specialist) may respond with function invocations instead of
                    # text content.  Accumulate function name + argument fragments into
                    # response_text so quality scoring sees the code and runs_success
                    # isn't falsely zeroed by an "empty response (0 tokens)" error.
                    for tc in delta.get("tool_calls") or []:
                        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                        chunk_text += (fn.get("name") or "") + (fn.get("arguments") or "")
                    if (chunk_text or reasoning_chunk) and t_first_token is None:
                        t_first_token = time.perf_counter()
                    response_text += chunk_text
                    reasoning_text += reasoning_chunk
                    if not response_model:
                        response_model = obj.get("model", "")
                    # Usage may appear in the final chunk
                    usage = obj.get("usage") or {}
                    if usage.get("completion_tokens"):
                        completion_tokens = usage["completion_tokens"]
                    if usage.get("prompt_tokens"):
                        prompt_tokens = usage["prompt_tokens"]

        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            return {
                "run": run_num,
                "error": str(e)[:100],
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }
        except httpx.ReadTimeout:
            return {"run": run_num, "error": "timeout", "elapsed_s": request_timeout}
        except Exception as e:
            return {
                "run": run_num,
                "error": str(e)[:100],
                "elapsed_s": round(time.perf_counter() - t0, 2),
            }

        elapsed = time.perf_counter() - t0
        # Fallback token count: estimate from response + reasoning text if server didn't emit usage.
        # Reasoning tokens (delta.reasoning) count toward TPS — they represent real generation work.
        combined_text = response_text + (" " + reasoning_text if reasoning_text else "")
        if completion_tokens == 0 and combined_text.strip():
            completion_tokens = max(1, len(combined_text.split()))
        # Empty response: server returned HTTP 200 and a valid stream, but zero
        # content and zero reasoning tokens.  Treat as a failure so runs_success
        # accurately reflects whether the model produced usable output.
        if completion_tokens == 0:
            return {
                "run": run_num,
                "error": "empty response (0 tokens)",
                "elapsed_s": round(elapsed, 2),
            }
        tps = completion_tokens / elapsed if elapsed > 0 else 0.0
        ttft = round(t_first_token - t0, 3) if t_first_token is not None else None

        result: dict = {
            "run": run_num,
            "elapsed_s": round(elapsed, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tps": round(tps, 1),
            "time_to_first_token_s": ttft,
            "response_model": response_model,
            "response_text": response_text,
        }
        if reasoning_text:
            result["reasoning_text"] = reasoning_text
        return result

    def _run_with_empty_retry(run_num: int) -> dict:
        # A clean HTTP 200 stream that yields zero content/reasoning tokens is an
        # intermittent transient (degenerate empty completion), NOT a model failure:
        # adjacent runs of the same cell return 110-125 tokens (see
        # bench_tps_20260619T031107Z.json auto-coding cells). Retry ONCE before
        # recording the failure. Timeouts ("timeout") and HTTP errors ("HTTP 5xx")
        # are deliberately NOT retried here — they have distinct error strings and
        # represent genuine load/crash conditions, not transient empties.
        result = _stream_one_run(run_num)
        if result.get("error") == "empty response (0 tokens)":
            result = _stream_one_run(run_num)
        return result

    for run_num in range(1, runs + 1):
        result = _run_with_empty_retry(run_num)
        run_results.append(result)

    successful = [r for r in run_results if "tps" in r]
    if successful:
        import statistics  # noqa: PLC0415

        tps_vals = [r["tps"] for r in successful]
        avg_tps = round(sum(tps_vals) / len(tps_vals), 1)
        min_tps = min(tps_vals)
        max_tps = max(tps_vals)
        # Sample stddev requires ≥2 runs. With one run, jitter is undefined.
        stddev_tps = round(statistics.stdev(tps_vals), 2) if len(tps_vals) > 1 else None
        # Coefficient of variation: stddev / mean. Dimensionless — comparable
        # across models with different absolute TPS. <0.05 tight, 0.05-0.15
        # normal, >0.15 unstable (warmup not done, memory pressure, etc.)
        cv = round(stddev_tps / avg_tps, 3) if (stddev_tps is not None and avg_tps > 0) else None
        avg_tokens = round(sum(r["completion_tokens"] for r in successful) / len(successful))
        avg_elapsed = round(sum(r["elapsed_s"] for r in successful) / len(successful), 2)
        ttft_vals = [
            r["time_to_first_token_s"]
            for r in successful
            if r.get("time_to_first_token_s") is not None
        ]
        avg_ttft = round(sum(ttft_vals) / len(ttft_vals), 3) if ttft_vals else None
    else:
        avg_tps = min_tps = max_tps = 0.0
        stddev_tps = None
        cv = None
        avg_tokens = 0
        avg_elapsed = 0.0
        avg_ttft = None

    # Capture the actual model returned by the API (pipeline routing may differ)
    routed_model = ""
    last_response_text = ""
    if successful:
        last_ok = successful[-1]
        routed_model = last_ok.get("response_model", "")
        last_response_text = last_ok.get("response_text", "") or last_ok.get("reasoning_text", "")

    # Quality scoring: measure signal coverage for this prompt category
    try:
        import sys as _sys

        # bench/ is one level deeper than the original bench_tps.py location —
        # point at tests/ explicitly via PROJECT_ROOT.
        _sys.path.insert(0, str(PROJECT_ROOT / "tests"))
        from quality_signals import quality_score as _qs

        qs = round(_qs(prompt_category, last_response_text), 2) if last_response_text else 0.0
    except Exception:
        qs = 1.0  # Don't penalize if signals module unavailable

    tps_quality = round(avg_tps * qs, 1)

    expected_match: bool | None = None
    expected_detail = ""
    try:
        import sys as _sys

        _sys.path.insert(0, str(PROJECT_ROOT / "tests"))
        from expected_models import (
            expected_model_keys,
            model_matches_expected,
        )

        if routed_model:
            if base_url == PIPELINE_URL:
                keys, src = expected_model_keys(model)
                if keys:
                    expected_match = model_matches_expected(routed_model, keys)
                    expected_detail = src
            else:
                requested_basename = model.split("/")[-1].lower()
                expected_match = requested_basename in routed_model.lower()
                expected_detail = f"requested {requested_basename}"
    except Exception as e:
        expected_detail = f"expected-check error: {e}"

    return {
        "model": model,
        "label": label,
        "runs_total": runs,
        "runs_success": len(successful),
        "avg_tps": avg_tps,
        "min_tps": min_tps,
        "max_tps": max_tps,
        "stddev_tps": stddev_tps,  # None if <2 successful runs
        "cv": cv,  # coefficient of variation; None if avg_tps==0
        "avg_completion_tokens": avg_tokens,
        "avg_elapsed_s": avg_elapsed,
        "avg_ttft_s": avg_ttft,
        "routed_model": routed_model,
        "prompt_category": prompt_category,
        "quality_score": qs,
        "tps_quality": tps_quality,
        "reasoning_mode": _reasoning,
        "expected_model_match": expected_match,
        "expected_model_detail": expected_detail,
        "runs": run_results,
    }


def close_bench_client() -> None:
    """Close and reset the shared benchmark client (called from main's finally)."""
    global _bench_client
    if _bench_client is not None:
        _bench_client.close()
        _bench_client = None
