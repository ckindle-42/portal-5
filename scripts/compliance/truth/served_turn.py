"""P6R: runtime serving facts, never a window inferred from a model tag.

The workspace context limit is an instruction to the adapter. It is not proof
of an engine's applied window. Read the serving engine's own metadata; missing
facts stay unknown and invalidate a declared measurement.
"""

from __future__ import annotations

from typing import Any


def window_fields(prompt_tokens: int | None, window: int | None) -> dict[str, Any]:
    """Unknown measurements remain None, including the exceedance flag."""
    known = prompt_tokens is not None and window is not None and window > 0
    return {
        "serving_window": window,
        "prompt_tokens": prompt_tokens,
        "window_pressure": prompt_tokens / window if known else None,
        "window_exceeded": prompt_tokens >= window if known else None,
    }


def capture(
    session,
    router: str,
    correlation_id: str,
    route: str,
    prompt_tokens: int | None,
    *,
    headers: dict,
) -> dict:
    """Read a completed pipeline trace and serving metadata without changing either."""
    from portal.platform.inference.cluster_backends import BackendRegistry
    from portal.platform.inference.omlx_auth import omlx_headers

    out: dict = {"correlation_id": correlation_id, "errors": []}
    trace = {}
    if correlation_id:
        try:
            response = session.get(
                f"{router}/v1/trace/{correlation_id}", headers=headers, timeout=10
            )
            response.raise_for_status()
            trace = response.json()
        except Exception as exc:  # noqa: BLE001 - an unknown fact is recorded
            out["errors"].append(f"trace: {exc}")
    parts = route.split(";")
    backend_id = trace.get("backend") or (parts[1] if len(parts) > 1 else "")
    model = trace.get("model") or (parts[2] if len(parts) > 2 else "")
    backend = BackendRegistry()._backends.get(backend_id)
    out.update(
        {
            "backend": backend_id,
            "engine": backend.type if backend else None,
            "served_model": model,
            "trace": trace,
        }
    )
    # Keep the exact trace events; absent metadata is not evidence of no cascade.
    out["cascade"] = (
        [
            s
            for s in trace.get("spans", [])
            if "cascade" in s.get("name", "")
            or "fallback" in s.get("name", "")
            or s.get("fallback")
        ]
        if trace
        else None
    )
    window = None
    if backend:
        url = backend.url.replace("host.docker.internal", "localhost").rstrip("/")
        try:
            if backend.type == "omlx":
                response = session.get(f"{url}/v1/models", headers=omlx_headers(), timeout=10)
                response.raise_for_status()
                entry = next(
                    (m for m in response.json().get("data", []) if m.get("id") == model), {}
                )
                window = entry.get("max_model_len")
                out["window_source"] = "serving engine /v1/models max_model_len"
            elif backend.type == "ollama":
                response = session.get(f"{url}/api/ps", timeout=10)
                response.raise_for_status()
                entry = next(
                    (
                        m
                        for m in response.json().get("models", [])
                        if model in (m.get("name"), m.get("model"))
                    ),
                    {},
                )
                window = entry.get("context_length")
                out["window_source"] = "serving engine /api/ps context_length"
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"window: {exc}")
    out.update(window_fields(prompt_tokens, int(window) if window else None))
    return out
