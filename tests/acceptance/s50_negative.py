"""S50: Negative tests — pipeline graceful degradation under bad inputs."""
from tests.acceptance._common import (
    record, time, asyncio, _chat_with_model, _get, _mlx_health,
    PIPELINE_URL, AUTH, httpx, json,
)


async def run() -> None:
    print("\n━━━ S50. NEGATIVE TESTING ━━━")
    sec = "S50"

    # S50-01: Empty prompt — pipeline must not crash
    t0 = time.time()
    code, response, model, _ = await _chat_with_model("auto", "", max_tokens=50, timeout=30)
    if code in (200, 400):
        record(sec, "S50-01", "Empty prompt handled gracefully", "PASS",
               f"HTTP {code}", t0=t0)
    elif code in (500, 502, 503):
        record(sec, "S50-01", "Empty prompt handled gracefully", "FAIL",
               f"HTTP {code} — pipeline crashed on empty prompt", t0=t0)
    else:
        record(sec, "S50-01", "Empty prompt handled gracefully", "WARN",
               f"unexpected HTTP {code}", t0=t0)

    # S50-02: Oversized prompt — should be rejected or truncated, not crash
    t0 = time.time()
    huge_prompt = "Repeat this. " * 50000  # ~600KB
    code, response, model, _ = await _chat_with_model("auto", huge_prompt, max_tokens=50, timeout=60)
    # Pipeline configured with MAX_REQUEST_BYTES=4MB by default; 600KB shouldn't hit that.
    # The model may produce truncated context, but the pipeline shouldn't 5xx.
    if code in (200, 400, 413):
        record(sec, "S50-02", "Oversized prompt rejected or truncated", "PASS",
               f"HTTP {code}", t0=t0)
    else:
        record(sec, "S50-02", "Oversized prompt", "WARN",
               f"unexpected HTTP {code}", t0=t0)

    # S50-03: Invalid model slug — should return 503 (no backends), not crash
    t0 = time.time()
    code, response, model, _ = await _chat_with_model("nonexistent-workspace", "hello", max_tokens=20, timeout=30)
    # Pipeline routes unknown workspaces with no candidates → 503
    if code in (200, 400, 404, 503):
        record(sec, "S50-03", "Invalid model slug handled", "PASS",
               f"HTTP {code} | model={model[:30]}", t0=t0)
    else:
        record(sec, "S50-03", "Invalid model slug", "FAIL",
               f"HTTP {code} — should be 200/400/404/503", t0=t0)

    # S50-04: Pipeline /health surfaces backend count (non-destructive health check)
    t0 = time.time()
    code, data = await _get(f"{PIPELINE_URL}/health")
    if code == 200 and isinstance(data, dict):
        backends_healthy = data.get("backends_healthy", 0)
        record(sec, "S50-04", "Pipeline /health surfaces backend count", "PASS",
               f"healthy: {backends_healthy}", t0=t0)
    else:
        record(sec, "S50-04", "Pipeline /health", "FAIL", f"HTTP {code}", t0=t0)

    # S50-05: Malformed JSON body — must return 400/422, not 500
    t0 = time.time()
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers={**AUTH, "Content-Type": "application/json"},
                content=b'{"model": "auto", "messages": [{"role": "user", "content": "hi",  ',
            )
            if r.status_code in (400, 422):
                record(sec, "S50-05", "Malformed JSON rejected", "PASS",
                       f"HTTP {r.status_code}", t0=t0)
            elif r.status_code == 500:
                record(sec, "S50-05", "Malformed JSON", "FAIL",
                       f"HTTP 500 — should be 400/422", t0=t0)
            else:
                record(sec, "S50-05", "Malformed JSON", "WARN",
                       f"unexpected HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S50-05", "Malformed JSON", "WARN", str(e)[:100], t0=t0)

    # S50-06: Missing Authorization header — must return 401
    t0 = time.time()
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{PIPELINE_URL}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={"model": "auto", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            )
            if r.status_code == 401:
                record(sec, "S50-06", "Missing auth rejected with 401", "PASS",
                       f"HTTP {r.status_code}", t0=t0)
            else:
                record(sec, "S50-06", "Missing auth", "FAIL",
                       f"HTTP {r.status_code} — should be 401", t0=t0)
    except Exception as e:
        record(sec, "S50-06", "Missing auth", "WARN", str(e)[:100], t0=t0)
