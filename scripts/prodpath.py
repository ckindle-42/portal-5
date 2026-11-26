"""Shared streamed client and receipt checks for production-path harnesses."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OWUI_ID: dict[str, str | None] = {
    "auto-security": "auto-security",
    "auto-security::uncensored": "securityuncensored",
    "auto-security::purpleteam-deep": None,
}
SUCCESS_OUTCOMES = frozenset({"complete", "ok", "safety_refusal"})
PREFLIGHT_PROMPT = "Read this short context fill and reply READY. " + "context " * 44


@dataclass(frozen=True)
class SeatTarget:
    workspace: str
    backend: str | None
    model: str
    engine: str | None = None
    route: str = "auto"
    owui_id: str | None = None
    request_workspace: str | None = None
    request_model: str | None = None


@dataclass
class StreamResult:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    first_token_s: float | None = None
    raw_lines: list[bytes | str] = field(default_factory=list)
    error: str = ""


@dataclass
class TurnReceipt:
    status: int = 0
    text: str = ""
    prompt_tokens: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] | None = None
    outcome: str = "no-trace"
    backend: str = ""
    model: str = ""
    correlation_id: str = ""
    started_at: float = 0.0
    wall_s: float = 0.0
    first_token_s: float | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_lines: list[bytes | str] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True)
class PreflightResult:
    target: SeatTarget
    receipt: TurnReceipt
    ok: bool
    failures: tuple[str, ...]


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    path = REPO / ".env"
    if not path.is_file():
        return default
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, raw = line.strip().partition("=")
        if key == name:
            return raw.strip().strip("'\"")
    return default


def resolve_route(workspace: str) -> tuple[str, str | None]:
    """Resolve known OWUI aliases and send unlisted variants through the Pipeline."""
    if workspace in OWUI_ID:
        model_id = OWUI_ID[workspace]
        return ("owui", model_id) if model_id else ("pipeline", None)
    if "::" in workspace:
        return "pipeline", None
    return "owui", workspace


def workspace_config(workspace: str) -> tuple[str, dict[str, Any]]:
    """Load a workspace's effective config, resolving deprecated workspace aliases."""
    import yaml

    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text(encoding="utf-8"))
    workspaces = portal["workspaces"]
    resolved = workspace
    visited = set()
    while resolved.split("::", 1)[0] not in workspaces:
        if resolved in visited:
            raise ValueError(f"workspace alias cycle for {workspace!r}")
        visited.add(resolved)
        alias = (portal.get("aliases") or {}).get(resolved)
        if not alias or not alias.get("to"):
            raise ValueError(f"unknown workspace {workspace!r}")
        resolved = str(alias["to"])
    from portal.platform.inference.config import effective_workspace

    return resolved, effective_workspace(workspaces, resolved)


def configured_target(
    workspace: str,
    model: str | None = None,
    *,
    backend: str | None = None,
    engine: str | None = None,
    route: str = "auto",
) -> SeatTarget:
    """Resolve the configured served identity for a workspace and optional model override."""
    from portal.platform.inference.cluster_backends import BackendRegistry

    resolved_workspace, config = workspace_config(workspace)
    hint = model or str(config.get("model_hint") or "")
    if not hint:
        raise ValueError(f"workspace {workspace!r} has no model hint")
    registry = BackendRegistry(config_path=str(REPO / "config/backends.yaml"))
    base = resolved_workspace.split("::", 1)[0]
    groups = list(registry.workspace_routes.get(base, []))
    groups.append("general")
    candidates = list(registry._backends.values())
    for group in groups:
        for candidate in candidates:
            if candidate.group != group or (backend and candidate.id != backend):
                continue
            if engine and candidate.type != engine:
                continue
            resolved = candidate.resolve_model(hint)
            if resolved:
                route_kind, alias = resolve_route(workspace)
                if resolved_workspace != workspace:
                    route_kind, alias = "pipeline", None
                return SeatTarget(
                    resolved_workspace,
                    candidate.id if backend else None,
                    resolved,
                    candidate.type,
                    route if route != "auto" else route_kind,
                    alias,
                    workspace if resolved_workspace != workspace else None,
                )
    raise ValueError(f"no configured backend resolves {hint!r} for {workspace!r}")


def parse_stream(lines: Any) -> StreamResult:
    """Read streamed content, usage and audit calls from OpenAI-compatible SSE."""
    result = StreamResult()
    text: list[str] = []
    started = time.monotonic()
    for raw in lines:
        result.raw_lines.append(raw)
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if event.get("error"):
            result.error = str(event["error"])
            continue
        if isinstance(event.get("usage"), dict):
            result.usage.update(event["usage"])
        if event.get("type") == "exec_audit":
            result.tool_calls.extend(event.get("tool_calls") or [])
            continue
        choice = (event.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        content = delta.get("content") or ""
        if content:
            if result.first_token_s is None:
                result.first_token_s = time.monotonic() - started
            text.append(content)
    result.text = "".join(text)
    return result


def _headers(key: str, correlation_id: str, extra: dict[str, str] | None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
        **(extra or {}),
    }


def _http_stream(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    client: Any = None,
) -> tuple[int, StreamResult, str]:
    if client is not None:
        try:
            with client.stream(
                "POST", url, json=body, headers=headers, timeout=timeout
            ) as response:
                status = int(response.status_code)
                if status != 200:
                    return status, StreamResult(), str(response.text)[:500]
                parsed = parse_stream(response.iter_lines())
                return status, parsed, parsed.error
        except Exception as exc:  # noqa: BLE001
            response = getattr(exc, "response", None)
            status = int(getattr(response, "status_code", 0) or 0)
            return status, StreamResult(), f"{type(exc).__name__}: {exc}"[:500]
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            parsed = parse_stream(response)
            return int(response.status), parsed, parsed.error
    except urllib.error.HTTPError as exc:
        return exc.code, StreamResult(), exc.read()[:500].decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, StreamResult(), f"{type(exc).__name__}: {exc}"[:500]


def _trace_data(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def _epoch(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        if isinstance(value, str):
            try:
                from datetime import datetime

                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0
        return 0.0


def select_trace(
    traces: list[dict[str, Any]],
    target: SeatTarget,
    started_at: float,
    correlation_id: str = "",
) -> dict[str, Any] | None:
    """Match a request id first, then the closest workspace trace in its time window."""
    id_fields = ("correlation_id", "request_id", "turn_id", "chat_id")
    if correlation_id:
        for trace in traces:
            if any(str(trace.get(key) or "") == correlation_id for key in id_fields):
                return trace
    aliases = {target.workspace}
    if target.request_workspace:
        aliases.add(target.request_workspace)
    owui_alias = target.owui_id or OWUI_ID.get(target.workspace)
    if owui_alias:
        aliases.add(owui_alias)
    matches = [
        trace
        for trace in traces
        if aliases.intersection(
            str(trace.get(key) or "") for key in ("workspace", "requested", "persona", "model")
        )
        and _epoch(trace.get("started_at")) >= started_at - 2
        # OWUI's title/tag task call fires on the same workspace right after the turn.
        and not trace.get("owui_task")
    ]
    return min(
        matches,
        key=lambda item: (
            abs(_epoch(item.get("started_at")) - started_at),
            -_epoch(item.get("started_at")),
        ),
        default=None,
    )


def _request_json(url: str, key: str, timeout: float, client: Any = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {key}"}
    if client is not None:
        response = client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def fetch_trace(
    target: SeatTarget,
    started_at: float,
    correlation_id: str,
    pipeline_url: str,
    pipeline_key: str,
    *,
    client: Any = None,
    wait_s: float = 1.5,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + wait_s
    while True:
        try:
            index = _request_json(
                f"{pipeline_url.rstrip('/')}/v1/trace?limit=30", pipeline_key, 30, client
            )
            traces = index.get("data") or []
            match = select_trace(traces, target, started_at, correlation_id)
            if match:
                trace_id = str(match.get("correlation_id") or "")
                if trace_id:
                    return _trace_data(
                        _request_json(
                            f"{pipeline_url.rstrip('/')}/v1/trace/{trace_id}",
                            pipeline_key,
                            30,
                            client,
                        )
                    )
                return match
        except Exception:  # noqa: BLE001 — a missing trace is reported as an invalid receipt
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def fetch_trace_by_id(
    correlation_id: str,
    pipeline_url: str,
    pipeline_key: str,
    *,
    client: Any = None,
) -> dict[str, Any]:
    """Fetch a trace by the request's correlation id."""
    return _trace_data(
        _request_json(
            f"{pipeline_url.rstrip('/')}/v1/trace/{correlation_id}",
            pipeline_key,
            30,
            client,
        )
    )


def prompt_tokens(usage: dict[str, Any], trace: dict[str, Any] | None) -> int:
    for source in (usage, (trace or {}).get("usage") or {}):
        try:
            count = int(source.get("prompt_tokens") or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return count
    try:
        return int((trace or {}).get("prompt_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def trace_failures(target: SeatTarget, trace: dict[str, Any] | None) -> list[str]:
    if trace is None:
        return ["no Pipeline /v1/trace record matched the OWUI turn"]
    failures = []
    expected_workspaces = {target.workspace}
    if target.request_workspace:
        expected_workspaces.add(target.request_workspace)
    if trace.get("workspace") not in expected_workspaces:
        failures.append(
            f"trace resolved {trace.get('workspace')!r}, not one of {sorted(expected_workspaces)!r}"
        )
    outcome = str(trace.get("outcome") or "")
    if outcome not in SUCCESS_OUTCOMES:
        failures.append(f"trace outcome {outcome!r} is not a successful outcome")
    backend = str(trace.get("backend") or "")
    model = str(trace.get("model") or "")
    if outcome == "safety_refusal" and not backend and not model:
        return failures
    if target.backend and (backend, model) != (target.backend, target.model):
        failures.append(
            f"served {backend}/{model}, seat intends {target.backend}/{target.model} "
            "(fallback is a FAIL, not a pass)"
        )
    if target.engine:
        try:
            import yaml

            config = yaml.safe_load((REPO / "config/backends.yaml").read_text(encoding="utf-8"))
            engine = next(
                str(item.get("type") or "")
                for item in config.get("backends") or []
                if item.get("id") == backend
            )
        except (StopIteration, OSError, ValueError):
            engine = ""
        if engine != target.engine:
            failures.append(f"served engine {engine or backend!r}, expected {target.engine!r}")
    if model != target.model and not target.backend:
        failures.append(f"served model {model!r}, expected {target.model!r}")
    return failures


def stream_chat(
    target: SeatTarget,
    messages: list[dict[str, Any]],
    *,
    owui_url: str,
    pipeline_url: str,
    owui_key: str,
    pipeline_key: str,
    timeout: float = 900,
    route: str | None = None,
    pipeline_model: str | None = None,
    body_extra: dict[str, Any] | None = None,
    headers_extra: dict[str, str] | None = None,
    client: Any = None,
) -> TurnReceipt:
    route_kind, owui_id = resolve_route(target.request_workspace or target.workspace)
    route_kind = route or (target.route if target.route != "auto" else route_kind)
    if target.owui_id is not None:
        owui_id = target.owui_id
    correlation_id = str(uuid.uuid4())
    started = time.time()
    if route_kind == "owui":
        url = f"{owui_url.rstrip('/')}/api/chat/completions"
        body_model = owui_id or target.request_workspace or target.workspace
        key = owui_key
    elif route_kind == "pipeline":
        url = f"{pipeline_url.rstrip('/')}/v1/chat/completions"
        requested_model = pipeline_model or target.request_model
        if requested_model:
            url += "?" + urllib.parse.urlencode({"model": requested_model})
        body_model = target.request_workspace or target.workspace
        key = pipeline_key
    else:
        raise ValueError(f"unknown production route {route_kind!r}")
    body = {
        "model": body_model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        **(body_extra or {}),
    }
    headers = _headers(key, correlation_id, headers_extra)
    started_mono = time.monotonic()
    status, streamed, error = _http_stream(url, body, headers, timeout, client)
    wall_s = time.monotonic() - started_mono
    trace = fetch_trace(
        target,
        started,
        correlation_id,
        pipeline_url,
        pipeline_key,
        client=client,
    )
    return TurnReceipt(
        status=status,
        text=streamed.text,
        prompt_tokens=prompt_tokens(streamed.usage, trace),
        usage=streamed.usage,
        trace=trace,
        outcome=str((trace or {}).get("outcome") or "no-trace"),
        backend=str((trace or {}).get("backend") or ""),
        model=str((trace or {}).get("model") or ""),
        correlation_id=correlation_id,
        started_at=started,
        wall_s=wall_s,
        first_token_s=streamed.first_token_s,
        tool_calls=streamed.tool_calls,
        raw_lines=streamed.raw_lines,
        error=error,
    )


def preflight(
    seats: list[SeatTarget],
    *,
    owui_url: str = "http://localhost:8080",
    pipeline_url: str = "http://localhost:9099",
    owui_key: str | None = None,
    pipeline_key: str | None = None,
    timeout: float = 180,
    client: Any = None,
) -> list[PreflightResult]:
    results = []
    for target in seats:
        receipt = stream_chat(
            target,
            [{"role": "user", "content": PREFLIGHT_PROMPT}],
            owui_url=owui_url,
            pipeline_url=pipeline_url,
            owui_key=owui_key or env("OWUI_API_KEY"),
            pipeline_key=pipeline_key or env("PIPELINE_API_KEY"),
            timeout=timeout,
            client=client,
        )
        failures = []
        if receipt.status != 200:
            failures.append(f"HTTP {receipt.status}: {receipt.error or 'no response'}")
        if receipt.error:
            failures.append(f"stream error: {receipt.error}")
        if receipt.prompt_tokens <= 0:
            failures.append("no measured prompt_tokens in the stream or Pipeline trace")
        failures.extend(trace_failures(target, receipt.trace))
        if receipt.trace and (not receipt.backend or not receipt.model):
            failures.append("trace does not name a served backend and model")
        outcome = receipt.outcome or "no-trace"
        served = f"{receipt.backend or '-'} / {receipt.model or '-'}"
        trace_id = str((receipt.trace or {}).get("correlation_id") or "-")
        label = "PASS" if not failures else "FAIL"
        print(
            f"PREFLIGHT {label} {target.workspace}: HTTP {receipt.status}, "
            f"prompt_tokens={receipt.prompt_tokens}, trace={trace_id}, "
            f"outcome={outcome}, served={served}",
            flush=True,
        )
        for failure in failures:
            print(f"  - {failure}", flush=True)
        results.append(PreflightResult(target, receipt, not failures, tuple(failures)))
    return results


def calibrate_context_fill(
    target: SeatTarget,
    baseline: TurnReceipt,
    *,
    owui_url: str,
    pipeline_url: str,
    owui_key: str,
    pipeline_key: str,
    timeout: float = 180,
) -> tuple[float, int] | None:
    """Measure a seat's filler density while cancelling its fixed prompt overhead."""
    receipt = stream_chat(
        target,
        [{"role": "user", "content": f"{PREFLIGHT_PROMPT} {PREFLIGHT_PROMPT}"}],
        owui_url=owui_url,
        pipeline_url=pipeline_url,
        owui_key=owui_key,
        pipeline_key=pipeline_key,
        timeout=timeout,
    )
    added_tokens = receipt.prompt_tokens - baseline.prompt_tokens
    failures = []
    if receipt.status != 200:
        failures.append(f"HTTP {receipt.status}: {receipt.error or 'no response'}")
    if receipt.error:
        failures.append(f"stream error: {receipt.error}")
    if added_tokens <= 0:
        failures.append("short calibration prompt added no measured prompt_tokens")
    failures.extend(trace_failures(target, receipt.trace))
    if failures:
        print(f"CALIBRATION FAIL {target.workspace}: {'; '.join(failures)}", flush=True)
        return None
    chars_per_token = len(PREFLIGHT_PROMPT) / added_tokens
    baseline_tokens = max(baseline.prompt_tokens - added_tokens, 0)
    print(
        f"CALIBRATION PASS {target.workspace}: delta_prompt_tokens={added_tokens}, "
        f"chars_per_token={chars_per_token:.3f}, baseline_tokens={baseline_tokens}",
        flush=True,
    )
    return chars_per_token, baseline_tokens
