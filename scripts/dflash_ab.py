#!/usr/bin/env python3
"""Unattended DFlash2 on/off A/B for one oMLX seat, ending in a single receipt.

Preconditions (Ollama unloaded, 64 GiB reclaimed, host quiet) → OFF arm → the plan's
two-key settings delta applied through oMLX's admin API and proven from the server log →
ON arm → receipt. Decode tok/s per size is the pass metric; a fixed coding prompt and a
tool-call probe guard correctness. DFlash is restored to its prior state on every exit
path (failure, Ctrl-C) unless the pass bar was met and ``--keep-on`` was given.

Usage:
    uv run python scripts/dflash_ab.py
    uv run python scripts/dflash_ab.py --keep-on --reps 3 --sizes 2000,8000,32000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The seat whose variant pins the model under test (config/personas/qwen38coder_dflash.yaml).
DEFAULT_SEAT = "auto-coding::qwen38coder-dflash"
#: The hunt's seat; measured only when it resolves to the model this delta toggles.
HUNT_SEAT = "hunt-reasoning"
#: The plan's draft checkpoint (coding_task/DFLASH2_080_PLAN.md).
DEFAULT_DRAFT = "/Volumes/data01/omlx-models/Qwen3.8-27B-DFlash2"
DEFAULT_SIZES = (2000, 8000, 32000)
DEFAULT_REPS = 3
RECLAIM_NEED_GIB = 64
REQUEST_TIMEOUT_S = 1800.0
CALL_TIMEOUT_S = 90.0
UNLOAD_TIMEOUT_S = 180.0
PROOF_TIMEOUT_S = 240.0
PROOF_POLL_S = 2.0
WARMUP_TOKENS = 8
PROBE_TOKENS = 512

#: The only per-model settings keys this A/B changes (DFLASH2_080_PLAN.md).
DFLASH_KEYS = ("dflash_enabled", "dflash_draft_model")
#: Engine log lines that prove a drafter is attached (oMLX 0.8.0), matched per model.
DFLASH_PROOF_MARKERS = (
    "DFlash drafter attached to engine:",
    "DFlash enabled for",
    "Speculative backend selected for",
)
#: Log lines that prove the toggle did not take.
DFLASH_FAILURE_MARKERS = ("toggle ignored", "loading without DFlash", "no draft model is set")
#: A short coding answer with one exact expected value: no execution, no judgement.
CODING_PROMPT = (
    "What does this Python print? Trace it exactly and reply with only the output line.\n\n"
    "```python\n"
    "def f(xs):\n"
    "    return [x * 2 for x in xs if x % 3 == 0]\n\n"
    "print(sum(f(range(1, 20))))\n"
    "```\n"
)
CODING_EXPECTED = "126"
PROBE_TOOL = "fetch_weather"
PROBE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": PROBE_TOOL,
            "description": "Fetch a short weather forecast for one city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer"},
                    "include_humidity": {"type": "boolean"},
                },
                "required": ["city", "days", "include_humidity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_saved_reports",
            "description": "List saved reports.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
    },
]
TOOL_PROMPT = (
    "For the city of Lisbon, call fetch_weather for a 3-day forecast that includes "
    "humidity. Emit the tool call; do not answer in prose."
)
READ_ERRORS = (OSError, ValueError, TimeoutError, urllib.error.URLError)


class AbortedError(RuntimeError):
    """The run cannot continue; the receipt records why."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _env_value(name: str, default: str = "") -> str:
    """Read one named value from the environment or the repo .env, never sourcing it."""
    value = os.environ.get(name)
    if value:
        return value
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'") or default
    return default


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"} if key else {}


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def _spread(values: list[float]) -> float | None:
    """Max minus min — the run-to-run band a gain has to clear."""
    return round(max(values) - min(values), 2) if values else None


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _answer_matches(answer: str, expected: str) -> bool:
    """True when the expected number appears in the answer as its own token."""
    flat = re.sub(r"[`*_]", "", answer or "")
    return re.search(rf"(?<!\d){re.escape(expected)}(?!\d)", flat) is not None


def _route_parts(route: str) -> tuple[str | None, str | None]:
    """Split ``workspace;backend;model`` (the Pipeline's x-portal-route) into its parts."""
    parts = route.split(";")
    if len(parts) < 3:
        return None, None
    return parts[1] or None, parts[2] or None


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


class Http:
    """Minimal JSON client; the seam unit tests replace."""

    def json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Any:
        body, _headers = self.json_response(
            url, method=method, payload=payload, headers=headers, timeout=timeout
        )
        return body

    def json_response(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> tuple[Any, dict[str, str]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        merged: dict[str, str] = {"Content-Type": "application/json"} if data is not None else {}
        merged.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=merged, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
        return (json.loads(raw) if raw else {}), response_headers


def _http_error(exc: urllib.error.HTTPError) -> str:
    try:
        detail = exc.read().decode("utf-8", "replace")[:400]
    except (OSError, AttributeError):
        detail = ""
    return f"HTTP {exc.code}: {detail}"


def _default_host_quiet() -> dict[str, Any]:
    """Run ``scripts/host_quiet.py``; non-zero means the host is not quiet."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "host_quiet.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-2000:],
    }


@dataclass
class DflashCtx:
    """Live endpoints, paths, and the injected seams unit tests replace."""

    out_dir: Path
    pipeline_url: str
    omlx_url: str
    ollama_url: str
    pipeline_key: str
    omlx_key: str
    settings_file: Path
    server_log: Path
    sizes: tuple[int, ...] = DEFAULT_SIZES
    reps: int = DEFAULT_REPS
    http: Http = field(default_factory=Http)
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    host_quiet: Callable[[], dict[str, Any]] = _default_host_quiet
    speed: Callable[..., int] | None = None
    pipeline_bench: Callable[..., int] | None = None


@dataclass(frozen=True)
class Plan:
    """What the run measures and how it toggles."""

    seat: str
    model: str
    draft: str
    sizes: tuple[int, ...]
    reps: int
    keep_on: bool
    hunt: dict[str, Any]
    backend: str = ""


def _host_url(name: str, default: str) -> str:
    return (_env_value(name) or default).replace("host.docker.internal", "localhost").rstrip("/")


def context(out_dir: Path, args: argparse.Namespace) -> DflashCtx:
    return DflashCtx(
        out_dir=out_dir,
        pipeline_url=_host_url("PIPELINE_URL", "http://localhost:9099"),
        omlx_url=_host_url("OMLX_URL", "http://localhost:8085"),
        ollama_url=_host_url("OLLAMA_URL", "http://localhost:11434"),
        pipeline_key=_env_value("PIPELINE_API_KEY"),
        omlx_key=_env_value("OMLX_API_KEY"),
        settings_file=Path(args.settings_file).expanduser(),
        server_log=Path(args.server_log).expanduser(),
        sizes=tuple(args.sizes),
        reps=args.reps,
    )


# --------------------------------------------------------------------------- preconditions


def _ollama_residents(ctx: DflashCtx) -> list[str]:
    payload = ctx.http.json(f"{ctx.ollama_url}/api/ps", timeout=10.0)
    models = (payload or {}).get("models") or [] if isinstance(payload, dict) else []
    return [str(row.get("name") or row.get("model")) for row in models if isinstance(row, dict)]


def _unload_ollama(ctx: DflashCtx, models: list[str]) -> list[dict[str, Any]]:
    results = []
    for model in models:
        try:
            ctx.http.json(
                f"{ctx.ollama_url}/api/generate",
                method="POST",
                payload={"model": model, "keep_alive": 0, "stream": False},
                timeout=60.0,
            )
            results.append({"model": model, "ok": True})
        except READ_ERRORS as exc:
            results.append({"model": model, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return results


def reclaim(ctx: DflashCtx) -> dict[str, Any]:
    """Ask the Pipeline to free ``RECLAIM_NEED_GIB`` (the plan's precondition)."""
    try:
        body = ctx.http.json(
            f"{ctx.pipeline_url}/admin/reclaim-idle",
            method="POST",
            payload={"need_gib": RECLAIM_NEED_GIB},
            headers=_bearer(ctx.pipeline_key),
            timeout=CALL_TIMEOUT_S,
        )
        return {"ok": True, "response": body}
    except READ_ERRORS as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def precondition(ctx: DflashCtx) -> dict[str, Any]:
    """Unload Ollama residents, reclaim 64 GiB, then require a quiet host."""
    record: dict[str, Any] = {"started_at": _now(), "ok": False, "problems": []}
    try:
        record["ollama_before"] = _ollama_residents(ctx)
    except READ_ERRORS as exc:
        record["problems"].append(f"ollama /api/ps unavailable: {type(exc).__name__}: {exc}")
        record["finished_at"] = _now()
        return record
    record["ollama_unloads"] = _unload_ollama(ctx, record["ollama_before"])
    record["reclaim"] = reclaim(ctx)
    if not record["reclaim"]["ok"]:
        record["problems"].append(f"reclaim-idle failed: {record['reclaim']['error']}")
    quiet = ctx.host_quiet()
    record["host_quiet"] = quiet
    if quiet.get("returncode") != 0:
        record["problems"].append("host is not quiet (host_quiet.py exited non-zero)")
    record["ok"] = not record["problems"]
    record["finished_at"] = _now()
    return record


# ------------------------------------------------------------------------------- settings


def settings_delta(draft: str) -> dict[str, Any]:
    """The plan's exact delta for the model entry — two keys, nothing else."""
    return {"dflash_enabled": True, "dflash_draft_model": str(Path(draft))}


def restore_payload(prior: Mapping[str, Any]) -> dict[str, Any]:
    """The prior state of the two keys, shaped for the same settings endpoint."""
    return {
        "dflash_enabled": bool(prior.get("enabled")),
        "dflash_draft_model": prior.get("draft") or None,
    }


def read_settings(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def dflash_state(settings: Mapping[str, Any], model: str) -> dict[str, Any]:
    """``dflash_enabled``/``dflash_draft_model`` of one model entry, as recorded."""
    entry = (settings.get("models") or {}).get(model)
    if not isinstance(entry, dict):
        return {"found": False, "enabled": None, "draft": None}
    return {
        "found": True,
        "enabled": bool(entry.get("dflash_enabled")),
        "draft": entry.get("dflash_draft_model"),
    }


def backup_settings(path: Path, stamp: str) -> Path:
    """Timestamped sibling copy of the settings file, taken before any write."""
    target = path.with_name(f"{path.name}.dflash-ab-{stamp}")
    shutil.copy2(path, target)
    return target


def put_settings(ctx: DflashCtx, model: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """PUT one model's settings through oMLX's admin API (0.8.0)."""
    url = f"{ctx.omlx_url}/admin/api/models/{urllib.parse.quote(model, safe='')}/settings"
    try:
        return ctx.http.json(
            url,
            method="PUT",
            payload=dict(payload),
            headers=_bearer(ctx.omlx_key),
            timeout=CALL_TIMEOUT_S,
        )
    except urllib.error.HTTPError as exc:
        raise AbortedError(f"oMLX settings PUT failed for {model}: {_http_error(exc)}") from exc
    except READ_ERRORS as exc:
        raise AbortedError(
            f"oMLX settings PUT failed for {model}: {type(exc).__name__}: {exc}"
        ) from exc


def unload_model(ctx: DflashCtx, model: str) -> dict[str, Any]:
    url = f"{ctx.omlx_url}/admin/api/models/{urllib.parse.quote(model, safe='')}/unload"
    try:
        body = ctx.http.json(
            url, method="POST", payload={}, headers=_bearer(ctx.omlx_key), timeout=CALL_TIMEOUT_S
        )
        return {"ok": True, "response": body}
    except urllib.error.HTTPError as exc:
        detail = _http_error(exc)
        return {"ok": False, "error": detail, "benign": exc.code in (400, 404)}
    except READ_ERRORS as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "benign": False}


def residents(ctx: DflashCtx) -> dict[str, Any]:
    """Loaded models oMLX reports, or the error that stopped the read."""
    try:
        payload = ctx.http.json(
            f"{ctx.omlx_url}/v1/models/status", headers=_bearer(ctx.omlx_key), timeout=10.0
        )
    except READ_ERRORS as exc:
        return {"loaded": [], "error": f"{type(exc).__name__}: {exc}"}
    models = (payload or {}).get("models") or [] if isinstance(payload, dict) else []
    loaded = []
    for row in models:
        if not isinstance(row, dict) or row.get("loaded") is False:
            continue
        size = row.get("estimated_size") or row.get("actual_size") or row.get("size")
        loaded.append(
            {
                "name": str(row.get("id") or row.get("name")),
                "size_gib": round(float(size) / 1024**3, 2) if size else None,
            }
        )
    return {"loaded": loaded, "error": None}


def model_loaded(snapshot: Mapping[str, Any], model: str) -> bool:
    return any(row.get("name") == model for row in snapshot.get("loaded") or [])


def wait_unloaded(ctx: DflashCtx, model: str, timeout: float = UNLOAD_TIMEOUT_S) -> dict[str, Any]:
    deadline = ctx.monotonic() + timeout
    while True:
        snapshot = residents(ctx)
        if snapshot["error"] is None and not model_loaded(snapshot, model):
            return {"unloaded": True, "snapshot": snapshot}
        if ctx.monotonic() >= deadline:
            return {"unloaded": False, "snapshot": snapshot}
        ctx.sleep(PROOF_POLL_S)


def _unload_and_wait(ctx: DflashCtx, model: str) -> dict[str, Any]:
    record = {"unload": unload_model(ctx, model)}
    record["wait"] = wait_unloaded(ctx, model)
    if not record["wait"]["unloaded"]:
        raise AbortedError(f"{model} did not unload; a stale engine would invalidate the arm")
    return record


def apply_delta(ctx: DflashCtx, plan: Plan) -> dict[str, Any]:
    """PUT the plan's two-key delta through the admin API; return payload and response."""
    payload = settings_delta(plan.draft)
    return {"payload": payload, "response": put_settings(ctx, plan.model, payload)}


def reload_after_delta(ctx: DflashCtx, plan: Plan, response: Mapping[str, Any]) -> dict[str, Any]:
    """Unload after a load-time settings change so the next request rebuilds the engine."""
    if not response.get("requires_reload") or response.get("auto_reloaded"):
        return {"needed": False}
    record: dict[str, Any] = {"needed": True}
    if not response.get("auto_unloaded"):
        record["unload"] = unload_model(ctx, plan.model)
    record["wait"] = wait_unloaded(ctx, plan.model)
    if not record["wait"]["unloaded"]:
        raise AbortedError(
            f"{plan.model} did not unload after the settings change; refusing to measure "
            "an engine built with the previous settings"
        )
    return record


def restore_off(ctx: DflashCtx, plan: Plan, prior: Mapping[str, Any]) -> dict[str, Any]:
    """Put both keys back to their pre-run state; never raises."""
    payload = restore_payload(prior)
    record: dict[str, Any] = {"payload": payload, "ok": False}
    try:
        record["response"] = put_settings(ctx, plan.model, payload)
        state = dflash_state(read_settings(ctx.settings_file), plan.model)
        record["settings"] = state
        record["ok"] = state.get("enabled") is False
    except Exception as exc:  # restore must not mask the run's own failure
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


# ------------------------------------------------------------------------------ log proof


def log_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_since(path: Path, offset: int) -> str:
    """Everything appended after ``offset``; a rotated (shorter) file is read whole."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(0 if size < offset else offset)
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def dflash_proof(text: str, model: str) -> str | None:
    """The first attach/proof line naming ``model`` in ``text``."""
    for line in text.splitlines():
        if model in line and any(marker in line for marker in DFLASH_PROOF_MARKERS):
            return line.strip()
    return None


def dflash_failure(text: str, model: str) -> str | None:
    """The first line saying DFlash did not take for ``model``."""
    for line in text.splitlines():
        if model in line and any(marker in line for marker in DFLASH_FAILURE_MARKERS):
            return line.strip()
    return None


def wait_for_proof(ctx: DflashCtx, model: str, offset: int) -> dict[str, Any]:
    """Poll the appended log until a DFlash attach line for ``model`` appears."""
    deadline = ctx.monotonic() + PROOF_TIMEOUT_S
    while True:
        text = read_since(ctx.server_log, offset)
        failure = dflash_failure(text, model)
        if failure:
            return {"line": None, "failure": failure}
        line = dflash_proof(text, model)
        if line:
            return {"line": line, "failure": None}
        if ctx.monotonic() >= deadline:
            return {
                "line": None,
                "failure": f"no DFlash attach line for {model} within {PROOF_TIMEOUT_S:.0f}s",
            }
        ctx.sleep(PROOF_POLL_S)


# ---------------------------------------------------------------------------- measurement


def _default_speed(ctx: DflashCtx, model: str, path: Path) -> int:
    from scripts import speed_bench

    return speed_bench.run_bench(
        "omlx",
        ctx.omlx_url,
        model,
        list(ctx.sizes),
        out=str(path),
        api_key=ctx.omlx_key,
        timeout=REQUEST_TIMEOUT_S,
    )


def _default_pipeline(ctx: DflashCtx, seat: str, path: Path) -> int:
    from scripts import speed_bench

    return speed_bench.run_bench(
        "pipeline",
        ctx.pipeline_url,
        seat,
        list(ctx.sizes),
        out=str(path),
        api_key=ctx.pipeline_key,
        timeout=REQUEST_TIMEOUT_S,
    )


def _warmup(ctx: DflashCtx, model: str) -> dict[str, Any]:
    """One tiny direct request: loads the model with whatever settings are current."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Ready?"}],
        "stream": False,
        "max_tokens": WARMUP_TOKENS,
    }
    started = time.monotonic()
    try:
        body = ctx.http.json(
            f"{ctx.omlx_url}/v1/chat/completions",
            method="POST",
            payload=payload,
            headers=_bearer(ctx.omlx_key),
            timeout=REQUEST_TIMEOUT_S,
        )
    except READ_ERRORS as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    usage = body.get("usage") or {} if isinstance(body, dict) else {}
    return {
        "ok": True,
        "wall_s": round(time.monotonic() - started, 2),
        "model": body.get("model") if isinstance(body, dict) else None,
        "load_seconds": usage.get("model_load_duration"),
    }


def _reps(ctx: DflashCtx, model: str, label: str) -> list[dict[str, Any]]:
    runner = ctx.speed or _default_speed
    reps = []
    for index in range(1, ctx.reps + 1):
        path = ctx.out_dir / f"{label}_rep{index}.json"
        path.unlink(missing_ok=True)
        try:
            returncode = runner(ctx, model, path)
        except READ_ERRORS as exc:
            returncode = 1
            payload = {"results": [], "failures": [f"{type(exc).__name__}: {exc}"]}
            reps.append({"file": path.name, "returncode": returncode, "payload": payload})
            continue
        reps.append({"file": path.name, "returncode": returncode, "payload": read_json(path) or {}})
    return reps


def summarise_reps(reps: list[dict[str, Any]], sizes: tuple[int, ...]) -> dict[str, Any]:
    """Per size: every decode/ttft sample, its median, and the max-minus-min spread."""
    summary: dict[str, Any] = {"sizes": {}, "failures": [], "reps": len(reps)}
    for rep in reps:
        payload = rep.get("payload") or {}
        summary["failures"].extend(str(item) for item in payload.get("failures") or [])
    for size in sizes:
        rows = [
            row
            for rep in reps
            for row in (rep.get("payload") or {}).get("results") or []
            if isinstance(row, dict) and row.get("size_tokens") == size
        ]
        decode = [float(row["decode_tps"]) for row in rows if row.get("decode_tps") is not None]
        ttft = [float(row["ttft_s"]) for row in rows if row.get("ttft_s") is not None]
        summary["sizes"][str(size)] = {
            "rows": len(rows),
            "decode": decode,
            "decode_median": _median(decode),
            "decode_spread": _spread(decode),
            "ttft": ttft,
            "ttft_median": _median(ttft),
            "timing_sources": sorted({str(row.get("timing_source")) for row in rows}),
            "prompt_tokens": [row.get("prompt_tokens") for row in rows],
        }
    return summary


def _pipeline_pass(ctx: DflashCtx, plan: Plan, label: str) -> dict[str, Any]:
    runner = ctx.pipeline_bench or _default_pipeline
    path = ctx.out_dir / f"{label}_pipeline.json"
    path.unlink(missing_ok=True)
    try:
        returncode = runner(ctx, plan.seat, path)
    except READ_ERRORS as exc:
        return {"returncode": 1, "rows": [], "failures": [f"{type(exc).__name__}: {exc}"]}
    payload = read_json(path) or {}
    return {
        "target": plan.seat,
        "returncode": returncode,
        "rows": payload.get("results") or [],
        "failures": payload.get("failures") or [],
        "notes": payload.get("notes") or [],
    }


# -------------------------------------------------------------------------- probe probes


def chat_request(
    ctx: DflashCtx, seat: str, prompt: str, extra: Mapping[str, Any]
) -> dict[str, Any]:
    """One non-streaming Pipeline turn; returns the body plus the route's engine/model."""
    payload = {
        "model": seat,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": PROBE_TOKENS,
        **dict(extra),
    }
    headers = {**_bearer(ctx.pipeline_key), "X-Portal-Client": "api"}
    body, response_headers = ctx.http.json_response(
        f"{ctx.pipeline_url}/v1/chat/completions",
        method="POST",
        payload=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT_S,
    )
    route = response_headers.get("x-portal-route") or ""
    backend, served = _route_parts(route)
    return {"body": body, "route": route, "backend": backend, "served_model": served}


def _message_of(body: Mapping[str, Any]) -> dict[str, Any]:
    choices = (body.get("choices") or [{}]) if isinstance(body, Mapping) else [{}]
    message = (choices[0] or {}).get("message") or {}
    return message if isinstance(message, dict) else {}


def evaluate_coding(response: Mapping[str, Any]) -> dict[str, Any]:
    message = _message_of(response.get("body") or {})
    answer = message.get("content") or ""
    return {
        "answer": answer,
        "expected": CODING_EXPECTED,
        "matched": _answer_matches(answer, CODING_EXPECTED),
        "backend": response.get("backend"),
        "served_model": response.get("served_model"),
    }


def evaluate_tool(response: Mapping[str, Any]) -> dict[str, Any]:
    """Read the caller-side tool_calls: validity, selected name, argument types."""
    message = _message_of(response.get("body") or {})
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw = function.get("arguments")
        parsed: Any = raw if isinstance(raw, dict) else None
        error = None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                error = str(exc)
        types = {key: _json_type(value) for key, value in (parsed or {}).items()}
        calls.append(
            {
                "name": function.get("name"),
                "arguments": raw,
                "valid": isinstance(parsed, dict),
                "error": error,
                "argument_types": types,
            }
        )
    first = calls[0] if calls else {}
    return {
        "tool_calls": calls,
        "selected": first.get("name"),
        "expected": PROBE_TOOL,
        "valid": bool(calls) and all(call["valid"] for call in calls),
        "argument_types": first.get("argument_types") or {},
        "content": message.get("content") or "",
        "backend": response.get("backend"),
        "served_model": response.get("served_model"),
    }


def probe_seat(ctx: DflashCtx, seat: str) -> dict[str, Any]:
    """Fixed coding prompt (no tools) and a tool-call prompt with client-only tools."""
    coding = chat_request(ctx, seat, CODING_PROMPT, {"portal_no_tools": True})
    tool = chat_request(
        ctx,
        seat,
        TOOL_PROMPT,
        {"portal_client_tools_only": True, "tools": PROBE_TOOLS, "tool_choice": "auto"},
    )
    return {"coding": evaluate_coding(coding), "tool": evaluate_tool(tool)}


# --------------------------------------------------------------------------------- verdict


def _tool_problems(off_tool: Mapping[str, Any], on_tool: Mapping[str, Any]) -> tuple[list, list]:
    problems: list[str] = []
    notes: list[str] = []
    if not on_tool.get("valid"):
        problems.append("ON tool probe returned no valid tool_call JSON")
    if on_tool.get("selected") != PROBE_TOOL:
        problems.append(
            f"ON tool probe selected {on_tool.get('selected')!r}, expected {PROBE_TOOL!r}"
        )
    if off_tool.get("selected") and on_tool.get("selected") != off_tool.get("selected"):
        problems.append(
            f"tool selection changed OFF {off_tool.get('selected')!r} → "
            f"ON {on_tool.get('selected')!r}"
        )
    changed_types = on_tool.get("argument_types") != off_tool.get("argument_types")
    if off_tool.get("argument_types") and changed_types:
        problems.append(
            f"tool argument types changed OFF {off_tool.get('argument_types')} → "
            f"ON {on_tool.get('argument_types')}"
        )
    if off_tool.get("selected") != PROBE_TOOL:
        notes.append(f"OFF tool probe selected {off_tool.get('selected')!r}")
    return problems, notes


def _coding_problems(off: Mapping[str, Any], on: Mapping[str, Any]) -> tuple[list, list]:
    problems: list[str] = []
    notes: list[str] = []
    off_matched, on_matched = bool(off.get("matched")), bool(on.get("matched"))
    if off_matched and not on_matched:
        problems.append(f"coding probe answer changed: OFF ok, ON gave {on.get('answer')!r}")
    if not off_matched and not on_matched:
        notes.append("coding probe did not match its expected value in either arm")
    if on.get("answer") and on.get("answer") != off.get("answer"):
        notes.append("coding answers differ between arms (seat samples at temperature 0.7)")
    return problems, notes


def correctness_problems(off: Mapping[str, Any], on: Mapping[str, Any]) -> tuple[list, list]:
    """Regressions from OFF to ON, plus observations that are not regressions."""
    tool_problems, tool_notes = _tool_problems(off.get("tool") or {}, on.get("tool") or {})
    coding_problems, coding_notes = _coding_problems(
        off.get("coding") or {}, on.get("coding") or {}
    )
    return tool_problems + coding_problems, tool_notes + coding_notes


def invalid_reasons(off: Mapping[str, Any], on: Mapping[str, Any]) -> list[str]:
    """A row that was not served by the intended engine/model is INVALID, not a measurement."""
    reasons: list[str] = []
    for arm in (off, on):
        pipeline = arm.get("pipeline") or {}
        for failure in pipeline.get("failures") or []:
            reasons.append(f"{arm.get('label')}: {failure}")
        for row in pipeline.get("rows") or []:
            if row.get("engine_ok") is False:
                reasons.append(
                    f"{arm.get('label')}: size {row.get('size_tokens')} served "
                    f"{row.get('backend')}/{row.get('served_model')} (wrong engine)"
                )
    return reasons


def classify(rows: list[dict[str, Any]], problems: list[str], invalid: list[str]) -> str:
    if invalid:
        return "INVALID"
    if problems:
        return "CORRECTNESS_REGRESSION"
    if not rows or any(not row.get("complete") for row in rows):
        return "INCOMPLETE"
    if all(row.get("beyond") for row in rows):
        return "PASS"
    if all(row.get("delta", 0) > 0 for row in rows):
        return "WITHIN_SPREAD"
    return "NO_GAIN"


def probe_invalid(arm: Mapping[str, Any], backend: str | None, model: str | None) -> list[str]:
    """Probe rows must be served by the seat's intended backend and model, or nothing compares."""
    reasons: list[str] = []
    probe = arm.get("probe") or {}
    for name in ("coding", "tool"):
        row = probe.get(name) or {}
        if (backend and row.get("backend") != backend) or (
            model and row.get("served_model") != model
        ):
            reasons.append(
                f"{arm.get('label')} {name} probe served "
                f"{row.get('backend')}/{row.get('served_model')} (expected {backend}/{model})"
            )
    return reasons


def compare_arms(
    off: Mapping[str, Any],
    on: Mapping[str, Any],
    sizes: tuple[int, ...],
    *,
    backend: str | None = None,
    model: str | None = None,
) -> dict:
    """Per-size gain against the run-to-run band, then the pass bar."""
    rows = []
    for size in sizes:
        key = str(size)
        base = (off.get("speed") or {}).get("sizes", {}).get(key) or {}
        trial = (on.get("speed") or {}).get("sizes", {}).get(key) or {}
        row: dict[str, Any] = {"size": size, "complete": False}
        if base.get("decode_median") is not None and trial.get("decode_median") is not None:
            delta = round(trial["decode_median"] - base["decode_median"], 2)
            band = max(base.get("decode_spread") or 0.0, trial.get("decode_spread") or 0.0)
            row = {
                "size": size,
                "complete": True,
                "off_median": base["decode_median"],
                "on_median": trial["decode_median"],
                "off_spread": base.get("decode_spread"),
                "on_spread": trial.get("decode_spread"),
                "delta": delta,
                "delta_pct": round(100 * delta / base["decode_median"], 1)
                if base["decode_median"]
                else None,
                "band": band,
                "beyond": delta > 0 and delta > band,
            }
        rows.append(row)
    problems, notes = correctness_problems(off.get("probe") or {}, on.get("probe") or {})
    invalid = invalid_reasons(off, on)
    invalid += probe_invalid(off, backend, model) + probe_invalid(on, backend, model)
    status = classify(rows, problems, invalid)
    return {
        "rows": rows,
        "problems": problems,
        "notes": notes,
        "invalid": invalid,
        "status": status,
        "passed": status == "PASS",
    }


# ----------------------------------------------------------------------------------- arms


def run_arm(
    ctx: DflashCtx,
    plan: Plan,
    *,
    label: str,
    unload: bool,
    prove: bool,
    offset: int | None = None,
) -> dict[str, Any]:
    """One arm: (re)load the model, prove its speculative state, measure, probe."""
    record: dict[str, Any] = {"label": label, "started_at": _now()}
    log_offset = log_size(ctx.server_log) if offset is None else offset
    record["residents_before"] = residents(ctx)
    if unload:
        record["unload"] = _unload_and_wait(ctx, plan.model)
    record["warmup"] = _warmup(ctx, plan.model)
    if prove:
        record["proof"] = wait_for_proof(ctx, plan.model, log_offset)
        if record["proof"]["line"] is None:
            raise AbortedError(f"DFlash is not proven on: {record['proof']['failure']}")
    else:
        text = read_since(ctx.server_log, log_offset)
        line = dflash_proof(text, plan.model)
        if line is not None:
            raise AbortedError(f"OFF arm loaded with DFlash attached: {line}")
        record["proof"] = {"line": None, "absence_ok": True, "failure": None}
    record["reps"] = _reps(ctx, plan.model, label)
    record["speed"] = summarise_reps(record["reps"], plan.sizes)
    record["pipeline"] = _pipeline_pass(ctx, plan, label)
    record["probe"] = probe_seat(ctx, plan.seat)
    record["residents_after"] = residents(ctx)
    record["finished_at"] = _now()
    return record


def resolve_targets(seat: str, model: str | None, hunt_seat: str) -> tuple[dict, dict]:
    """Resolve the seat and the hunt seat through the Pipeline's own routing config."""
    from scripts import speed_bench

    hunted = speed_bench.resolve_intended_seat(hunt_seat)
    intended = speed_bench.resolve_intended_seat(seat)
    if intended is None:
        raise AbortedError(f"seat {seat!r} does not resolve to a backend in config")
    backend, engine, target = intended
    resolved_model = model or target
    hunt = {
        "seat": hunt_seat,
        "backend": hunted[0] if hunted else None,
        "engine": hunted[1] if hunted else None,
        "model": hunted[2] if hunted else None,
        "included": bool(hunted and hunted[1] == "omlx" and hunted[2] == resolved_model),
    }
    if not hunt["included"]:
        hunt["reason"] = (
            "the plan's delta toggles only the model under test, so this seat carries no "
            "DFlash ON/OFF variable"
        )
    return {"seat": seat, "backend": backend, "engine": engine, "model": resolved_model}, hunt


def run_experiment(ctx: DflashCtx, plan: Plan) -> dict[str, Any]:
    """Preconditions → OFF → switch ON → ON → restore; always returns a renderable run."""
    run: dict[str, Any] = {
        "schema": 1,
        "stamp": ctx.out_dir.name,
        "started_at": _now(),
        "seat": plan.seat,
        "model": plan.model,
        "draft": plan.draft,
        "sizes": list(plan.sizes),
        "reps": plan.reps,
        "keep_on": plan.keep_on,
        "settings_file": str(ctx.settings_file),
        "server_log": str(ctx.server_log),
        "hunt": plan.hunt,
        "abort": None,
    }
    switched = False
    try:
        if not Path(plan.draft).is_dir() or not (Path(plan.draft) / "config.json").is_file():
            raise AbortedError(f"DFlash draft checkpoint is missing a config.json: {plan.draft}")
        try:
            run["backup"] = str(backup_settings(ctx.settings_file, ctx.out_dir.name))
        except OSError as exc:
            raise AbortedError(f"cannot back up {ctx.settings_file}: {exc}") from exc
        prior = dflash_state(read_settings(ctx.settings_file), plan.model)
        if not prior["found"]:
            raise AbortedError(f"{plan.model} has no entry in {ctx.settings_file}")
        if prior["enabled"]:
            raise AbortedError(
                f"DFlash is already enabled for {plan.model}; the OFF arm needs it off"
            )
        run["prior"] = prior
        run["precondition"] = precondition(ctx)
        if not run["precondition"]["ok"]:
            raise AbortedError("precondition failed: " + "; ".join(run["precondition"]["problems"]))
        run["off"] = run_arm(ctx, plan, label="off", unload=True, prove=False)
        switch_offset = log_size(ctx.server_log)
        switched = True  # the next write may land: restoring the prior state is idempotent
        run["switch_on"] = apply_delta(ctx, plan)
        run["switch_on"]["reload"] = reload_after_delta(ctx, plan, run["switch_on"]["response"])
        run["on"] = run_arm(ctx, plan, label="on", unload=False, prove=True, offset=switch_offset)
        run["comparison"] = compare_arms(
            run["off"], run["on"], plan.sizes, backend=plan.backend or None, model=plan.model
        )
    except KeyboardInterrupt:
        run["abort"] = "interrupted (Ctrl-C); DFlash restored to its prior state"
    except Exception as exc:  # every failure still ends in a receipt and a restore
        run["abort"] = f"{type(exc).__name__}: {exc}"
    finally:
        keep = plan.keep_on and bool((run.get("comparison") or {}).get("passed"))
        run["kept_on"] = keep
        if switched and not keep:
            run["restore"] = restore_off(ctx, plan, run.get("prior") or {})
        run["finished_at"] = _now()
    return run


# -------------------------------------------------------------------------------- receipt


def _fmt(value: Any, spec: str = ".1f") -> str:
    return "-" if value is None else format(value, spec)


def _identity_lines(run: Mapping[str, Any]) -> list[str]:
    hunt = run.get("hunt") or {}
    lines = [
        f"- seat: `{run.get('seat')}`",
        f"- model under test: `{run.get('model')}` (oMLX; direct speed rows + one Pipeline pass)",
        f"- per arm: unload the model, one warmup request reloads it, then "
        f"`speed_bench --engine omlx --model {run.get('model')} --sizes "
        f"{','.join(str(size) for size in run.get('sizes') or [])}` × {run.get('reps') or '?'} "
        f"and one `speed_bench --engine pipeline --workspace {run.get('seat')}`",
        f"- DFlash draft: `{run.get('draft')}`",
        f"- settings: `{run.get('settings_file')}`"
        + (f" (backup `{run['backup']}`)" if run.get("backup") else ""),
    ]
    if hunt.get("seat"):
        state = "measured" if hunt.get("included") else "not part of the A/B"
        lines.append(
            f"- hunt seat `{hunt['seat']}` → `{hunt.get('model')}` on "
            f"{hunt.get('backend')} ({hunt.get('engine')}) — {state}"
            + (f": {hunt['reason']}" if hunt.get("reason") else "")
        )
    if run.get("reps"):
        lines.append(
            f"- raw rows: `run.json` plus `off_rep1..{run['reps']}.json`, "
            f"`on_rep1..{run['reps']}.json` and `off_pipeline.json` / `on_pipeline.json`"
        )
    return lines


def _precondition_lines(run: Mapping[str, Any]) -> list[str]:
    precondition = run.get("precondition")
    if not precondition:
        return ["## Preconditions", "", "Not reached.", ""]
    reclaim = precondition.get("reclaim") or {}
    quiet = precondition.get("host_quiet") or {}
    unloads = precondition.get("ollama_unloads") or []
    lines = [
        "## Preconditions",
        "",
        f"- Ollama residents before: {precondition.get('ollama_before') or []}"
        f" · unloads ok: {sum(1 for row in unloads if row.get('ok'))}/{len(unloads)}",
        f"- reclaim-idle need_gib={RECLAIM_NEED_GIB}: {'ok' if reclaim.get('ok') else reclaim}",
        f"- host_quiet: exit {quiet.get('returncode')}",
    ]
    for problem in precondition.get("problems") or []:
        lines.append(f"- blocker: {problem}")
    lines.append("")
    return lines


def _speed_failure_lines(run: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for arm in ("off", "on"):
        for failure in ((run.get(arm) or {}).get("speed") or {}).get("failures") or []:
            lines.append(f"- {arm} speed failure: {failure}")
    return lines


def _speed_lines(run: Mapping[str, Any]) -> list[str]:
    comparison = run.get("comparison") or {}
    rows = comparison.get("rows") or []
    failures = _speed_failure_lines(run)
    if not rows:
        return [
            "## Decode tok/s",
            "",
            "Not measured (run aborted before both arms completed).",
            "",
            *failures,
            "",
        ]
    lines = [
        f"## Decode tok/s (median of {run.get('reps')}, spread = max − min; pass metric)",
        "",
        "| size | OFF median | OFF spread | ON median | ON spread | delta | delta % | beyond spread |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if not row.get("complete"):
            lines.append(f"| {row.get('size')} | - | - | - | - | - | - | incomplete |")
            continue
        lines.append(
            f"| {row['size']} | {_fmt(row['off_median'])} | {_fmt(row['off_spread'])} "
            f"| {_fmt(row['on_median'])} | {_fmt(row['on_spread'])} | {_fmt(row['delta'], '+.2f')} "
            f"| {_fmt(row.get('delta_pct'), '+.1f')} | {'yes' if row['beyond'] else 'no'} |"
        )
    lines.append("")
    if failures:
        lines.extend(failures)
        lines.append("")
    return lines


def _ttft_lines(run: Mapping[str, Any]) -> list[str]:
    lines = ["## TTFT (s, median of reps; engine-reported or client-measured)", ""]
    lines += ["| size | OFF | ON | timing source |", "| --- | --- | --- | --- |"]
    off = ((run.get("off") or {}).get("speed") or {}).get("sizes") or {}
    on = ((run.get("on") or {}).get("speed") or {}).get("sizes") or {}
    for size in run.get("sizes") or []:
        key = str(size)
        base, trial = off.get(key) or {}, on.get(key) or {}
        sources = sorted(
            set(base.get("timing_sources") or []) | set(trial.get("timing_sources") or [])
        )
        lines.append(
            f"| {size} | {_fmt(base.get('ttft_median'), '.2f')} "
            f"| {_fmt(trial.get('ttft_median'), '.2f')} | {', '.join(sources) or '-'} |"
        )
    lines.append("")
    return lines


def _served_lines(run: Mapping[str, Any]) -> list[str]:
    lines = ["## Served engine / model (a wrong engine makes the run INVALID)", ""]
    for label in ("off", "on"):
        arm = run.get(label) or {}
        if not arm:
            lines.append(f"- {label}: not measured")
            continue
        loaded = [row.get("name") for row in (arm.get("residents_after") or {}).get("loaded") or []]
        lines.append(
            f"- {label} direct oMLX rows: engine `omlx`, model `{run.get('model')}` "
            f"(requested by name; loaded after the arm: {', '.join(loaded) or 'none'})"
        )
        for row in (arm.get("pipeline") or {}).get("rows") or []:
            lines.append(
                f"- {label} `{row.get('size_tokens')}` tokens via `{run.get('seat')}`: "
                f"{row.get('backend')} ({row.get('served_engine') or 'unknown'}) / "
                f"{row.get('served_model')} — engine_ok={row.get('engine_ok')}"
            )
    lines.append("")
    return lines


def _proof_lines(run: Mapping[str, Any]) -> list[str]:
    lines = ["## DFlash attach proof", ""]
    on_proof = ((run.get("on") or {}).get("proof") or {}).get("line")
    off_proof = (run.get("off") or {}).get("proof") or {}
    switch = run.get("switch_on") or {}
    response = switch.get("response") or {}
    prior = run.get("prior") or {}
    delta = switch.get("payload") or settings_delta(run.get("draft") or DEFAULT_DRAFT)
    lines += [
        "```diff",
        "-" + json.dumps(restore_payload(prior), sort_keys=True),
        "+" + json.dumps(delta, sort_keys=True),
        "```",
    ]
    if response:
        lines.append(
            f"- settings PUT: requires_reload={response.get('requires_reload')}, "
            f"auto_unloaded={response.get('auto_unloaded')}, "
            f"auto_reloaded={response.get('auto_reloaded')}"
        )
    lines.append(f"- ON: {'`' + on_proof + '`' if on_proof else 'NOT PROVEN'}")
    lines.append(
        "- OFF: "
        + (
            "no DFlash attach line for the model after the OFF reload"
            if off_proof.get("absence_ok")
            else "absence not checked"
        )
    )
    restore = run.get("restore")
    if restore and restore.get("settings"):
        state = restore["settings"]
        lines.append(
            f"- restored settings: dflash_enabled={state.get('enabled')} "
            f"dflash_draft_model={state.get('draft')!r}"
        )
    lines.append("")
    return lines


def _tool_line(label: str, probe: Mapping[str, Any]) -> str:
    calls = probe.get("tool_calls") or []
    return (
        f"- tool prompt ({label}): selected={probe.get('selected')!r} "
        f"valid={probe.get('valid')} argument_types={probe.get('argument_types')} "
        f"calls={len(calls)} served={probe.get('backend')}/{probe.get('served_model')}"
    )


def _probe_lines(run: Mapping[str, Any]) -> list[str]:
    off = (run.get("off") or {}).get("probe") or {}
    on = (run.get("on") or {}).get("probe") or {}
    lines = ["## Correctness probe (same prompts, sampling and tool schemas in both arms)", ""]
    if not off or not on:
        return [*lines, "Not measured (run aborted before both arms completed).", ""]
    off_coding = (off.get("coding") or {}).get("answer") or ""
    on_coding = (on.get("coding") or {}).get("answer") or ""
    lines += [
        f"- coding prompt (expected `{CODING_EXPECTED}`): "
        f"OFF matched={bool((off.get('coding') or {}).get('matched'))} "
        f"`{off_coding[:120]}` · "
        f"ON matched={bool((on.get('coding') or {}).get('matched'))} `{on_coding[:120]}` "
        f"· served {(on.get('coding') or {}).get('backend')}/"
        f"{(on.get('coding') or {}).get('served_model')}"
    ]
    lines.append(_tool_line("OFF", off.get("tool") or {}))
    lines.append(_tool_line("ON", on.get("tool") or {}))
    lines.append("")
    return lines


def _verdict_lines(run: Mapping[str, Any]) -> list[str]:
    comparison = run.get("comparison") or {}
    lines = ["## Verdict against the plan's pass bar", ""]
    lines.append(f"**{comparison.get('status') or 'NOT MEASURED'}**")
    lines.append("")
    lines.append(
        "Bar: a positive decode tok/s gain larger than the run-to-run spread at every "
        "size, and no correctness regression, with every row served by the intended "
        "engine/model."
    )
    lines.append("")
    if run.get("abort"):
        lines.append(f"- aborted: {run['abort']}")
    for row in comparison.get("rows") or []:
        if row.get("complete"):
            lines.append(
                f"- size {row['size']}: delta {_fmt(row['delta'], '+.2f')} tok/s vs band "
                f"{_fmt(row['band'], '.2f')} — {'beyond spread' if row['beyond'] else 'inside spread'}"
            )
        else:
            lines.append(f"- size {row['size']}: no measurement")
    for problem in comparison.get("problems") or []:
        lines.append(f"- correctness regression: {problem}")
    for problem in comparison.get("invalid") or []:
        lines.append(f"- invalid row: {problem}")
    for note in comparison.get("notes") or []:
        lines.append(f"- note: {note}")
    restore = run.get("restore")
    if run.get("kept_on"):
        lines.append("- DFlash left ON (--keep-on and the pass bar was met)")
    elif restore:
        lines.append(
            f"- DFlash restored OFF: {'ok' if restore.get('ok') else 'FAILED — ' + str(restore)}"
        )
    lines.append("")
    return lines


def render_receipt(run: Mapping[str, Any]) -> str:
    lines = [f"# DFlash2 A/B — {run.get('stamp')}", ""]
    lines += _identity_lines(run)
    lines.append("")
    lines += _precondition_lines(run)
    lines += _speed_lines(run)
    lines += _ttft_lines(run)
    lines += _served_lines(run)
    lines += _proof_lines(run)
    lines += _probe_lines(run)
    lines += _verdict_lines(run)
    return "\n".join(lines).rstrip() + "\n"


def write_receipt(run: Mapping[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "run.json", run)
    receipt = out_dir / "receipt.md"
    receipt.write_text(render_receipt(run), encoding="utf-8")
    return receipt


# ----------------------------------------------------------------------------------- main


def _sizes(spec: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part) for part in spec.split(",") if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--sizes must be integers, got {spec!r}") from exc
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("--sizes must be positive integers")
    return values


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unattended DFlash2 on/off A/B for one oMLX seat, ending in one receipt."
    )
    parser.add_argument("--seat", default=DEFAULT_SEAT, help="workspace id or persona slug")
    parser.add_argument("--model", default=None, help="oMLX model id (default: the seat's pin)")
    parser.add_argument("--draft", default=DEFAULT_DRAFT, help="DFlash draft checkpoint path")
    parser.add_argument("--sizes", type=_sizes, default=DEFAULT_SIZES)
    parser.add_argument("--reps", type=int, default=DEFAULT_REPS)
    parser.add_argument(
        "--settings-file", default=str(Path.home() / ".omlx" / "model_settings.json")
    )
    parser.add_argument("--server-log", default=str(Path.home() / ".omlx" / "logs" / "server.log"))
    parser.add_argument("--out-root", default=str(Path.home() / ".portal5" / "dflash_ab"))
    parser.add_argument(
        "--keep-on",
        action="store_true",
        help="leave DFlash on only when the pass bar was met",
    )
    return parser


def _signal_handler(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.reps < 1:
        _parser().error("--reps must be at least 1")
    out_dir = Path(args.out_root).expanduser() / _stamp()
    ctx = context(out_dir, args)
    run: dict[str, Any] = {"schema": 1, "stamp": out_dir.name, "started_at": _now()}
    signal.signal(signal.SIGTERM, _signal_handler)
    try:
        targets, hunt = resolve_targets(args.seat, args.model, HUNT_SEAT)
        plan = Plan(
            seat=args.seat,
            model=targets["model"],
            draft=args.draft,
            sizes=tuple(args.sizes),
            reps=args.reps,
            keep_on=args.keep_on,
            hunt=hunt,
            backend=targets["backend"],
        )
        run = run_experiment(ctx, plan)
    except (AbortedError, KeyboardInterrupt) as exc:
        run["abort"] = str(exc) or "interrupted"
        run["finished_at"] = _now()
    receipt = write_receipt(run, out_dir)
    status = (run.get("comparison") or {}).get("status") or "ABORTED"
    print(f"{status} receipt={receipt}")
    if status == "ABORTED":
        return 3
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
