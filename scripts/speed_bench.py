#!/usr/bin/env python3
"""Measure prefill/decode speed on any of the Portal inference paths.

Three engines share one table and one JSON report:

* ``ollama`` — Ollama ``/api/chat``; the response carries the prefill/decode
  split as nanosecond durations.
* ``omlx`` — oMLX's OpenAI-compatible ``/v1/chat/completions``; oMLX reports
  ``prompt_eval_duration`` / ``generation_duration`` in ``usage``. When it
  reports neither, one streamed request is timed client-side and the row is
  marked ``timing_source: measured``.
* ``pipeline`` — the Portal Pipeline (the preferred path for seat decisions):
  streams a workspace reply, reads the ``portal_timings`` frame emitted before
  ``[DONE]`` plus ``x-portal-route``/served ``model``, and verifies the seat hit
  its intended backend and model.

URLs come from ``--host``, else ``OLLAMA_URL`` / ``OMLX_URL`` / ``PIPELINE_URL``,
else the documented localhost defaults; keys from ``--api-key``, else
``OMLX_API_KEY`` / ``PIPELINE_API_KEY``, else the repo ``.env``. Exit status is
non-zero when a request fails or a pipeline row hits the wrong engine/model.

Usage:
    uv run python scripts/speed_bench.py --engine ollama --model qwen3.8:27b
    uv run python scripts/speed_bench.py --engine omlx --model Qwen3.8-27B-oQ4e-mtp
    uv run python scripts/speed_bench.py --engine pipeline --workspace auto-coding
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

#: Estimated characters per token, used to size the filler prompt.
CHARS_PER_TOKEN = 4

#: Fixed decode length (tokens) for every benchmark request.
NUM_PREDICT = 128

#: Engines this bench can drive.
ENGINES = ("ollama", "omlx", "pipeline")

#: Documented local defaults, overridable by ``--host`` or the env var.
DEFAULT_URLS = {
    "ollama": "http://localhost:11434",
    "omlx": "http://localhost:8085",
    "pipeline": "http://localhost:9099",
}
URL_ENV = {"ollama": "OLLAMA_URL", "omlx": "OMLX_URL", "pipeline": "PIPELINE_URL"}
KEY_ENV = {"ollama": "", "omlx": "OMLX_API_KEY", "pipeline": "PIPELINE_API_KEY"}

_NS_PER_S = 1_000_000_000
_ENV_FILE = _REPO_ROOT / ".env"

_COLUMNS = ("size", "prompt", "prefill tok/s", "decode tok/s", "load s")


def build_filler_prompt(n_tokens: int) -> str:
    """Return a deterministic filler prompt of ``n_tokens * CHARS_PER_TOKEN`` chars."""
    if n_tokens < 1:
        raise ValueError("n_tokens must be at least 1")
    base = n_tokens * CHARS_PER_TOKEN
    word = "bench fill "
    return (word * (base // len(word) + 1))[:base]


def _number(value: object) -> float | None:
    """Return ``value`` as a float, or None when it is absent or unparseable."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _count(value: object) -> int | None:
    """Return ``value`` as an int, or None when it is absent or unparseable."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _row(
    *,
    prompt_tokens: int | None,
    prefill_tps: float | None,
    decode_tps: float | None,
    load_seconds: float | None,
    ttft_s: float | None,
    total_s: float | None,
    timing_source: str,
    engine_ok: bool = True,
) -> dict[str, Any]:
    """Build one engine-independent result row."""
    return {
        "prompt_tokens": prompt_tokens,
        "prefill_tps": prefill_tps,
        "decode_tps": decode_tps,
        "load_seconds": load_seconds,
        "ttft_s": ttft_s,
        "total_s": total_s,
        "timing_source": timing_source,
        "engine_ok": engine_ok,
    }


def speed_metrics(data: dict) -> dict:
    """Compute prefill/decode tok/s and load seconds from an ``/api/chat`` response.

    Durations are nanoseconds; a missing or zero counter/duration yields 0.0
    rather than a division error.
    """

    def per_second(count: object, ns: object) -> float:
        c = int(count or 0)  # type: ignore[arg-type]
        d = int(ns or 0)  # type: ignore[arg-type]
        return c / (d / _NS_PER_S) if c and d else 0.0

    return _row(
        prompt_tokens=int(data.get("prompt_eval_count") or 0),
        prefill_tps=per_second(data.get("prompt_eval_count"), data.get("prompt_eval_duration")),
        decode_tps=per_second(data.get("eval_count"), data.get("eval_duration")),
        load_seconds=int(data.get("load_duration") or 0) / _NS_PER_S,
        ttft_s=None,
        total_s=None,
        timing_source="engine",
    )


def omlx_metrics(body: dict) -> dict:
    """Read oMLX's OpenAI-shaped ``usage`` timing fields into a result row."""
    usage = body.get("usage") or {}
    prompt_tokens = _count(usage.get("prompt_tokens"))
    completion = _count(usage.get("completion_tokens"))
    prefill_s = _number(usage.get("prompt_eval_duration"))
    decode_s = _number(usage.get("generation_duration"))
    decode_tps = _number(usage.get("generation_tokens_per_second"))
    if decode_tps is None and completion and decode_s:
        decode_tps = completion / decode_s
    return _row(
        prompt_tokens=prompt_tokens,
        prefill_tps=prompt_tokens / prefill_s if prompt_tokens and prefill_s else None,
        decode_tps=decode_tps,
        load_seconds=_number(usage.get("model_load_duration")),
        ttft_s=_number(usage.get("time_to_first_token")),
        total_s=_number(usage.get("total_time")),
        timing_source="engine",
    )


def pipeline_metrics(
    timings: dict,
    usage: dict,
    served_model: str | None = None,
    *,
    route: str = "",
) -> dict:
    """Map the Pipeline's ``portal_timings`` frame, usage, and route to one result row."""
    prompt_tokens = _count(usage.get("prompt_tokens"))
    prefill_s = _number(timings.get("prefill_s"))
    row = _row(
        prompt_tokens=prompt_tokens,
        prefill_tps=prompt_tokens / prefill_s if prompt_tokens and prefill_s else None,
        decode_tps=_number(timings.get("answer_tps")),
        load_seconds=_number(usage.get("model_load_duration")),
        ttft_s=_number(timings.get("ttft_s")),
        total_s=_number(timings.get("total_s")),
        timing_source=str(timings.get("timing_source") or "measured"),
    )
    backend: str | None = None
    route_model: str | None = None
    if route:
        parts = route.split(";")
        if len(parts) >= 3:
            backend = parts[1] or None
            route_model = parts[2] or None
    row["backend"] = backend
    row["served_model"] = served_model or route_model
    row["completion_tokens"] = _count(usage.get("completion_tokens"))
    return row


def resolve_intended_seat(
    seat: str,
    *,
    registry: Any = None,
    portal_config: Any = None,
    personas: Mapping[str, Any] | None = None,
) -> tuple[str, str, str] | None:
    """Resolve ``seat`` to ``(backend_id, engine_type, target_model)`` via Pipeline routing."""
    from portal.platform.inference.cluster_backends import BackendRegistry
    from portal.platform.inference.config import load_persona_map, load_portal_config

    cfg = portal_config if portal_config is not None else load_portal_config(include_bench=True)
    reg = registry if registry is not None else BackendRegistry()
    persona_map = personas if personas is not None else load_persona_map(include_bench=True)

    ws_id = seat
    model_pin: str | None = None
    if ws_id.partition("::")[0] not in cfg.workspaces:
        persona = persona_map.get(ws_id)
        if persona is not None:
            ws_id = (
                f"{persona.workspace_model}::{persona.variant}"
                if persona.variant
                else persona.workspace_model
            )
            model_pin = persona.model_pin
        elif ws_id in cfg.aliases:
            ws_id = cfg.aliases[ws_id].to

    base_id, _, variant_name = ws_id.partition("::")
    spec = cfg.workspaces.get(base_id)
    if spec is None:
        return None
    model_hint = str(spec.model_hint or "")
    if variant_name and variant_name in spec.variants:
        model_hint = str(spec.variants[variant_name].get("model_hint") or model_hint)
    if model_pin:
        model_hint = str(model_pin)

    candidates = reg.get_backend_candidates(base_id)
    if not candidates:
        return None
    if model_hint:
        for backend in candidates:
            resolved = backend.resolve_model(model_hint)
            if resolved is not None:
                return (backend.id, backend.type, resolved)
    first = candidates[0]
    if not first.models:
        return None
    return (first.id, first.type, first.models[0])


def check_pipeline_engine(
    row: dict[str, Any],
    seat: str,
    *,
    intended: tuple[str, str, str] | None,
    backend_types: Mapping[str, str],
) -> str | None:
    """Verify a pipeline row served ``seat``'s intended backend and model.

    Mutates ``row`` with ``engine_ok`` and ``served_engine``; returns a loud
    ``WRONG ENGINE`` error string on mismatch, else ``None``.
    """
    served_backend = row.get("backend")
    served_model = row.get("served_model")
    served_engine = backend_types.get(served_backend) if served_backend else None
    if served_engine is not None:
        row["served_engine"] = served_engine

    if intended is None:
        row["engine_ok"] = False
        row["served_engine"] = served_engine or "unknown"
        return (
            f"WRONG ENGINE: seat {seat!r} could not be resolved in config "
            f"(got {served_backend or 'unknown'} ({row['served_engine']}) / "
            f"{served_model or 'unknown'})"
        )

    exp_backend, exp_engine, exp_model = intended
    if served_backend == exp_backend and served_model == exp_model:
        row["engine_ok"] = True
        return None

    row["engine_ok"] = False
    row["served_engine"] = served_engine or "unknown"
    return (
        f"WRONG ENGINE: seat {seat!r} expected {exp_backend} ({exp_engine}) / {exp_model}, "
        f"got {served_backend or 'unknown'} ({row['served_engine']}) / "
        f"{served_model or 'unknown'}"
    )


def stream_wall(lines: Iterable[bytes | str], clock: Any = time.monotonic) -> dict[str, Any]:
    """Time one OpenAI SSE stream client-side; return TTFT, wall time and usage."""
    started = clock()
    first: float | None = None
    last = started
    usage: dict[str, Any] = {}
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        obj = json.loads(data)
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        choices = obj.get("choices") or []
        delta = (choices[0].get("delta") or {}) if choices else {}
        now = clock()
        if first is None and (
            delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning")
        ):
            first = now
        last = now
    return {
        "ttft_s": None if first is None else first - started,
        "total_s": last - started,
        "usage": usage,
    }


def parse_sse_timings(lines: Iterable[bytes | str]) -> tuple[dict, dict, str | None]:
    """Return the last ``portal_timings`` frame, the usage chunk, and the served model."""
    timings: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    model: str | None = None
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj.get("portal_timings"), dict):
            timings = obj["portal_timings"]
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        if isinstance(obj.get("model"), str) and obj["model"]:
            model = obj["model"]
    return timings, usage, model


def _post(url: str, payload: dict, timeout: float, headers: dict[str, str] | None = None) -> Any:
    """POST ``payload`` as JSON and return the open response."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - documented host URLs


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"} if key else {}


def request_chat(host: str, model: str, prompt: str, timeout: float = 600.0) -> dict:
    """Send one non-streaming chat completion to Ollama and return the JSON body."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": NUM_PREDICT},
    }
    with _post(host.rstrip("/") + "/api/chat", payload, timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_omlx(
    host: str, model: str, prompt: str, api_key: str = "", timeout: float = 600.0
) -> dict:
    """Send one non-streaming completion to oMLX and return the JSON body."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": NUM_PREDICT,
    }
    with _post(
        host.rstrip("/") + "/v1/chat/completions", payload, timeout, _bearer(api_key)
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_omlx_streamed(
    host: str, model: str, prompt: str, api_key: str = "", timeout: float = 600.0
) -> dict:
    """Stream one completion and time TTFT/decode client-side (no engine split)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": NUM_PREDICT,
    }
    with _post(
        host.rstrip("/") + "/v1/chat/completions", payload, timeout, _bearer(api_key)
    ) as resp:
        return stream_wall(resp)


def request_pipeline(
    host: str,
    workspace: str,
    prompt: str,
    api_key: str = "",
    timeout: float = 600.0,
    *,
    no_tools: bool = False,
) -> tuple[dict, dict, str | None, str]:
    """Stream one workspace reply through the Pipeline.

    Returns ``(timings, usage, served_model, route)``: the ``portal_timings``
    frame, the usage chunk, the SSE chunk ``model``, and ``x-portal-route``.
    """
    payload: dict[str, Any] = {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": NUM_PREDICT,
    }
    if no_tools:
        payload["portal_no_tools"] = True
    headers = {**_bearer(api_key), "X-Portal-Client": "api"}
    with _post(host.rstrip("/") + "/v1/chat/completions", payload, timeout, headers) as resp:
        route = str(resp.headers.get("x-portal-route") or "") if hasattr(resp, "headers") else ""
        timings, usage, served_model = parse_sse_timings(resp)
        return timings, usage, served_model, route


def _measured_omlx(
    host: str, model: str, prompt: str, api_key: str, timeout: float
) -> dict[str, Any]:
    """Build a client-side-measured row when oMLX reported no durations."""
    wall = request_omlx_streamed(host, model, prompt, api_key, timeout)
    ttft_s = wall["ttft_s"]
    decode_s = None if ttft_s is None else max(0.0, wall["total_s"] - ttft_s)
    usage = wall["usage"]
    completion = _count(usage.get("completion_tokens"))
    prompt_tokens = _count(usage.get("prompt_tokens"))
    return _row(
        prompt_tokens=prompt_tokens,
        prefill_tps=prompt_tokens / ttft_s if prompt_tokens and ttft_s else None,
        decode_tps=completion / decode_s if completion and decode_s else None,
        load_seconds=None,
        ttft_s=ttft_s,
        total_s=wall["total_s"],
        timing_source="measured",
    )


def _measure(
    engine: str,
    host: str,
    target: str,
    prompt: str,
    api_key: str,
    timeout: float,
    *,
    no_tools: bool = False,
) -> dict[str, Any]:
    """Measure one prompt on ``engine`` and return a result row."""
    if engine == "ollama":
        return speed_metrics(request_chat(host, target, prompt, timeout))
    if engine == "omlx":
        row = omlx_metrics(request_omlx(host, target, prompt, api_key, timeout))
        if row["prefill_tps"] is None and row["decode_tps"] is None:
            return _measured_omlx(host, target, prompt, api_key, timeout)
        return row
    if engine == "pipeline":
        timings, usage, served_model, route = request_pipeline(
            host, target, prompt, api_key, timeout, no_tools=no_tools
        )
        if not timings:
            raise ValueError("stream carried no portal_timings frame")
        return pipeline_metrics(timings, usage, served_model, route=route)
    raise ValueError(f"unknown engine {engine!r}")


def _cell(value: object, spec: str) -> str:
    """Format a metric, or a dash when the engine did not report it."""
    return "-" if value is None else format(value, spec)  # type: ignore[call-overload]


def format_table(rows: list[dict]) -> str:
    """Render one aligned table row per measured size."""
    cells = [
        [
            _cell(row["size_tokens"], "d"),
            _cell(row["prompt_tokens"], "d"),
            _cell(row["prefill_tps"], ".1f"),
            _cell(row["decode_tps"], ".1f"),
            _cell(row["load_seconds"], ".3f"),
        ]
        for row in rows
    ]
    widths = [len(header) for header in _COLUMNS]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(w) for h, w in zip(_COLUMNS, widths, strict=True))]
    lines.extend("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in cells)
    return "\n".join(lines)


def _pipeline_seat_context(
    target: str,
    *,
    registry: Any = None,
    portal_config: Any = None,
    personas: Mapping[str, Any] | None = None,
) -> tuple[tuple[str, str, str] | None, dict[str, str]]:
    """Resolve the intended seat and backend id -> engine type map once per run."""
    from portal.platform.inference.cluster_backends import BackendRegistry

    reg = registry if registry is not None else BackendRegistry()
    intended = resolve_intended_seat(
        target, registry=reg, portal_config=portal_config, personas=personas
    )
    backend_types = {b.id: b.type for b in reg.list_backends()}
    return intended, backend_types


def run_bench(
    engine: str,
    host: str,
    target: str,
    sizes: list[int],
    *,
    out: str | None = None,
    api_key: str = "",
    timeout: float = 600.0,
    no_tools: bool = False,
    registry: Any = None,
    portal_config: Any = None,
    personas: Mapping[str, Any] | None = None,
) -> int:
    """Benchmark every size; print the table; return 0 on success, 1 on any failure."""
    rows: list[dict] = []
    failures: list[str] = []
    intended: tuple[str, str, str] | None = None
    backend_types: dict[str, str] = {}
    if engine == "pipeline":
        intended, backend_types = _pipeline_seat_context(
            target, registry=registry, portal_config=portal_config, personas=personas
        )

    for size in sizes:
        prompt = build_filler_prompt(size)
        try:
            row = _measure(engine, host, target, prompt, api_key, timeout, no_tools=no_tools)
        except (OSError, ValueError) as exc:
            failures.append(f"FAILED size {size} tokens: {exc}")
            continue
        if row["timing_source"] == "measured" and engine == "omlx":
            print(
                f"NOTE size {size}: oMLX reported no prefill/decode split; "
                "TTFT and decode measured client-side",
                file=sys.stderr,
            )
        if engine == "pipeline":
            mismatch = check_pipeline_engine(
                row, target, intended=intended, backend_types=backend_types
            )
            if mismatch:
                failures.append(f"{mismatch} [size {size} tokens]")
        rows.append({"size_tokens": size, **row})

    if rows:
        print(format_table(rows))
    for message in failures:
        print(message, file=sys.stderr)

    if out is not None:
        report = {
            "engine": engine,
            "host": host,
            "model": target,
            "results": rows,
            "failures": failures,
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
    return 1 if failures else 0


def parse_sizes(spec: str) -> list[int]:
    """Parse a comma-separated list of positive prompt sizes."""
    try:
        sizes = [int(part) for part in spec.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--sizes must be positive integers, got {spec!r}"
        ) from exc
    if not sizes or any(s <= 0 for s in sizes):
        raise argparse.ArgumentTypeError(
            "--sizes must be a comma-separated list of positive integers"
        )
    return sizes


def resolve_url(engine: str, override: str | None = None) -> str:
    """``--host``, else the engine's env var, else its documented local default."""
    url = override or os.environ.get(URL_ENV[engine]) or DEFAULT_URLS[engine]
    return url.rstrip("/")


def _env_file_value(name: str) -> str:
    """Read ``name`` from the repo ``.env`` (host scripts have no exported env)."""
    if not _ENV_FILE.is_file():
        return ""
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def engine_key(engine: str) -> str:
    """The engine's API key from the environment, else the repo ``.env``."""
    name = KEY_ENV[engine]
    return (os.environ.get(name) or _env_file_value(name)) if name else ""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure prefill/decode tok/s per prompt size on Ollama, oMLX or "
        "the Portal Pipeline."
    )
    parser.add_argument("--engine", choices=ENGINES, default="ollama")
    parser.add_argument(
        "--host",
        default=None,
        help="Base URL; default OLLAMA_URL / OMLX_URL / PIPELINE_URL per engine, "
        "else the documented localhost default",
    )
    parser.add_argument("--model", default=None, help="Model name (ollama/omlx) or workspace id")
    parser.add_argument(
        "--workspace", default=None, help="Pipeline workspace id (default: --model)"
    )
    parser.add_argument(
        "--sizes",
        type=parse_sizes,
        default=[2000, 8000, 32000],
        help="Comma-separated prompt sizes in tokens (default: 2000,8000,32000)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Engine key; default OMLX_API_KEY / PIPELINE_API_KEY, else the repo .env",
    )
    parser.add_argument("--timeout", type=float, default=600.0, help="Per-request seconds")
    parser.add_argument("--out", default=None, help="Optional path to write the JSON results")
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Send portal_no_tools=true on pipeline requests (measure raw seat speed)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.engine == "pipeline":
        target = args.workspace or args.model
        if not target:
            parser.error("--workspace (or --model) is required for --engine pipeline")
    else:
        target = args.model
        if not target:
            parser.error(f"--model is required for --engine {args.engine}")
    return run_bench(
        args.engine,
        resolve_url(args.engine, args.host),
        target,
        args.sizes,
        out=args.out,
        api_key=args.api_key if args.api_key is not None else engine_key(args.engine),
        timeout=args.timeout,
        no_tools=args.no_tools,
    )


if __name__ == "__main__":
    raise SystemExit(main())
