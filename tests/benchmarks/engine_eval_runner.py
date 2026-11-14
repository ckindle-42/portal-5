#!/usr/bin/env python3
"""Run managed engine-eval canaries and guard Stage 3 receipts."""

from __future__ import annotations

import argparse
import ast
import contextlib
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from portal.platform.inference.cluster_backends import BackendRegistry
from scripts import host_quiet
from tests.benchmarks import bench_engine_h2h as h2h
from tests.benchmarks import engine_eval_instrument as instrument

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name("engine_eval_protocol_20261113.yaml")
OPENAI_MODELS_SOURCE = "https://platform.openai.com/docs/api-reference/models/list"
OPENAI_CHAT_SOURCE = "https://platform.openai.com/docs/api-reference/chat/create"


class Stage3BlockedError(RuntimeError):
    """A required gate or protocol mapping does not support this run."""


def data_root() -> Path:
    """Return the required external evidence directory."""
    raw = os.environ.get("PORTAL_DATA_ROOT")
    if not raw:
        raise Stage3BlockedError("PORTAL_DATA_ROOT is required for raw engine-eval output")
    root = Path(raw).expanduser().resolve()
    if root == REPO or REPO in root.parents:
        raise Stage3BlockedError("PORTAL_DATA_ROOT must be outside the repository")
    return root


def _configure_results(root: Path) -> None:
    """Move the existing harness state and logs below PORTAL_DATA_ROOT."""
    h2h.RESULTS = root / "tests" / "benchmarks" / "results" / "engine_h2h"
    h2h.STATE_DIR = h2h.RESULTS / "state"


def _bench_workspaces() -> dict[str, Any]:
    path = REPO / "config" / "bench_workspaces.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("workspaces") or {}


def _cell_id(cell: dict[str, Any]) -> str:
    return "--".join(str(cell[key]) for key in ("engine", "mode", "seat"))


def canary_receipt_path(root: Path, build: str, cell: dict[str, Any]) -> Path:
    """Path to one immutable canary receipt for a commit and cell."""
    return root / "engine_eval" / "canaries" / build / f"{_cell_id(cell)}.json"


def require_valid_canary(root: Path, build: str, cell: dict[str, Any]) -> dict[str, Any]:
    """Read a cell receipt, refusing missing, stale, or invalid evidence."""
    path = canary_receipt_path(root, build, cell)
    if not path.is_file():
        raise Stage3BlockedError(f"no canary receipt for {_cell_id(cell)} on current build {build}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("build") != build:
        raise Stage3BlockedError(
            f"canary receipt for {_cell_id(cell)} is not for the current build"
        )
    if receipt.get("skipped"):
        raise Stage3BlockedError(f"{_cell_id(cell)} is not installed: {receipt.get('reason')}")
    if receipt.get("valid") is not True:
        raise Stage3BlockedError(f"canary invalid for {_cell_id(cell)}: {receipt.get('failures')}")
    return receipt


def require_seat_canary(root: Path, build: str, seat: str) -> dict[str, Any]:
    """A seat may run its incumbent pair when any current-build cell for it is valid."""
    directory = root / "engine_eval" / "canaries" / build
    if not directory.is_dir():
        raise Stage3BlockedError(f"no canary directory for current build {build}")
    for path in sorted(directory.glob("*.json")):
        if path.name == "table.json":
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cell = receipt.get("cell") or {}
        if (
            cell.get("seat") == seat
            and receipt.get("valid") is True
            and receipt.get("build") == build
        ):
            return receipt
    raise Stage3BlockedError(f"no valid canary for seat {seat} on current build {build}")


def _is_external(cell: dict[str, Any]) -> bool:
    return cell.get("engine_kind") == "external"


def _gate_canary(root: Path, build: str, cell: dict[str, Any]) -> dict[str, Any]:
    if _is_external(cell):
        return require_seat_canary(root, build, str(cell["seat"]))
    return require_valid_canary(root, build, cell)


def current_build() -> str:
    """Return the lane HEAD used to key the canary gate."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, timeout=10
    ).strip()


def candidate_cells() -> list[dict[str, Any]]:
    """Expand approved seats over managed registry engines and declared modes."""
    cfg = h2h.load_config()
    workspaces = _bench_workspaces()
    matrix = cfg.get("engine_eval") or {}
    excluded = {
        (item["seat"], item["engine"], item["mode"]): item["reason"]
        for item in matrix.get("excluded_cells") or []
    }
    cells = []
    for seat, mapping in (matrix.get("seats") or {}).items():
        workspace = mapping["workspace"]
        workspace_cfg = workspaces[workspace]
        model = mapping["model"]
        hint = str(workspace_cfg["model_hint"])
        for engine, engine_cfg in cfg["engines"].items():
            if engine_cfg.get("kind") != "managed" or not h2h.model_supports_engine(
                cfg, model, engine
            ):
                continue
            modes = ["plain"]
            if h2h.spec_entry(cfg, model, engine) is not None:
                modes.append("spec")
            for mode in modes:
                if (seat, engine, mode) in excluded:
                    continue
                cells.append(
                    _make_cell(cfg, engine, engine_cfg, mode, seat, mapping, workspace_cfg, hint)
                )
    return cells


def _missing_binary(argv: list[str], cwd: str | None) -> str | None:
    """The executable the argv names when it is absent from this host."""
    if not argv:
        return None
    exe = argv[0]
    if "/" in exe:
        path = Path(os.path.expanduser(exe))
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
        return None if path.exists() else str(path)
    return None if shutil.which(exe) else exe


def _make_cell(
    cfg: dict,
    engine: str,
    engine_cfg: dict,
    mode: str,
    seat: str,
    mapping: dict,
    workspace_cfg: dict,
    hint: str,
) -> dict[str, Any]:
    """Resolve the process argv and static route identity for one cell."""
    model = mapping["model"]
    try:
        argv, cwd = h2h.launch_command(cfg, engine, model, mode)
        launch_error = None
    except SystemExit as exc:
        argv, cwd, launch_error = [], None, str(exc)
    engine_cfg = cfg["engines"][engine]
    port = int(engine_cfg["port"])
    missing = None
    if not launch_error and not engine_cfg.get("install"):
        missing = _missing_binary(argv, cwd)
    return {
        "seat": seat,
        "workspace": mapping["workspace"],
        "engine": engine,
        "engine_kind": engine_cfg["kind"],
        "mode": mode,
        "model": model,
        "model_hint": hint,
        "expected_model": hint,
        "backend": "eval-openai" if port == 11234 else f"eval-openai-{engine}",
        "port": port,
        "base": h2h.base_url(cfg, engine),
        "argv": argv,
        "cwd": cwd,
        "launch_error": launch_error,
        "not_installed": (
            f"{engine} not installed: {missing} is missing and the registry has no install step"
            if missing
            else None
        ),
        "workspace_settings": workspace_cfg,
    }


def _candidate_residency(cfg: dict) -> dict[str, dict[str, int] | None]:
    """Capture loaded model identities from both production engines and all ports."""
    residents = {
        name: instrument._resident_snapshot(name, h2h.base_url(cfg, name))
        for name in ("ollama", "omlx")
    }
    for engine, entry in cfg["engines"].items():
        if entry.get("kind") != "managed":
            continue
        pid = h2h.pid_on_port(int(entry["port"]))
        if not pid:
            residents[engine] = {}
            continue
        state_file = h2h._state_file(engine)
        if not state_file.is_file():
            residents[engine] = {f"listener:{pid}": pid}
            continue
        state = json.loads(state_file.read_text(encoding="utf-8"))
        model = state.get("model")
        mode = state.get("mode", "plain")
        try:
            served = h2h.served_id(cfg, engine, model, mode) if model else f"listener:{pid}"
        except (KeyError, SystemExit):
            served = f"listener:{pid}"
        residents[engine] = {str(served): pid}
    return residents


def _production_loaded_models(engine: str, cfg: dict[str, Any]) -> list[str]:
    base = h2h.base_url(cfg, engine)
    endpoint = "/api/ps" if engine == "ollama" else "/v1/models/status"
    payload = h2h.http_json(f"{base}{endpoint}", timeout=15)
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise ValueError(f"{engine} {endpoint} did not return a models list")
    loaded = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{engine} {endpoint} returned a malformed model row")
        if engine == "omlx" and row.get("loaded") is not True:
            continue
        model = row.get("name") or row.get("model") if engine == "ollama" else row.get("id")
        if not isinstance(model, str) or not model:
            raise ValueError(f"{engine} {endpoint} returned a loaded model without an id")
        loaded.append(model)
    return loaded


UNLOAD_SETTLE_TIMEOUT_S = 60.0


def _unload_production_model(engine: str, model: str, cfg: dict[str, Any]) -> None:
    base = h2h.base_url(cfg, engine)
    if engine == "ollama":
        h2h.http_json(
            f"{base}/api/generate",
            {"model": model, "keep_alive": 0, "stream": False},
            timeout=60,
        )
        return
    try:
        h2h.http_json(f"{base}/v1/models/{quote(model, safe='')}/unload", {}, timeout=60)
    except urllib.error.HTTPError as exc:
        # oMLX queues an unload behind in-flight work and answers a repeat POST
        # for that model with 400 "Model not loaded"; the release still lands.
        body = exc.read().decode("utf-8", "replace")
        if exc.code != 400 or "not loaded" not in body.lower():
            raise
        print(f"pre-canary | unload already queued | {engine} | {model}", flush=True)


def _wait_model_unloaded(engine: str, model: str, cfg: dict[str, Any]) -> bool:
    """Wait until the engine's own loaded set no longer names ``model``."""
    deadline = time.monotonic() + UNLOAD_SETTLE_TIMEOUT_S
    while True:
        if model not in _production_loaded_models(engine, cfg):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _prepare_production_models(cfg: dict[str, Any]) -> dict[str, Any]:
    """Unload and verify every model resident on the two production engines."""
    result: dict[str, Any] = {
        "valid": True,
        "loaded": {},
        "unloaded": {"omlx": [], "ollama": []},
        "remaining": {},
        "failures": [],
    }
    for engine in ("omlx", "ollama"):
        try:
            loaded = _production_loaded_models(engine, cfg)
            result["loaded"][engine] = loaded
        except Exception as exc:
            loaded = []
            result["loaded"][engine] = None
            result["failures"].append(f"{engine} loaded-model read failed: {exc}")
        if not loaded:
            print(f"pre-canary | no models loaded | {engine}", flush=True)
        for model in loaded:
            try:
                _unload_production_model(engine, model, cfg)
                if not _wait_model_unloaded(engine, model, cfg):
                    raise TimeoutError(f"not released within {UNLOAD_SETTLE_TIMEOUT_S:.0f}s")
                result["unloaded"][engine].append(model)
                print(f"pre-canary | unloaded | {engine} | {model}", flush=True)
            except Exception as exc:
                result["failures"].append(f"{engine} unload failed for {model}: {exc}")
                print(f"pre-canary | unload failed | {engine} | {model} | {exc}", flush=True)
        try:
            remaining = _production_loaded_models(engine, cfg)
            result["remaining"][engine] = remaining
            if remaining:
                result["failures"].append(f"{engine} still has loaded model(s): {remaining}")
        except Exception as exc:
            result["remaining"][engine] = None
            result["failures"].append(f"{engine} unload verification failed: {exc}")
    result["valid"] = not result["failures"]
    return result


class CandidateHTTPError(RuntimeError):
    """An upstream or pipeline HTTP response that invalidated a candidate cell."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body[:1000]


def _models_payload(base: str) -> dict[str, Any]:
    """Read the engine's raw model-list response for settings and identity evidence."""
    status, payload, raw = h2h._models_response(base)
    if status != 200:
        raise CandidateHTTPError(status, raw)
    return {"status": status, "json": payload, "raw": raw}


def _model_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept only the registered OpenAI collection or mlx-serve's model rows."""
    for key in ("data", "models"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _model_row(payload: dict[str, Any], expected_model: str) -> dict[str, Any]:
    return next((row for row in _model_rows(payload) if row.get("id") == expected_model), {})


def _candidate_memory(
    vm_before: str,
    port: int,
    engine: str,
    engine_cfg: dict[str, Any],
    model_row: dict[str, Any],
) -> dict[str, Any]:
    """Compare one engine-specific residency reading with the vm_stat wired delta."""
    try:
        vm_after = subprocess.check_output(["vm_stat"], text=True, timeout=10)
        rows = instrument.parse_ps_tree(
            subprocess.check_output(["ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=10)
        )
    except (OSError, subprocess.CalledProcessError):
        vm_after, rows = "", []
    root = h2h.pid_on_port(port)
    rss = instrument.tree_rss_gb(rows, root) if root else None
    footprint = None
    if root and engine_cfg.get("requires") != "gguf":
        try:
            raw_footprint = subprocess.check_output(
                ["footprint", "-p", str(root)], text=True, timeout=10
            )
            footprint = instrument.parse_footprint(raw_footprint).get("phys_footprint_gb")
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    delta = (
        instrument.vm_deltas_gb(
            instrument.parse_vm_stat(vm_before), instrument.parse_vm_stat(vm_after)
        )
        or {}
    )
    resident_bytes = next(
        (
            model_row.get(key)
            for key in ("bytes_resident", "resident_bytes", "memory_bytes")
            if isinstance(model_row.get(key), (int, float)) and model_row[key] > 0
        ),
        None,
    )
    if engine_cfg.get("requires") == "gguf":
        primary, source = rss, "process-tree RSS (llama.cpp maps the GGUF into its process)"
        resident_field = None
    elif resident_bytes is not None:
        primary = float(resident_bytes) / (1024**3)
        source = "GET /v1/models bytes_resident"
        resident_field = "bytes_resident"
    else:
        primary, source = footprint, "macOS footprint phys_footprint"
        resident_field = "phys_footprint"
    return {
        "tree_walked": root is not None and rss is not None,
        "tree_rss_gb": rss,
        "phys_footprint_gb": footprint,
        "engine_resident_bytes": resident_bytes,
        "engine_resident_decimal_gb": resident_bytes / 1_000_000_000
        if resident_bytes is not None
        else None,
        "engine_weight_gb": primary,
        "engine_weight_unit": "GiB",
        "engine_weight_field": resident_field,
        "engine_weight_source": source,
        "engine_weight_reason": "sampled after the first completed request; compared in GiB with independent vm_stat wired pages",
        "engine": engine,
        **delta,
    }


THINK_OFF_PROMPT = "Reply with exactly OK in visible text."
TOOL_CALL_PROMPT = "Invoke get_weather for Boston."
PARITY_PROMPT = "Reply with exactly OK in visible text and invoke get_weather for Boston."
TOOL_TURN_PROMPT = "Invoke get_weather for Boston."
TOOL_TURN_FOLLOW_UP = "Using the weather result, reply with one sentence giving the temperature."
TOOL_TURN_RESULT = "18C and clear."
# A rendered tool block is thousands of tokens; this floor separates it from the
# user-prompt differences between the no-tools and tools probes.
TOOL_RENDER_MIN_TOKENS = 50
FORCED_CHOICE_RULE = (
    "honoured means the forced call came back with no prose: prose under a named tool_choice "
    "is recorded as the engine not forcing the function"
)
_GET_WEATHER_CHOICE = {"type": "function", "function": {"name": "get_weather"}}


def _probe_body(cell: dict[str, Any], prompt: str, extra: dict[str, Any]) -> dict[str, Any]:
    """One Pipeline probe body carrying this cell's seat defaults."""
    return {
        "model": cell["workspace"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "think": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "portal_backend": cell["backend"],
        **extra,
    }


def _candidate_body(cell: dict[str, Any]) -> dict[str, Any]:
    """The greedy pair parity compares: this seat's tools and a forced function."""
    return _probe_body(
        cell,
        PARITY_PROMPT,
        {"tools": instrument._TOOL_SPEC, "tool_choice": _GET_WEATHER_CHOICE},
    )


def _think_off_body(cell: dict[str, Any]) -> dict[str, Any]:
    """Think-off alone. An explicit empty tools list switches tools and tool_choice off."""
    return _probe_body(cell, THINK_OFF_PROMPT, {"tools": []})


def _tool_call_body(cell: dict[str, Any]) -> dict[str, Any]:
    """The tool-call check alone, under a named forced function."""
    return _probe_body(
        cell,
        TOOL_CALL_PROMPT,
        {"tools": instrument._TOOL_SPEC, "tool_choice": _GET_WEATHER_CHOICE},
    )


def _forced_tool_choice(engine: str, tool_row: dict[str, Any]) -> dict[str, Any]:
    """Whether a named forced function was enforced, not merely requested."""
    message = tool_row["message"]
    reply = instrument._visible_reply(message)
    tool = instrument.tool_from_message(message)
    if not tool.get("ok"):
        honoured = False
        why = f"no valid get_weather call: {tool.get('why') or tool}"
    elif reply.strip():
        honoured = False
        why = f"prose {reply.strip()[:40]!r} accompanied the forced call"
        if engine == "mlx_lm.server":
            why += (
                "; mlx_lm/server.py _tokenize passes only tools to apply_chat_template, "
                "so tool_choice never reaches the template"
            )
    else:
        honoured = True
        why = "the forced call came back with no prose"
    return {
        "requested": _GET_WEATHER_CHOICE,
        "honoured": honoured,
        "evidence": why,
        "rule": FORCED_CHOICE_RULE,
    }


@functools.lru_cache(maxsize=1)
def _tool_registry() -> BackendRegistry:
    """The registry whose tool map the Pipeline consults, eval engines included."""
    return BackendRegistry(
        config_path=str(REPO / "config" / "backends.yaml"), include_eval_backends=True
    )


@functools.lru_cache(maxsize=32)
def _workspace_tools(workspace: str) -> tuple[str, ...]:
    """The workspace's declared tools, from config/bench_workspaces.yaml."""
    declared = (_bench_workspaces().get(workspace) or {}).get("tools") or []
    return tuple(str(item) for item in declared)


def _tool_surface_reason(cell: dict[str, Any]) -> str | None:
    """Why this seat cannot receive tools at all, or None when it can.

    The Pipeline strips ``tools``/``tool_choice`` when the workspace declares no
    tools or the model is not declared tool-capable, so a forced call cannot be
    delivered and is not the engine's to pass.
    """
    if not _workspace_tools(str(cell.get("workspace") or "")):
        return f"{cell['workspace']} declares no tools in config/bench_workspaces.yaml"
    if not _tool_registry().model_supports_tools(str(cell.get("expected_model") or "")):
        return f"{cell['expected_model']!r} is declared supports_tools: false"
    return None


def _grade_cell_preflight(
    cell: dict[str, Any], think_row: dict[str, Any], tool_row: dict[str, Any]
) -> dict[str, Any]:
    """Grade the separate think-off and tool-call requests, then record the choice."""
    served = think_row.get("engine_model")
    not_applicable = _tool_surface_reason(cell)
    graded = instrument.grade_preflight(
        instrument._visible_reply(think_row["message"]),
        instrument.tool_from_message(tool_row["message"]),
        served if served == cell["expected_model"] else None,
        tool_not_applicable=not_applicable,
    )
    graded["separate_requests"] = True
    graded["requests"] = {
        "think_off": {"prompt": THINK_OFF_PROMPT, "tools": "none (explicit empty list)"},
        "tool_call": {"prompt": TOOL_CALL_PROMPT, "tool_choice": "get_weather"},
    }
    graded["tool_choice"] = (
        {**instrument._exclude(f"not applicable: {not_applicable}"), "applicable": False}
        if not_applicable
        else _forced_tool_choice(cell["engine"], tool_row)
    )
    return graded


def _candidate_tokenizer(cfg: dict, cell: dict[str, Any]) -> Path | None:
    """Resolve the loaded checkpoint tokenizer from the benchmark registry."""
    entry = cfg["models"][cell["model"]]
    if cfg["engines"][cell["engine"]].get("requires") == "gguf":
        tokenizer = {"repo": entry["source_repo"], "file": "tokenizer.json"}
        try:
            return Path(h2h.cached_hf_file(tokenizer, cell["model"]))
        except SystemExit:
            return None
    directory = Path(h2h.model_root(cfg, cell["engine"])) / h2h.model_dir_for(
        cfg, cell["model"], cell["engine"], cell["mode"]
    )
    return instrument.resolve_tokenizer(cell["engine"], directory, None)


def _candidate_template(cfg: dict, cell: dict[str, Any]) -> dict[str, Any]:
    """Check templates only for cells that load the same registered checkpoint."""
    entry = cfg["models"][cell["model"]]
    is_gguf = cfg["engines"][cell["engine"]].get("requires") == "gguf"
    same = is_gguf or (
        cell["mode"] == "plain"
        and h2h.model_dir_for(cfg, cell["model"], cell["engine"], cell["mode"]) == entry.get("mlx")
    )
    if not same:
        return {"same_checkpoint": False}
    try:
        result = h2h.template_check(cfg, cell["engine"], cell["model"], cell["mode"])
    except (KeyError, OSError, SystemExit) as exc:
        return {"same_checkpoint": True, "match": None, "note": str(exc)}
    return {
        "same_checkpoint": True,
        "match": result.get("ok") if isinstance(result.get("ok"), bool) else None,
        "note": str(result.get("note") or ""),
    }


def _candidate_prompt_token_count(engine: str, log_text: str) -> int | None:
    """The last prompt count the engine logged. Per-request selection is in
    ``_parity_prompt_tokens``; this is the engine-format parser."""
    if engine == "mlx-serve":
        matches = _MLX_SERVE_PROMPT_RE.findall(log_text)
    elif engine == "mlx_lm.server":
        matches = re.findall(r"Prompt processing progress: \d+/(\d+)", log_text)
    else:
        matches = re.findall(r"\bprompt_tokens[=: ]+(\d+)\b", log_text)
    return int(matches[-1]) if matches else None


def _engine_prompt_blocks(engine: str, log_text: str) -> list[dict[str, Any]]:
    """Per-request prompt counts with the request's own tool bytes, when the log has them.

    mlx-serve logs ``POST /v1/chat/completions (... user=<n>b, tools=<n>b ...)`` then
    ``prompt=<n> tokens`` for the same request, so a probe's own count can be picked
    out of a log that also holds the preflight's.
    """
    if engine != "mlx-serve":
        count = _candidate_prompt_token_count(engine, log_text)
        return [{"tools_bytes": None, "user_bytes": None, "prompt_tokens": count}] if count else []
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in log_text.splitlines():
        request = _MLX_SERVE_REQUEST_RE.search(line)
        if request:
            current = {
                "tools_bytes": int(request.group("tools")),
                "user_bytes": int(request.group("user")),
                "prompt_tokens": None,
            }
            blocks.append(current)
            continue
        prompt = _MLX_SERVE_PROMPT_RE.search(line)
        if prompt and current is not None and current["prompt_tokens"] is None:
            current["prompt_tokens"] = int(prompt.group(1))
            current = None
    return [block for block in blocks if block["prompt_tokens"] is not None]


def _parity_prompt_tokens(blocks: list[dict[str, Any]], *, user_bytes: int) -> int | None:
    """The parity request's own rendered-prompt count, not another probe's."""
    matching = [
        block for block in blocks if block["tools_bytes"] and block["user_bytes"] == user_bytes
    ]
    if matching:
        return int(matching[-1]["prompt_tokens"])
    return int(blocks[-1]["prompt_tokens"]) if blocks else None


def _tool_rendering(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether the engine put the offered tool schemas into the rendered prompt."""
    with_tools = [block for block in blocks if (block["tools_bytes"] or 0) > 0]
    without = [block for block in blocks if block["tools_bytes"] == 0]
    if not with_tools or not without:
        return {
            "rendered": None,
            "reason": "the engine log carries no tools request beside a no-tools request",
        }
    high = max(int(block["prompt_tokens"]) for block in with_tools)
    low = max(int(block["prompt_tokens"]) for block in without)
    return {
        "rendered": high - low >= TOOL_RENDER_MIN_TOKENS,
        "with_tools_prompt_tokens": high,
        "without_tools_prompt_tokens": low,
        "delta_tokens": high - low,
        "source": "engine log: tools=<bytes> and prompt=<n> logged per request",
        "rule": f"a rendered tool block adds at least {TOOL_RENDER_MIN_TOKENS} prompt tokens",
    }


def _candidate_engine_log_text(started_info: dict[str, Any]) -> str:
    chunks = []
    for key in ("stderr_log", "stdout_log"):
        path = started_info.get(key)
        if not path:
            continue
        try:
            chunks.append(Path(path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def _candidate_effective_temperature(engine: str, log_text: str) -> float | None:
    if engine != "mlx-serve":
        return None
    match = re.search(r"\btemp=([0-9]+(?:\.[0-9]+)?)", log_text)
    return float(match.group(1)) if match else None


def _candidate_output(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {"content": str(message)}
    output = {
        key: message[key]
        for key in ("content", "reasoning", "reasoning_content", "refusal")
        if key in message
    }
    tool_calls = []
    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        tool_calls.append(
            {
                "type": call.get("type"),
                "function": {
                    "name": function.get("name"),
                    "arguments": function.get("arguments"),
                },
            }
        )
    if tool_calls:
        output["tool_calls"] = tool_calls
    return output


def _candidate_parity(ctx: dict[str, Any]) -> dict[str, Any]:
    cell = ctx["cell"]
    body = ctx["body"]
    log_text = ctx["engine_log_text"]
    blocks = ctx["prompt_blocks"]
    return {
        "engine": cell["engine"],
        "requests": [body, body],
        "outputs": [_candidate_output(row["message"]) for row in ctx["parity_rows"]],
        "requested_temperature": body.get("temperature"),
        "max_tokens": body.get("max_tokens"),
        "effective_temperature": _candidate_effective_temperature(cell["engine"], log_text),
        "effective_temperature_source": "engine stderr temp field"
        if cell["engine"] == "mlx-serve"
        else None,
        "effective_temperature_note": (
            "mlx_lm.server log omits the effective value; installed handler reads request.temperature "
            "and passes it to SamplingArguments"
            if cell["engine"] == "mlx_lm.server"
            else "engine log does not emit the effective sampling value"
            if cell["engine"] != "mlx-serve"
            else None
        ),
        "rendered_prompt_token_count": _parity_prompt_tokens(
            blocks, user_bytes=len(PARITY_PROMPT.encode())
        ),
        "rendered_prompt_token_count_source": "engine log: this request's own prompt line",
        "rendered_prompt_blocks": blocks,
        "tool_rendering": _tool_rendering(blocks),
        "tools_exposed": pipeline_tools_exposed(ctx["log"]),
    }


OMLX_INCUMBENT_BACKEND = "eval-openai-omlx-incumbent"
OMLX_PORT = 8085
_OMLX_CHAT_PROMPT_RE = re.compile(
    r"Chat completion: model=(?P<model>[^,]+),.*?\bprompt:\s*(?P<prompt>\d+)"
)
_PIPE_TOOLS_RE = re.compile(r"NON-STREAM tools: (\[.*\])")
_TEMPLATE_MISMATCH = "chat_template_rendering_mismatch"
_TOOL_SCHEMA_NOT_RENDERED = "tool_schema_not_rendered"
_MLX_SERVE_REQUEST_RE = re.compile(
    r"POST /v1/chat/completions \(.*?user=(?P<user>\d+)b, tools=(?P<tools>\d+)b"
)
_MLX_SERVE_PROMPT_RE = re.compile(r"\bprompt=(\d+) tokens\b")


def omlx_prompt_token_count(log_text: str, model: str) -> int | None:
    """Last per-request prompt count oMLX logged for ``model``."""
    found = None
    for line in log_text.splitlines():
        match = _OMLX_CHAT_PROMPT_RE.search(line)
        if match and match.group("model").strip() == model:
            found = int(match.group("prompt"))
    return found


def pipeline_tools_exposed(log_text: str) -> list[str] | None:
    """The tool names the Pipeline last offered a backend on this log slice."""
    found = None
    for line in log_text.splitlines():
        match = _PIPE_TOOLS_RE.search(line)
        if not match:
            continue
        try:
            parsed = ast.literal_eval(match.group(1))
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, list):
            found = [str(name) for name in parsed]
    return found


def _incumbent_leg(cell: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """oMLX identity for the checkpoint this cell loaded."""
    return {
        "engine": "omlx",
        "backend": OMLX_INCUMBENT_BACKEND,
        "base": h2h.base_url(cfg, "omlx"),
        "port": OMLX_PORT,
        "model": cell["expected_model"],
    }


def _incumbent_parity_blocker(cell: dict[str, Any], cfg: dict[str, Any]) -> str | None:
    """Why oMLX cannot render this cell's checkpoint, or None when it can."""
    if cfg["engines"][cell["engine"]].get("requires") != "mlx":
        return f"{cell['engine']} does not load the MLX checkpoint oMLX serves"
    if not h2h.model_supports_engine(cfg, cell["model"], "omlx"):
        return f"{cell['model']} has no MLX artifact for the oMLX incumbent"
    return None


def _read_log_from(path: Path, offset: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _unload_incumbent(cfg: dict[str, Any], model: str) -> dict[str, Any]:
    """Return oMLX to its pre-cell resident set and say whether it did."""
    unload: dict[str, Any] = {"model": model, "requested": False, "remaining": None}
    try:
        loaded = _production_loaded_models("omlx", cfg)
    except Exception as exc:
        unload["error"] = str(exc)
        return unload
    if model in loaded:
        try:
            _unload_production_model("omlx", model, cfg)
            unload["requested"] = True
        except Exception as exc:
            unload["error"] = str(exc)
    try:
        unload["remaining"] = _production_loaded_models("omlx", cfg)
    except Exception as exc:
        unload["error"] = str(exc)
    return unload


def _measure_incumbent_parity(
    cell: dict[str, Any], cfg: dict[str, Any], pipeline: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Send the cell's own greedy probe to oMLX on the same checkpoint and read it back."""
    leg = _incumbent_leg(cell, cfg)
    log_path = instrument.omlx_server_log()
    try:
        offset = log_path.stat().st_size
    except OSError as exc:
        return {"status": "unmeasured", "reason": f"{log_path} is unreadable: {exc}"}
    swap_before = h2h.swap_now().get("used_mb")
    pipeline_mark = time.strftime("%Y-%m-%dT%H:%M:%S")
    incumbent_body = {**body, "portal_backend": leg["backend"]}
    try:
        row = _candidate_request(f"{pipeline.rstrip('/')}/v1/chat/completions", incumbent_body)
    except Exception as exc:
        return {
            "status": "unmeasured",
            "reason": f"incumbent request failed: {exc}",
            "unload": _unload_incumbent(cfg, leg["model"]),
        }
    log_text = _read_log_from(log_path, offset)
    route = str(row.get("header") or "")
    match = instrument._ROUTE_RE.match(route)
    if (
        not match
        or match.group(2) != leg["backend"]
        or match.group(3) != leg["model"]
        or row.get("engine_model") != leg["model"]
    ):
        unload = _unload_incumbent(cfg, leg["model"])
        return {
            "status": "unmeasured",
            "reason": (
                f"incumbent route {route!r} model {row.get('engine_model')!r} is not "
                f"{leg['backend']}/{leg['model']}"
            ),
            "unload": unload,
        }
    prompt = omlx_prompt_token_count(log_text, leg["model"])
    measured = {
        "status": "measured",
        "engine": leg["engine"],
        "backend": leg["backend"],
        "model": leg["model"],
        "route": route,
        "engine_model": row.get("engine_model"),
        "requests": [incumbent_body],
        "outputs": [_candidate_output(row["message"])],
        "requested_temperature": incumbent_body.get("temperature"),
        "max_tokens": incumbent_body.get("max_tokens"),
        "effective_temperature": None,
        "effective_temperature_source": None,
        "effective_temperature_note": (
            "oMLX server.log has no per-request effective temperature line; the request carried 0"
        ),
        "rendered_prompt_token_count": prompt,
        "rendered_prompt_token_count_source": "~/.omlx/logs/server.log Chat completion prompt",
        "tool_rendering": {
            "rendered": None,
            "reason": "oMLX server.log logs the prompt count but not the request's tools bytes",
        },
        "tools_exposed": pipeline_tools_exposed(instrument._pipeline_log_since(pipeline_mark)),
        "swap_used_mb": [swap_before, h2h.swap_now().get("used_mb")],
        "unload": _unload_incumbent(cfg, leg["model"]),
    }
    if prompt is None:
        measured["status"] = "unmeasured"
        measured["reason"] = "oMLX server.log had no Chat completion prompt line for this request"
    return measured


def _template_reconciliation(cell: dict[str, Any]) -> dict[str, Any]:
    """What the engine offers for rendering the incumbent's prompt, and why it cannot."""
    engine = cell["engine"]
    pre_rendered = (
        "sending the incumbent's rendered prompt to a completion endpoint would equalise the "
        "token counts but bypasses the engine's own chat template, so it cannot evidence "
        "template parity; not applied"
    )
    if engine == "mlx_lm.server":
        detail = (
            "mlx_lm.server has --chat-template, but it already applies the checkpoint's own "
            "chat_template.jinja: AutoTokenizer loads it from the model directory and "
            "mlx_lm/server.py _tokenize calls tokenizer.apply_chat_template(messages, "
            "add_generation_prompt=True, tools=..., **chat_template_kwargs). The Pipeline "
            "canonicalises the tool schemas for every eval arm, so the payload is identical."
        )
    elif engine == "mlx-serve":
        detail = (
            "mlx-serve 26.11.2 exposes no chat-template flag in `mlx-serve --help`; the Pipeline "
            "canonicalises the tool schemas for every eval arm, so the payload is identical."
        )
    else:
        detail = f"{engine} has no registered chat-template override for this matrix cell"
    return {
        "attempted": False,
        "available": False,
        "pre_rendered_input": pre_rendered,
        "detail": detail,
    }


def _differs_from_incumbent(comparison: dict[str, Any]) -> str | None:
    if comparison.get("valid") is True:
        return None
    counts = comparison.get("rendered_prompt_token_counts") or {}
    if counts.get("left") is None or counts.get("right") is None:
        return "unmeasured"
    return "left"


def parity_settings() -> dict[str, Any]:
    """The operator's parity rule: prompt tolerance and matched text prefix, from the protocol."""
    block = (yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}).get("template_parity")
    if not isinstance(block, dict):
        raise Stage3BlockedError("the protocol carries no template_parity rule")
    tolerance = block.get("prompt_token_tolerance")
    prefix = block.get("prefix_tokens")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance <= 0:
        raise Stage3BlockedError("template_parity.prompt_token_tolerance must be a positive number")
    if isinstance(prefix, bool) or not isinstance(prefix, int) or prefix < 0:
        raise Stage3BlockedError("template_parity.prefix_tokens must be a non-negative integer")
    return {"prompt_token_tolerance": float(tolerance), "prefix_tokens": prefix}


def _template_difference(cell: dict[str, Any], comparison: dict[str, Any]) -> str | None:
    """The recorded FINDING when the candidate renders the same probe differently."""
    classification = comparison.get("classification")
    if classification == _TOOL_SCHEMA_NOT_RENDERED:
        rendering = (comparison.get("tool_rendering") or {}).get("left") or {}
        return (
            f"{cell['engine']} does not render the offered tool schemas into its prompt "
            f"({rendering.get('with_tools_prompt_tokens')} tokens with tools, "
            f"{rendering.get('without_tools_prompt_tokens')} without). Tool-use quality is "
            f"not comparable for this engine; answer quality is compared on the same payload."
        )
    if classification != _TEMPLATE_MISMATCH:
        return None
    counts = comparison.get("rendered_prompt_token_counts") or {}
    candidate, incumbent = counts.get("left"), counts.get("right")
    if candidate is None or incumbent is None:
        return (
            f"{cell['engine']} rendered-prompt count unreadable against incumbent oMLX "
            f"({candidate} vs {incumbent})"
        )
    delta = int(candidate) - int(incumbent)
    return (
        f"{cell['engine']} renders the same greedy probe to {candidate} prompt tokens; "
        f"incumbent oMLX renders {incumbent} ({delta:+d}), beyond the "
        f"{parity_settings()['prompt_token_tolerance']:.0%} tolerance, with the tool payload "
        f"canonicalised byte-identically for both legs by the Pipeline. The residual is each "
        f"engine's own message rendering, so the quality comparison for this cell is not "
        f"comparable."
    )


def _template_rule() -> str:
    """The parity rule as the receipt states it, with the protocol's own numbers."""
    settings = parity_settings()
    return (
        "Template parity is the candidate cell against the oMLX incumbent on the same checkpoint, "
        "both probed inside this cell with the identical greedy request. The Pipeline canonicalises "
        "the tool schemas exactly as oMLX does before they leave it, so both legs render the same "
        "payload; a rendered-prompt token-count difference beyond "
        f"{settings['prompt_token_tolerance']:.0%} stays a FINDING (template_differs) and makes "
        "the cell's quality comparison not comparable. An engine whose tools-bearing request "
        "renders to the same size as its no-tools request is recorded as not rendering the tool "
        "schemas, and its tool-use quality is not comparable. Operator rule 2026-11-14: parity is "
        "template/BOS/stop conformance, not bit-identical generation — the first "
        f"{settings['prefix_tokens']} greedy text tokens must match, and a later divergence is "
        "recorded numerical drift, not a failure."
    )


def _parity_unmeasured(
    template: dict[str, Any],
    parity: dict[str, Any],
    classification: str,
    findings: list[str],
    extra: dict[str, Any] | None = None,
) -> None:
    """Record a pair that could not be compared. The cell stays instrument-invalid."""
    parity["status"] = "unmeasured"
    parity["comparisons"] = {
        "omlx": {
            "valid": False,
            "classification": classification,
            "findings": findings,
            **(extra or {}),
        }
    }
    template["quality_comparable"] = True


def _tool_payloads_differ(parity: dict[str, Any], incumbent: dict[str, Any]) -> list[str] | None:
    """The tool names each leg was offered, when the Pipeline did not offer the same set."""
    candidate_tools = parity.get("tools_exposed")
    incumbent_tools = incumbent.get("tools_exposed")
    if candidate_tools is None or incumbent_tools is None or candidate_tools == incumbent_tools:
        return None
    return [str(candidate_tools), str(incumbent_tools)]


def _classify_incumbent_leg(
    cell: dict[str, Any],
    template: dict[str, Any],
    parity: dict[str, Any],
    incumbent: dict[str, Any],
) -> None:
    """Compare the two legs, or record why their payloads are not comparable."""
    differing_tools = _tool_payloads_differ(parity, incumbent)
    if differing_tools:
        _parity_unmeasured(
            template,
            parity,
            "tool_payload_mismatch",
            [
                "the Pipeline offered different tools to each leg: "
                f"{differing_tools[0]} vs {differing_tools[1]}"
            ],
            {"engines": {"left": cell["engine"], "right": "omlx"}},
        )
        return
    comparison = _compare_candidate_parity(parity, incumbent)
    comparison["engines"] = {"left": cell["engine"], "right": "omlx"}
    comparison["reference"] = "omlx"
    comparison["differs_from_incumbent"] = _differs_from_incumbent(comparison)
    parity["status"] = "compared"
    parity["comparisons"] = {"omlx": comparison}
    difference = _template_difference(cell, comparison)
    template["template_differs"] = difference
    template["quality_comparable"] = difference is None
    template["tool_use_comparable"] = comparison.get("classification") != _TOOL_SCHEMA_NOT_RENDERED
    if difference:
        template["reconciliation"] = _template_reconciliation(cell)


def _attach_incumbent_parity(
    cell: dict[str, Any], cfg: dict[str, Any], pipeline: str, evidence: dict[str, Any]
) -> None:
    """Compare this cell's own greedy probe with the oMLX incumbent's, in-cell."""
    template = evidence.setdefault("template", {})
    parity = template.get("parity")
    if template.get("same_checkpoint") is not True:
        template["parity"] = {
            "status": "not_run",
            "reason": "cell does not load the matrix checkpoint, so there is no incumbent pair",
        }
        return
    if not isinstance(parity, dict):
        parity = {}
        template["parity"] = parity
        _parity_unmeasured(
            template,
            parity,
            "candidate_probe_missing",
            ["the candidate's own greedy probe was not recorded"],
        )
        return
    template["rule"] = _template_rule()
    blocker = _incumbent_parity_blocker(cell, cfg)
    if blocker:
        parity["status"] = "not_run"
        parity["reason"] = blocker
        template["quality_comparable"] = True
        return
    body = _parity_request(parity)
    if body is None:
        _parity_unmeasured(
            template,
            parity,
            "candidate_probe_missing",
            ["candidate request body missing from the cell's parity evidence"],
        )
        return
    body.pop("_repeated_request_mismatch", None)
    incumbent = _measure_incumbent_parity(cell, cfg, pipeline, body)
    parity["incumbent"] = incumbent
    if incumbent.get("status") != "measured":
        _parity_unmeasured(
            template,
            parity,
            "incumbent_parity_unmeasured",
            [str(incumbent.get("reason") or "incumbent parity not measured")],
        )
        return
    _classify_incumbent_leg(cell, template, parity, incumbent)


def _parity_request(parity: dict[str, Any]) -> dict[str, Any] | None:
    requests = parity.get("requests")
    if isinstance(requests, list) and requests and isinstance(requests[0], dict):
        first = dict(requests[0])
        if any(item != requests[0] for item in requests[1:]):
            first["_repeated_request_mismatch"] = True
        return first
    request = parity.get("request")
    return request if isinstance(request, dict) else None


def _parity_requests_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_request, right_request = _parity_request(left), _parity_request(right)
    if left_request is None or right_request is None:
        return False
    left_repeated_mismatch = left_request.pop("_repeated_request_mismatch", False)
    right_repeated_mismatch = right_request.pop("_repeated_request_mismatch", False)
    left_request.pop("portal_backend", None)
    right_request.pop("portal_backend", None)
    return (
        left_request == right_request and not left_repeated_mismatch and not right_repeated_mismatch
    )


def _parity_readback_findings(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    findings = []
    for side, parity in (("left", left), ("right", right)):
        if parity.get("effective_temperature") is None:
            findings.append(
                f"{side} effective sampling readback unavailable: "
                f"{parity.get('effective_temperature_note') or 'no engine setting source'}"
            )
    return findings


def _parity_requests_are_greedy(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_request, right_request = _parity_request(left) or {}, _parity_request(right) or {}
    left_temperature = left.get("requested_temperature", left_request.get("temperature"))
    right_temperature = right.get("requested_temperature", right_request.get("temperature"))
    left_max_tokens = left.get("max_tokens", left_request.get("max_tokens"))
    right_max_tokens = right.get("max_tokens", right_request.get("max_tokens"))
    return (
        left_temperature == 0
        and right_temperature == 0
        and left_max_tokens == right_max_tokens
        and isinstance(left_max_tokens, int)
        and left_max_tokens > 0
    )


def _outputs_are_stable(parity: dict[str, Any]) -> bool:
    outputs = parity.get("outputs") or []
    return bool(outputs) and all(item == outputs[0] for item in outputs)


def _effective_temperature_nonzero(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return any(
        isinstance(parity.get("effective_temperature"), (int, float))
        and parity["effective_temperature"] != 0
        for parity in (left, right)
    )


def _rendered_prompt_counts_differ(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_count = left.get("rendered_prompt_token_count")
    right_count = right.get("rendered_prompt_token_count")
    if left_count is None or right_count is None:
        return False
    return not _counts_within_tolerance(left_count, right_count)


def _counts_within_tolerance(left: int, right: int) -> bool:
    """Same input renders to the same tokens; this absorbs only per-engine message handling."""
    tolerance = parity_settings()["prompt_token_tolerance"]
    return abs(int(left) - int(right)) <= tolerance * max(abs(int(left)), abs(int(right)), 1)


def _prompt_token_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_count = left.get("rendered_prompt_token_count")
    right_count = right.get("rendered_prompt_token_count")
    if left_count is None or right_count is None:
        return {}
    tolerance = int(
        parity_settings()["prompt_token_tolerance"] * max(int(left_count), int(right_count), 1)
    )
    return {
        "left": left_count,
        "right": right_count,
        "delta": int(left_count) - int(right_count),
        "tolerance_tokens": tolerance,
        "within_tolerance": _counts_within_tolerance(left_count, right_count),
    }


def _tool_schemas_missing(engine: str, parity: dict[str, Any]) -> str | None:
    """The engine that does not put the offered schemas into its prompt, if one does not."""
    rendering = parity.get("tool_rendering") or {}
    if rendering.get("rendered") is not False:
        return None
    return (
        f"{engine} renders a tools-bearing request to "
        f"{rendering.get('with_tools_prompt_tokens')} prompt tokens and the same request "
        f"without tools to {rendering.get('without_tools_prompt_tokens')}: the offered tool "
        f"schemas are not in its prompt, so its tool-use quality is not comparable"
    )


def _output_text(output: Any) -> str:
    """The text an output carries, reasoning first, as the wire shows it."""
    if not isinstance(output, dict):
        return str(output)
    return "\n".join(
        str(output[key])
        for key in ("reasoning", "reasoning_content", "content", "refusal")
        if isinstance(output.get(key), str) and output.get(key)
    )


def _greedy_divergence(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Where the two legs' own text stops agreeing, with both outputs as they came back."""
    left_output = (left.get("outputs") or [{}])[0]
    right_output = (right.get("outputs") or [{}])[0]
    left_tokens = _output_text(left_output).split()
    right_tokens = _output_text(right_output).split()
    shared = 0
    for left_token, right_token in zip(left_tokens, right_tokens, strict=False):
        if left_token != right_token:
            break
        shared += 1
    return {
        "index": shared,
        "unit": "whitespace-delimited text tokens of the generated message",
        "left_text_tokens": len(left_tokens),
        "right_text_tokens": len(right_tokens),
        "identical": left_output == right_output,
        "left_output": left_output,
        "right_output": right_output,
    }


def _greedy_output_classification(drift: dict[str, Any]) -> tuple[str, list[str]]:
    """Operator rule 2026-11-14: the first K text tokens match, then divergence is drift."""
    prefix = parity_settings()["prefix_tokens"]
    if drift["identical"]:
        return "match", []
    if drift["index"] < prefix:
        return "greedy_output_mismatch_unexplained", [
            f"greedy text diverged at token {drift['index']}, before the {prefix} the protocol "
            "requires to match: a template or BOS difference, not drift"
        ]
    return "greedy_numerical_drift", [
        f"greedy text diverged at token {drift['index']}; the protocol requires the first "
        f"{prefix} to match, so the remainder is recorded numerical drift"
    ]


def _classify_candidate_outputs(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[str, list[str], dict[str, Any]]:
    drift = _greedy_divergence(left, right)
    if not _outputs_are_stable(left) or not _outputs_are_stable(right):
        return "sampling_or_nondeterminism", ["repeated output differed with temperature 0"], drift
    if _effective_temperature_nonzero(left, right):
        return (
            "sampling_field_not_honored",
            ["an engine read back a nonzero effective temperature"],
            drift,
        )
    if _tool_schemas_missing(str(left.get("engine")), left) or _tool_schemas_missing(
        str(right.get("engine")), right
    ):
        return _TOOL_SCHEMA_NOT_RENDERED, ["a leg does not render the offered tool schemas"], drift
    if _rendered_prompt_counts_differ(left, right):
        return _TEMPLATE_MISMATCH, ["same request rendered to different prompt token counts"], drift
    return *_greedy_output_classification(drift), drift


def _compare_candidate_parity(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_request, right_request = _parity_request(left), _parity_request(right)
    if left_request is None or right_request is None:
        return {
            "valid": False,
            "classification": "request_evidence_missing",
            "findings": ["request body missing from a parity side"],
        }
    findings = _parity_readback_findings(left, right)
    if not _parity_requests_match(left, right) or not _parity_requests_are_greedy(left, right):
        classification, drift = "sampling_request_mismatch", _greedy_divergence(left, right)
        findings.append("parity requests are not identical greedy requests with fixed max_tokens")
    else:
        classification, output_findings, drift = _classify_candidate_outputs(left, right)
        findings.extend(output_findings)
    left_max_tokens = left.get("max_tokens", left_request.get("max_tokens"))
    settings = parity_settings()
    return {
        "valid": classification in ("match", "greedy_numerical_drift"),
        "classification": classification,
        "requested_temperature": 0,
        "max_tokens": left_max_tokens,
        "outputs_equal": drift["identical"],
        "greedy_divergence": drift,
        "rendered_prompt_token_counts": {
            "left": left.get("rendered_prompt_token_count"),
            "right": right.get("rendered_prompt_token_count"),
        },
        "rendered_prompt_token_delta": _prompt_token_delta(left, right),
        "tool_rendering": {
            "left": left.get("tool_rendering"),
            "right": right.get("tool_rendering"),
        },
        "prompt_token_tolerance": settings["prompt_token_tolerance"],
        "prefix_tokens": settings["prefix_tokens"],
        "findings": findings,
    }


def _candidate_request(url: str, body: dict[str, Any]) -> dict[str, Any]:
    """Preserve the HTTP status and upstream response body when a request fails."""
    try:
        return instrument._one_chat(url, body, instrument._pipeline_headers())
    except urllib.error.HTTPError as exc:
        raise CandidateHTTPError(
            exc.code, exc.read().decode("utf-8", "replace") or str(exc.reason)
        ) from exc


def _candidate_cell_inputs(
    cell: dict[str, Any],
    pipeline: str,
    vm_before: str | None = None,
    resident_before: dict[str, Any] | None = None,
    started_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect the raw inputs shared by the evidence sections."""
    cfg = h2h.load_config()
    vm_before = vm_before or subprocess.check_output(["vm_stat"], text=True, timeout=10)
    resident_before = resident_before or _candidate_residency(cfg)
    models_response = _models_payload(cell["base"])
    model_row = _model_row(models_response["json"], cell["expected_model"])
    served = [str(row.get("id")) for row in _model_rows(models_response["json"]) if row.get("id")]
    log_since = time.strftime("%Y-%m-%dT%H:%M:%S")
    body = _candidate_body(cell)
    url = f"{pipeline.rstrip('/')}/v1/chat/completions"
    think_row = _candidate_request(url, _think_off_body(cell))
    memory_models_response = _models_payload(cell["base"])
    memory = _candidate_memory(
        vm_before,
        cell["port"],
        cell["engine"],
        cfg["engines"][cell["engine"]],
        _model_row(memory_models_response["json"], cell["expected_model"]),
    )
    tool_row = _candidate_request(url, _tool_call_body(cell))
    parity_rows = [_candidate_request(url, body) for _ in range(2)]
    rows = [think_row, tool_row, *parity_rows]
    resident_after = _candidate_residency(cfg)
    log = instrument._pipeline_log_since(log_since)
    engine_log_text = _candidate_engine_log_text(started_info or {})
    preflight = _grade_cell_preflight(cell, think_row, tool_row)
    tokenizer = _candidate_tokenizer(cfg, cell)
    return {
        "cell": cell,
        "cfg": cfg,
        "vm_before": vm_before,
        "resident_before": resident_before,
        "resident_after": resident_after,
        "models_response": models_response,
        "memory_models_response": memory_models_response,
        "memory": memory,
        "model_row": model_row,
        "served": served,
        "body": body,
        "rows": rows,
        "think_row": think_row,
        "tool_row": tool_row,
        "parity_rows": parity_rows,
        "log": log,
        "engine_log_text": engine_log_text,
        "prompt_blocks": _engine_prompt_blocks(cell["engine"], engine_log_text),
        "preflight": preflight,
        "tokenizer": tokenizer,
        "started_info": started_info or {},
    }


def _candidate_evidence_sources(cell: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = {
        "engine_models": f"POST /v1/chat/completions response.model ({OPENAI_CHAT_SOURCE})",
        "served_model_id": f"POST /v1/chat/completions response.model ({OPENAI_CHAT_SOURCE})",
        "pipeline_route": "Pipeline x-portal-route, logs, and response model",
        "tokens": "Pipeline usage and the registered checkpoint tokenizer.json, else the engine's POST /tokenize",
        "memory": "engine-specific resident reading compared with vm_stat wired delta",
        "residency": "Ollama /api/ps; oMLX /v1/models/status; managed-port listeners and state",
        "models_response": f"GET {cell['base']}/v1/models (raw response attached)",
    }
    excluded = {
        key: instrument._exclude(
            f"{cell['engine']} has no verified request-level readback source for this claim"
        )
        for key in instrument.REQUIRED_CLAIMS
    }
    return sources, excluded


def _candidate_route_evidence(ctx: dict[str, Any]) -> dict[str, Any]:
    cell, rows = ctx["cell"], ctx["rows"]
    return {
        "engine": cell["engine"],
        "mode": cell["mode"],
        "claimed": {},
        "readback": {},
        "sources": {},
        "source_conflicts": [],
        "expected_model": cell["expected_model"],
        "expected_workspace": cell["workspace"],
        "expected_backend": cell["backend"],
        "routes": [{"header": row["header"], "engine_model": row["engine_model"]} for row in rows],
        "engine_models": [row["engine_model"] for row in rows],
        "pipeline_models": [
            model for _ws, _be, model in instrument.parse_pipeline_routes(ctx["log"])
        ],
        "memory": ctx["memory"],
        "memory_sample_timing": "after the first completed Pipeline request",
        "memory_engine_models_response": ctx["memory_models_response"],
        "residency": {"before": ctx["resident_before"], "after": ctx["resident_after"]},
    }


def _engine_token_count(cell: dict[str, Any], text: str) -> int | None:
    """Count with the engine's own tokenizer when the checkpoint has no tokenizer.json."""
    payload = json.dumps({"content": text}).encode()
    request = urllib.request.Request(
        f"{cell['base'].rstrip('/')}/tokenize",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            tokens = json.load(response).get("tokens")
    except (OSError, ValueError):
        return None
    return len(tokens) if isinstance(tokens, list) else None


def _token_evidence(ctx: dict[str, Any]) -> dict[str, Any]:
    """Pipeline usage against the checkpoint tokenizer, else the engine's own tokenizer."""
    text = ctx["think_row"]["text"]
    tokenizer = ctx["tokenizer"]
    local = instrument.count_tokens(text, tokenizer) if tokenizer else None
    source = "think-off reply: Pipeline usage vs the registered checkpoint tokenizer"
    if local is None:
        local = _engine_token_count(ctx["cell"], text)
        source = (
            "think-off reply: Pipeline usage vs the engine's own POST /tokenize "
            "(the checkpoint has no tokenizer.json)"
        )
    return {
        "engine_completion": ctx["think_row"]["tokens"],
        "tokenizer_completion": local,
        "source": source,
    }


def _candidate_settings_evidence(ctx: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    cell, model_row, models = ctx["cell"], ctx["model_row"], ctx["models_response"]
    cfg = ctx["cfg"]
    template = _candidate_template(cfg, cell)
    template["parity"] = _candidate_parity(ctx)
    return {
        "engine_models_response": models,
        "engine_settings_readback": {
            key: model_row[key]
            for key in ("context_length", "max_model_len", "batched_decode")
            if key in model_row
        },
        "engine_settings_source": sources["models_response"],
        "startup_readiness": {
            "endpoint": f"{cell['base']}/v1/models",
            "timeout_s": (cfg["engines"][cell["engine"]].get("readiness") or {}).get(
                "timeout_s", 300
            ),
            "ready_s": ctx["started_info"].get("ready_s"),
            "expected_model": cell["expected_model"],
            "status": models["status"],
            "listed_model_ids": ctx["served"],
            "state": model_row.get("state"),
            "loaded": model_row.get("loaded"),
        },
        "tokens": _token_evidence(ctx),
        "noise": instrument._pair_noise(
            [(row["tokens"], row["elapsed"]) for row in ctx["parity_rows"]]
        ),
        "template": template,
    }


def _candidate_verdict_evidence(ctx: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    cell, preflight = ctx["cell"], ctx["preflight"]
    cfg = ctx["cfg"]
    return {
        "preflight_verdict": preflight["verdict"],
        "preflight": preflight,
        "swap_samples_mb": instrument._swap_pair(h2h.swap_now().get("used_mb")),
        "max_swap_growth_mb": cfg["guard"]["max_swap_growth_mb"],
        "max_start_swap_used_mb": cfg["guard"]["max_start_swap_used_mb"],
        "served_model_id": next(
            (
                row["engine_model"]
                for row in ctx["rows"]
                if row.get("engine_model") == cell["expected_model"]
            ),
            None,
        ),
        "launch_argv": cell["argv"],
        "check_sources": {
            "route": sources["pipeline_route"],
            "memory": sources["memory"],
            "tokens": sources["tokens"],
            "noise": "two back-to-back Pipeline requests with the same body",
            "preflight": "separate think-off request (no tools) then a named tool_choice request, through the Pipeline",
            "residency": sources["residency"],
            "template": "registry model template vs source repository when same_checkpoint is true",
            "endpoint_sources": sources,
            "models_response": "engine_models_response.json is embedded below in the receipt",
        },
    }


def collect_candidate_cell(
    cell: dict[str, Any],
    pipeline: str,
    vm_before: str | None = None,
    resident_before: dict[str, Any] | None = None,
    started_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect two routed requests, readbacks, tokens, and all-engine snapshots."""
    ctx = _candidate_cell_inputs(cell, pipeline, vm_before, resident_before, started_info)
    sources, excluded = _candidate_evidence_sources(cell)
    return {
        **_candidate_route_evidence(ctx),
        "excluded_claims": excluded,
        **_candidate_settings_evidence(ctx, sources),
        **_candidate_verdict_evidence(ctx, sources),
        "sources": {},
        "source_conflicts": [],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a receipt atomically. An existing receipt is moved aside first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path.replace(path.with_name(f"{path.name}.bak-{stamp}"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _stop_cell_engine(cell: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Stop the candidate so the incumbent can hold the same checkpoint."""
    h2h.stop_managed(cfg, cell["engine"])
    listener = h2h.pid_on_port(cell["port"])
    if listener:
        raise Stage3BlockedError(
            f"{cell['engine']} still listening on port {cell['port']} (pid {listener})"
        )


def _execute_candidate_cell(
    cell: dict[str, Any],
    pipeline: str,
    cfg: dict[str, Any],
    receipt: dict[str, Any],
    log_paths: tuple[Path, Path],
    mark_started: Any,
) -> None:
    if cell.get("launch_error"):
        raise Stage3BlockedError(f"registry argv unavailable: {cell['launch_error']}")
    host_prep = _prepare_production_models(cfg)
    receipt["host_prep"] = host_prep
    if not host_prep["valid"]:
        raise Stage3BlockedError(f"pre-canary unload failed: {host_prep['failures']}")
    if h2h.pid_on_port(cell["port"]):
        raise Stage3BlockedError(f"candidate port {cell['port']} is already occupied")
    okay, reason = h2h.start_gate(cfg)
    if not okay:
        raise Stage3BlockedError(f"swap start gate: {reason}")
    vm_before = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    resident_before = _candidate_residency(cfg)
    with h2h.single_flight():
        started_info = h2h.start_managed(
            cfg,
            cell["engine"],
            cell["model"],
            cell["mode"],
            log_paths=log_paths,
            on_started=mark_started,
        )
        receipt["pipeline_backend"] = wait_pipeline_eval_backend(pipeline, cell["backend"])
        receipt["engine_models_response"] = _models_payload(cell["base"])
        evidence = collect_candidate_cell(cell, pipeline, vm_before, resident_before, started_info)
        evidence["launch_argv"] = started_info.get("argv") or cell["argv"]
        _stop_cell_engine(cell, cfg)
        _attach_incumbent_parity(cell, cfg, pipeline, evidence)
        judged = instrument.judge_cell(evidence)
        receipt.update(
            {"evidence": evidence, "valid": judged["valid"], "failures": judged["failures"]}
        )


def _finish_candidate_cell(
    cell: dict[str, Any],
    cfg: dict[str, Any],
    receipt: dict[str, Any],
    log_paths: tuple[Path, Path],
    attempted: bool,
) -> None:
    model_response = receipt["engine_models_response"]
    if attempted and model_response.get("reason"):
        try:
            receipt["engine_models_response"] = _models_payload(cell["base"])
        except (CandidateHTTPError, OSError, ValueError) as exc:
            receipt["engine_models_response"] = {
                "status": getattr(exc, "status", None),
                "json": {},
                "raw": getattr(exc, "body", ""),
                "reason": str(exc),
            }
    elif not attempted:
        model_response["reason"] = (
            "not probed because this cell did not start an owned engine process"
        )
    if attempted:
        try:
            h2h.stop_managed(cfg, cell["engine"])
        except (OSError, subprocess.CalledProcessError, SystemExit) as exc:
            receipt["valid"] = False
            receipt.setdefault("failures", []).append(f"stop: {exc}")
    try:
        listener = h2h.pid_on_port(cell["port"])
    except (OSError, subprocess.CalledProcessError) as exc:
        listener = f"probe failed: {exc}"
    receipt["port_after_stop"] = {"port": cell["port"], "listener": listener}
    if listener:
        receipt["valid"] = False
        receipt.setdefault("failures", []).append(
            f"engine left listening on port {cell['port']} (pid {listener})"
        )
    receipt["engine_logs"]["stdout_exists"] = log_paths[0].is_file()
    receipt["engine_logs"]["stderr_exists"] = log_paths[1].is_file()
    receipt["evidence_sources"]["engine_logs"] = [str(path) for path in log_paths]


def run_cell(cell: dict[str, Any], pipeline: str, build: str | None = None) -> dict[str, Any]:
    """Start one managed engine, run two Pipeline requests, and stop it."""
    root = data_root()
    _configure_results(root)
    cfg = h2h.load_config()
    build = build or current_build()
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "build": build,
        "cell": {key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")},
        "created_at": datetime.now(UTC).isoformat(),
        "valid": False,
        "failures": [],
        "engine_models_response": {
            "status": None,
            "json": {},
            "raw": "",
            "reason": "engine did not reach its readiness check",
        },
        "evidence_sources": {
            "engine_request": OPENAI_CHAT_SOURCE,
            "engine_served_models": OPENAI_MODELS_SOURCE,
        },
    }
    if cell.get("not_installed"):
        path = canary_receipt_path(root, build, cell)
        receipt.update(
            {
                "skipped": True,
                "status": "NOT_INSTALLED",
                "reason": cell["not_installed"],
                "reason_norm": normalise_reason(cell["not_installed"], cell),
                "receipt": str(path),
                "elapsed_s": round(time.monotonic() - started, 1),
            }
        )
        _write_json(path, receipt)
        return receipt
    log_dir = root / "engine_eval" / "logs" / build / _cell_id(cell)
    log_paths = (log_dir / "engine.stdout.log", log_dir / "engine.stderr.log")
    log_dir.mkdir(parents=True, exist_ok=True)
    for path in log_paths:
        path.touch(exist_ok=True)
    receipt["engine_logs"] = {
        "stdout": str(log_paths[0]),
        "stderr": str(log_paths[1]),
        "stdout_exists": False,
        "stderr_exists": False,
    }
    attempted = False

    def mark_started() -> None:
        nonlocal attempted
        attempted = True

    try:
        _execute_candidate_cell(cell, pipeline, cfg, receipt, log_paths, mark_started)
    except CandidateHTTPError as exc:
        receipt["failures"] = [f"candidate cell: {exc}"]
        receipt["upstream_http"] = {"status": exc.status, "body": exc.body}
    except (Exception, SystemExit) as exc:
        receipt["failures"] = [f"candidate cell: {type(exc).__name__}: {exc}"]
    finally:
        _finish_candidate_cell(cell, cfg, receipt, log_paths, attempted)
    path = canary_receipt_path(root, build, cell)
    receipt["receipt"] = str(path)
    receipt["elapsed_s"] = round(time.monotonic() - started, 1)
    _stamp_reason(receipt)
    _write_json(path, receipt)
    return receipt


# The live canary saw eval_backends_healthy move about two minutes after the
# engine answered. The Pipeline probes on a 30s loop. 180s is that lag plus one cycle.
PIPELINE_HEALTH_TIMEOUT_S = 180.0


def wait_pipeline_eval_backend(
    pipeline: str, backend_id: str, timeout_s: float = PIPELINE_HEALTH_TIMEOUT_S
) -> dict[str, Any]:
    """Block until GET /v1/backends reports this eval backend healthy.

    Production health counts and the periodic loop are unchanged. The cell is
    sent only after the Pipeline's own record says the pin is healthy.
    """
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while True:
        last = _pipeline_backend_list(pipeline)
        rows = last.get("data") if isinstance(last.get("data"), list) else []
        row = next((item for item in rows if item.get("id") == backend_id), None)
        if isinstance(row, dict) and row.get("healthy") is True:
            return {"ready": True, "backend": row}
        if time.monotonic() >= deadline:
            break
        time.sleep(2)
    raise Stage3BlockedError(
        f"pipeline did not report {backend_id} healthy within {timeout_s:.0f}s: "
        f"{json.dumps(last)[:800]}"
    )


def _pipeline_backend_list(pipeline: str) -> dict[str, Any]:
    """Read the Pipeline's backend list. Errors are the Pipeline's own answer."""
    url = f"{pipeline.rstrip('/')}/v1/backends"
    request = urllib.request.Request(url, headers=instrument._pipeline_headers())
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", "replace")
            payload = json.loads(body)
            return payload if isinstance(payload, dict) else {"raw": body[:800]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return {"status": exc.code, "raw": raw[:800]}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"error": str(exc)}


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


_BACKEND_HEALTH_REASON_RE = re.compile(
    r"not a healthy candidate backend|did not report eval-openai[A-Za-z0-9_.-]* healthy"
)


def normalise_reason(text: str, cell: dict[str, Any] | None = None) -> str:
    """Collapse ids and counts so the same failure matches across cells.

    A backend-health refusal keeps its engine in the normalised text: two engines
    can answer 400 for different root causes, and merging them hides that.
    """
    raw = _one_line(text)
    text = re.sub(r"eval-openai[A-Za-z0-9_.-]*", "eval-backend", raw)
    text = re.sub(r"\b\d+\b", "N", text)
    if cell is not None and cell.get("engine") and _BACKEND_HEALTH_REASON_RE.search(raw):
        return f"{text[:280]}; engine={cell['engine']}"
    return text[:300]


def _stamp_reason(receipt: dict[str, Any]) -> None:
    failures = [str(item) for item in receipt.get("failures") or []]
    if receipt.get("valid") is True and not failures:
        receipt["reason"] = "ok"
    else:
        receipt["reason"] = _one_line(
            failures[0] if failures else receipt.get("reason") or "invalid"
        )
    receipt["reason_norm"] = normalise_reason(str(receipt["reason"]), receipt.get("cell"))
    if "structural readiness" in str(receipt["reason"]):
        receipt["structural_readiness"] = True


def _cell_selector(cell: dict[str, Any]) -> str:
    return f"{cell['engine']}:{cell['mode']}:{cell['seat']}"


def _progress(
    cell: dict[str, Any], valid: bool, reason: str, elapsed_s: float, *, skipped: bool = False
) -> None:
    state = "not installed" if skipped else ("valid" if valid else "invalid")
    print(f"{_cell_selector(cell)} | {state} | {reason} | {elapsed_s:.0f}s", flush=True)


def _canary_should_stop(results: list[dict[str, Any]]) -> str | None:
    """Two consecutive invalid cells with one reason, or a blind readiness check."""
    if results and results[-1].get("structural_readiness"):
        return "structural readiness check cannot pass"
    if not results or results[-1].get("skipped"):
        return None
    if len(results) < 2 or results[-1].get("valid") is True:
        return None
    prev = results[-2]
    if prev.get("skipped"):
        return None
    if prev.get("valid") is not True and prev.get("reason_norm") == results[-1].get("reason_norm"):
        return f"2 consecutive cells: {results[-1].get('reason_norm')}"
    return None


def _select_canary_cells(only: str | None) -> list[dict[str, Any]]:
    cells = candidate_cells()
    if not only:
        return cells
    parts = only.split(":")
    if len(parts) != 3 or not all(parts):
        raise Stage3BlockedError(f"canary --cell must be engine:mode:seat, got {only!r}")
    engine, mode, seat = parts
    chosen = [
        cell
        for cell in cells
        if cell["engine"] == engine and cell["mode"] == mode and cell["seat"] == seat
    ]
    if len(chosen) != 1:
        raise Stage3BlockedError(f"canary --cell {only} matched {len(chosen)} cells")
    return chosen


def run_canary(pipeline: str, only: str | None = None) -> tuple[list[dict[str, Any]], int]:
    """Run matrix cells sequentially. Stop on a repeated reason or a blind readiness check."""
    build = current_build()
    results: list[dict[str, Any]] = []
    stop_reason = None
    for cell in _select_canary_cells(only):
        print(f"{_cell_selector(cell)} | start", flush=True)
        t0 = time.monotonic()
        try:
            receipt = run_cell(cell, pipeline, build)
        except Exception as exc:
            root = data_root()
            receipt = {
                "build": build,
                "cell": {
                    key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")
                },
                "valid": False,
                "failures": [f"candidate cell: {type(exc).__name__}: {exc}"],
                "evidence_sources": {},
                "elapsed_s": round(time.monotonic() - t0, 1),
            }
            _stamp_reason(receipt)
            receipt["receipt"] = str(canary_receipt_path(root, build, cell))
            _write_json(Path(receipt["receipt"]), receipt)
        results.append(receipt)
        stop_reason = _canary_should_stop(results)
        if stop_reason:
            break
    root = data_root()
    for receipt in results:
        cell = receipt.get("cell") or {}
        _progress(
            cell,
            bool(receipt.get("valid")),
            str(receipt.get("reason") or ""),
            float(receipt.get("elapsed_s") or 0),
            skipped=bool(receipt.get("skipped")),
        )
    summary = root / "engine_eval" / "canaries" / build / "table.json"
    _write_json(
        summary,
        {"build": build, "stopped": stop_reason, "cells": _canary_table(results)},
    )
    print(f"cells {len(results)} stopped={stop_reason or 'no'}", flush=True)
    invalid = any(
        item.get("valid") is not True and not item.get("skipped") for item in results
    ) or bool(stop_reason)
    return results, 2 if invalid else 0


def _canary_table(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table = []
    for result in results:
        cell = result.get("cell") or {}
        table.append(
            {
                "cell": cell,
                "valid": result.get("valid"),
                "status": result.get("status") or ("valid" if result.get("valid") else "invalid"),
                "skipped": bool(result.get("skipped")),
                "reason": result.get("reason"),
                "elapsed_s": result.get("elapsed_s"),
                "failures": result.get("failures"),
            }
        )
    return table


def protocol_issues() -> dict[str, list[str]]:
    """Validate protocol plan ids, seats, long windows, and the executable workloads."""
    cfg = h2h.load_config()
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}
    workloads = protocol.get("workloads") or []
    quality = next((item for item in workloads if item.get("id") == "quality-seat"), {})
    registered = {
        entry.get("quality_gate", {}).get("wfe_plan")
        for entry in cfg["models"].values()
        if entry.get("quality_gate")
    }
    known_workspaces = {
        entry["workspace"] for entry in (cfg.get("engine_eval") or {}).get("seats", {}).values()
    }
    supported = {
        "quality-seat",
        "tool-turn",
        "concurrency-mix",
        "long-context",
        "co-residence",
        "soak",
    }
    unbound = sorted(set(quality.get("plans") or []) - registered)
    missing_seats = {
        str(item.get("id") or index): [
            f"protocol seat {seat} has no engine_eval seat mapping"
            for seat in item.get("seats") or []
            if seat not in known_workspaces
        ]
        for index, item in enumerate(workloads)
        if any(seat not in known_workspaces for seat in item.get("seats") or [])
    }
    unsupported = {
        str(item.get("id") or index): ["no executor is registered for this workload"]
        for index, item in enumerate(workloads)
        if item.get("id") not in supported
    }
    windows = next((item for item in workloads if item.get("id") == "long-context"), {}).get(
        "windows", []
    )
    invalid_windows = [
        row
        for row in windows
        if row.get("seat") not in known_workspaces or int(row.get("context_tokens") or 0) <= 0
    ]
    return {
        **(
            {"protocol": ["protocol status must be APPROVED"]}
            if protocol.get("status") != "APPROVED"
            else {}
        ),
        **({"quality-seat": [f"plans lack a seat mapping: {unbound}"]} if unbound else {}),
        **missing_seats,
        **unsupported,
        **(
            {"long-context": [f"invalid context window mapping: {invalid_windows}"]}
            if invalid_windows
            else {}
        ),
    }


def _protocol_workload(workload_id: str) -> dict[str, Any]:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}
    return next(
        (item for item in protocol.get("workloads") or [] if item.get("id") == workload_id),
        {},
    )


def _stage3_arm_id(entry: dict[str, Any], role: str, workspace: str) -> str:
    """Resolve the campaign arm id with the same WFE expansion rules as execution."""
    from tests.wfe import campaign

    old = {key: os.environ.pop(key, None) for key in ("WFE_SAMPLING", "WFE_THINK")}
    try:
        prepared = campaign._with_reasoning_budget(
            campaign._with_card_sampling(entry, role, workspace), role, workspace
        )
        return campaign.arm_spec(prepared)[0]
    finally:
        for key, value in old.items():
            if value is not None:
                os.environ[key] = value


def _stage3_arms(
    cell: dict[str, Any], workspace_cfg: dict[str, Any], compare: bool
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    sampling_keys = (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "repeat_penalty",
        "presence_penalty",
        "frequency_penalty",
    )
    sampling = {key: workspace_cfg[key] for key in sampling_keys if key in workspace_cfg}
    candidate = {
        "model": cell["expected_model"],
        "backend": cell["backend"],
        "label": f"{cell['engine']}-{cell['mode']}",
        "sampling": sampling,
        **({"think": workspace_cfg["think"]} if "think" in workspace_cfg else {}),
    }
    candidate_id = _stage3_arm_id(
        candidate, "challenger" if compare else "incumbent", cell["workspace"]
    )
    if not compare:
        return {"incumbent": candidate, "challengers": []}, [
            {"role": "incumbent", "arm_id": candidate_id}
        ]
    incumbent = {
        "model": cell["expected_model"],
        "backend": "eval-openai-omlx-incumbent",
        "label": "omlx-incumbent",
        "sampling": sampling,
        **({"think": workspace_cfg["think"]} if "think" in workspace_cfg else {}),
    }
    incumbent_id = _stage3_arm_id(incumbent, "incumbent", cell["workspace"])
    return {"incumbent": incumbent, "challengers": [candidate]}, [
        {"role": "incumbent", "arm_id": incumbent_id},
        {"role": "challenger", "arm_id": candidate_id},
    ]


def _wfe_plan(
    cell: dict[str, Any], root: Path, build: str, workload_id: str, *, compare: bool
) -> tuple[Path, str, list[dict[str, str]], dict[str, Any]]:
    """Bind the registered WFE task to the candidate workspace and backend pins."""
    cfg = h2h.load_config()
    model = cfg["models"][cell["model"]]
    quality = model.get("quality_gate") or {}
    source_path = quality.get("wfe_plan")
    if not source_path:
        raise Stage3BlockedError(f"{cell['seat']} has no registered WFE quality plan")
    source_plan = yaml.safe_load((REPO / source_path).read_text(encoding="utf-8")) or {}
    source_workspace = str(quality.get("wfe_workspace") or "").split("::", 1)[0]
    source_workload = (source_plan.get("workloads") or {}).get(quality.get("wfe_workspace"))
    if source_workload is None:
        source_workload = (source_plan.get("workloads") or {}).get(source_workspace)
    if not source_workspace or not source_workload:
        raise Stage3BlockedError(f"{source_path} does not map {quality.get('wfe_workspace')!r}")
    task_id = str(quality.get("wfe_task") or "")
    task_ids = [str(item) for item in source_workload.get("home_tasks") or []]
    if task_id not in task_ids:
        raise Stage3BlockedError(f"{source_path} does not register WFE task {task_id!r}")
    workspaces = _bench_workspaces()
    workspace_cfg = workspaces.get(cell["workspace"]) or {}
    arms, selections = _stage3_arms(cell, workspace_cfg, compare)
    plan = {
        "repeats": 1,
        "workloads": {
            cell["workspace"]: {
                "tool_mode": source_workload.get("tool_mode", "production"),
                "home": source_workload.get("home"),
                "home_tasks": [task_id],
                "discovery": [],
                "source_workspace": source_workspace,
                "arms": arms,
            }
        },
    }
    output = root / "engine_eval" / "stage3" / build / f"{_cell_id(cell)}--{workload_id}.plan.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return output, str(source_path), selections, plan


def _wfe_failure_detail(stdout: str, stderr: str) -> str:
    """The arm's own verdict line, not just the last helper log line."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    blocked = [line for line in lines if line.startswith("BLOCKED") or " BLOCKED " in line]
    if blocked:
        return blocked[-1][-1000:]
    tail = stderr.strip() or (lines[-1] if lines else "no output")
    return tail[-1000:]


def _run_wfe_arm(
    plan_path: Path,
    campaign_id: str,
    workspace: str,
    arm: dict[str, str],
    root: Path,
    pipeline: str,
    *,
    append: bool,
    fresh_incumbent: bool = False,
) -> dict[str, Any]:
    campaign_dir = root / "tests" / "wfe" / "results" / "campaigns" / campaign_id
    debug_dir = root / "engine_eval" / "stage3" / campaign_id / "debug"
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "tests.wfe.campaign",
        "--plan",
        str(plan_path),
        "--campaign-id",
        campaign_id,
        "--arm",
        arm["arm_id"],
        "--workspace",
        workspace,
        "--tier",
        "realuse",
        "--repeats",
        "1",
        "--no-halt",
        "--debug-dir",
        str(debug_dir),
    ]
    if append or (campaign_dir / "manifest.json").is_file():
        command.append("--append")
    if fresh_incumbent:
        command.append("--fresh-incumbent")
    env = {
        **os.environ,
        "PORTAL_ENABLE_EVAL": "1",
        "WFE_ENGINE": "pipeline",
        "WFE_CHAT_BASE_URL": pipeline,
    }
    env.pop("WFE_SAMPLING", None)
    env.pop("WFE_THINK", None)
    result = subprocess.run(
        command, cwd=REPO, env=env, capture_output=True, text=True, timeout=3600
    )
    output_base = root / "engine_eval" / "stage3" / campaign_id
    output_base.mkdir(parents=True, exist_ok=True)
    (output_base / f"{arm['role']}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (output_base / f"{arm['role']}.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise Stage3BlockedError(
            f"WFE {arm['role']} exited {result.returncode}: "
            f"{_wfe_failure_detail(result.stdout, result.stderr)}"
        )
    if not (campaign_dir / "manifest.json").is_file():
        raise Stage3BlockedError(f"WFE campaign did not write {campaign_dir / 'manifest.json'}")
    manifest = json.loads((campaign_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        row
        for row in manifest.get("rows") or []
        if row.get("arm_role") == arm["role"] and row.get("arm") == arm["arm_id"]
    ]
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": str(output_base / f"{arm['role']}.stdout.log"),
        "stderr": str(output_base / f"{arm['role']}.stderr.log"),
        "campaign": str(campaign_dir),
        "rows": rows,
    }


def _prepare_host(cfg: dict[str, Any]) -> dict[str, Any]:
    """Unload both production engines and refuse to start if anything is left resident."""
    host_prep = _prepare_production_models(cfg)
    if not host_prep["valid"]:
        raise Stage3BlockedError(f"pre-workload unload failed: {host_prep['failures']}")
    return host_prep


@contextlib.contextmanager
def _running_cells(
    cells: list[dict[str, Any]],
    root: Path,
    build: str,
    context_tokens: int | None = None,
    host_prep: dict[str, Any] | None = None,
):
    """Start distinct canary-qualified managed engines and always verify shutdown.

    ``host_prep`` lets a caller prep the host itself (and take its baseline
    snapshots after that) instead of having the unload land inside the window.
    """
    cfg = h2h.load_config()
    managed = [cell for cell in cells if not _is_external(cell)]
    if len({cell["engine"] for cell in managed}) != len(managed):
        raise Stage3BlockedError("co-resident cells must use distinct fixed engine ports")
    for cell in cells:
        _gate_canary(root, build, cell)
        if not _is_external(cell) and h2h.pid_on_port(cell["port"]):
            raise Stage3BlockedError(f"candidate port {cell['port']} is already occupied")
    # Every workload gets a quiet host: an engine left resident by the workload
    # before this one fails the next engine's memory preflight.
    host_prep = host_prep if host_prep is not None else _prepare_host(cfg)
    okay, reason = h2h.start_gate(cfg)
    if not okay:
        raise Stage3BlockedError(f"swap start gate: {reason}")
    started: list[dict[str, Any]] = []
    infos: dict[str, Any] = {}
    with h2h.single_flight():
        try:
            for cell in managed:
                log_dir = root / "engine_eval" / "stage3" / build / "logs" / _cell_id(cell)

                def remember_started(target: dict[str, Any] = cell) -> None:
                    started.append(target)

                infos[cell["engine"]] = h2h.start_managed(
                    cfg,
                    cell["engine"],
                    cell["model"],
                    cell["mode"],
                    context_tokens=context_tokens,
                    log_paths=(log_dir / "engine.stdout.log", log_dir / "engine.stderr.log"),
                    on_started=remember_started,
                )
            yield infos, host_prep
        finally:
            errors = []
            for cell in reversed(started):
                try:
                    h2h.stop_managed(cfg, cell["engine"])
                    listener = h2h.pid_on_port(cell["port"])
                    if listener:
                        errors.append(
                            f"{cell['engine']} left port {cell['port']} on pid {listener}"
                        )
                except (OSError, subprocess.CalledProcessError, SystemExit) as exc:
                    try:
                        listener = h2h.pid_on_port(cell["port"])
                    except (OSError, subprocess.CalledProcessError) as probe_exc:
                        listener = f"probe failed: {probe_exc}"
                    errors.append(f"{cell['engine']} stop failed: {exc}; listener={listener}")
            if errors:
                raise Stage3BlockedError("; ".join(errors))


def _pipeline_request(
    cell: dict[str, Any], pipeline: str, messages: list[dict[str, str]], **extra: Any
) -> dict[str, Any]:
    body = {
        "model": cell["workspace"],
        "messages": messages,
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "portal_backend": cell["backend"],
        **extra,
    }
    url = f"{pipeline.rstrip('/')}/v1/chat/completions"
    started = time.monotonic()
    row = _candidate_request(url, body)
    return {
        "workspace": cell["workspace"],
        "backend": cell["backend"],
        "expected_model": cell["expected_model"],
        "route": row.get("header"),
        "engine_model": row.get("engine_model"),
        "text": row.get("text", ""),
        "elapsed_s": round(time.monotonic() - started, 3),
    }


def _route_valid(row: dict[str, Any]) -> bool:
    match = instrument._ROUTE_RE.match(str(row.get("route") or ""))
    return bool(
        match
        and (match.group(1), match.group(2), match.group(3))
        == (row["workspace"], row["backend"], row["expected_model"])
        and row.get("engine_model") == row["expected_model"]
    )


def _valid_cell_for_seat(
    seat: str,
    build: str,
    root: Path,
    excluded_engines: set[str],
    preferred: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cells = candidate_cells()
    if preferred and preferred["seat"] == seat:
        cells = [preferred, *[row for row in cells if row != preferred]]
    for cell in cells:
        if cell["seat"] != seat or cell["mode"] != "plain" or cell["engine"] in excluded_engines:
            continue
        try:
            require_valid_canary(root, build, cell)
        except Stage3BlockedError:
            continue
        return cell
    return None


def _run_one_wfe_selection(
    cell: dict[str, Any],
    selection: dict[str, str],
    index: int,
    plan_path: Path,
    campaign_id: str,
    root: Path,
    build: str,
    pipeline: str,
    compare: bool,
) -> dict[str, Any]:
    args = (plan_path, campaign_id, cell["workspace"], selection, root, pipeline)
    options = {
        "append": index > 0,
        "fresh_incumbent": index == 0 and selection["role"] == "incumbent",
    }
    run_candidate = selection["role"] == ("challenger" if compare else "incumbent")
    if run_candidate:
        with _running_cells([cell], root, build) as (_infos, host_prep):
            run = _run_wfe_arm(*args, **options)
        run["host_prep"] = host_prep
        return run
    # The incumbent arm loads its model on oMLX through the Pipeline. The host
    # still has to be quiet first, or that load meets the previous model's footprint.
    host_prep = _prepare_host(h2h.load_config())
    okay, reason = h2h.start_gate(h2h.load_config())
    if not okay:
        raise Stage3BlockedError(f"swap start gate: {reason}")
    run = _run_wfe_arm(*args, **options)
    run["host_prep"] = host_prep
    return run


def _run_wfe_selections(
    cell: dict[str, Any],
    selections: list[dict[str, str]],
    plan_path: Path,
    campaign_id: str,
    root: Path,
    build: str,
    pipeline: str,
    compare: bool,
) -> list[dict[str, Any]]:
    return [
        _run_one_wfe_selection(
            cell, selection, index, plan_path, campaign_id, root, build, pipeline, compare
        )
        for index, selection in enumerate(selections)
    ]


def _read_wfe_arm_rows(
    runs: list[dict[str, Any]], selections: list[dict[str, str]]
) -> list[dict[str, Any]]:
    from tests.wfe.campaign import _row_path

    campaign_dir = Path(runs[-1]["campaign"])
    manifest = json.loads((campaign_dir / "manifest.json").read_text(encoding="utf-8"))
    arms = []
    for selection in selections:
        stubs = [
            row
            for row in manifest.get("rows") or []
            if row.get("arm_role") == selection["role"] and row.get("arm") == selection["arm_id"]
        ]
        data = [
            json.loads(_row_path(campaign_dir, stub["run_id"]).read_text(encoding="utf-8"))
            for stub in stubs
            if _row_path(campaign_dir, stub["run_id"]).is_file()
        ]
        arms.append({"role": selection["role"], "arm_id": selection["arm_id"], "rows": data})
    return arms


def _probe_row(cell: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """The route fields a Pipeline probe row is judged on."""
    return {
        "workspace": cell["workspace"],
        "backend": cell["backend"],
        "expected_model": cell["expected_model"],
        "route": raw.get("header"),
        "engine_model": raw.get("engine_model"),
        "text": raw.get("text", ""),
    }


def _tool_turn_reason(
    tool: dict[str, Any], routes_ok: bool, answer_used_result: bool, answer: str
) -> str:
    """One line saying what the tool turn did, for a receipt that never has an empty verdict."""
    if tool.get("ok") is not True:
        return f"tool turn: no usable get_weather call — {tool.get('why') or tool}"
    if not routes_ok:
        return "tool turn: a leg did not route to the pinned engine model"
    if not answer_used_result:
        head = " ".join(str(answer).split())[:80]
        return f"post-tool turn did not use the tool result: {head!r}"
    return "tool turn: get_weather called and the post-tool turn used its result"


def _run_tool_turn(cell: dict[str, Any], root: Path, build: str, pipeline: str) -> dict[str, Any]:
    """A tool call and the post-tool turn, both through the Pipeline.

    The registered WFE quality task is graded by the injected RAG context, so it can
    pass without ever calling a tool; this workload supplies the call and its result.
    """
    protocol = _protocol_workload("tool-turn")
    url = f"{pipeline.rstrip('/')}/v1/chat/completions"
    call_body = _probe_body(
        cell, TOOL_TURN_PROMPT, {"tools": instrument._TOOL_SPEC, "tool_choice": _GET_WEATHER_CHOICE}
    )
    with _running_cells([cell], root, build) as (_infos, host_prep):
        first = _candidate_request(url, call_body)
        calls = first["message"].get("tool_calls") or []
        tool = instrument.tool_from_message(first["message"])
        call_id = (calls[0] if calls else {}).get("id") or "call_tool_turn"
        follow_up = {
            **call_body,
            "messages": [
                {"role": "user", "content": TOOL_TURN_PROMPT},
                {
                    "role": "assistant",
                    "content": first["message"].get("content") or "",
                    "tool_calls": calls,
                },
                {"role": "tool", "tool_call_id": call_id, "content": TOOL_TURN_RESULT},
                {"role": "user", "content": TOOL_TURN_FOLLOW_UP},
            ],
            "tool_choice": "auto",
        }
        second = _candidate_request(url, follow_up)
    rows = [_probe_row(cell, first), _probe_row(cell, second)]
    routes_ok = all(_route_valid(row) for row in rows)
    answer = str((second["message"] or {}).get("content") or "")
    used_result = "18" in answer
    valid = tool.get("ok") is True and routes_ok and used_result
    return {
        "status": "PASS" if valid else "FAIL",
        "valid": valid,
        "verdict": "pass" if valid else "fail",
        "reason": _tool_turn_reason(tool, routes_ok, used_result, answer),
        "pass_rule": protocol.get("pass"),
        "turns": 2,
        "tool_calls": 1 if tool.get("ok") is True else 0,
        "tool_errors": 0,
        "requests": [call_body, follow_up],
        "routes": [{"header": row["route"], "engine_model": row["engine_model"]} for row in rows],
        "tool_call": tool,
        "tool_result": TOOL_TURN_RESULT,
        "post_tool_answer": answer,
        "host_prep": host_prep,
    }


def _grade_single_outcome(result: dict[str, Any], arms: list[dict[str, Any]]) -> None:
    """One pinned arm. Used for an incumbent quality cell, which has no challenger."""
    row = (arms[0].get("rows") or [{}])[0] if arms else {}
    outcome = row.get("outcome")
    if outcome not in ("PASS", "FAIL"):
        result.update(
            {
                "status": "BLOCKED",
                "valid": False,
                "reason": "WFE did not produce one gradeable row",
            }
        )
        return
    result["incumbent_outcome"] = outcome
    result["valid"] = outcome == "PASS"
    result["status"] = "PASS" if result["valid"] else "FAIL"


def _grade_quality_result(
    result: dict[str, Any],
    arms: list[dict[str, Any]],
    compare: bool,
    *,
    single_outcome: bool = False,
) -> None:
    if single_outcome:
        _grade_single_outcome(result, arms)
        return
    if compare:
        role_rows = {arm["role"]: arm["rows"] for arm in arms}
        inc, cand = role_rows.get("incumbent") or [], role_rows.get("challenger") or []
        gradeable = len(inc) == len(cand) == 1 and all(
            row.get("outcome") in ("PASS", "FAIL") for row in (inc[0], cand[0])
        )
        if not gradeable:
            result.update(
                {
                    "status": "BLOCKED",
                    "valid": False,
                    "reason": "WFE did not produce one gradeable row per arm",
                }
            )
            return
        result.update(
            {
                "incumbent_outcome": inc[0]["outcome"],
                "candidate_outcome": cand[0]["outcome"],
            }
        )
        result["valid"] = cand[0]["outcome"] == "PASS" or inc[0]["outcome"] == "FAIL"
    else:
        row = (arms[0].get("rows") or [{}])[0]
        result.update(
            {
                "tool_calls": row.get("tool_calls"),
                "turns": row.get("turns"),
                "tool_errors": row.get("tool_errors"),
                "valid": row.get("outcome") == "PASS"
                and int(row.get("turns") or 0) >= 2
                and int(row.get("tool_calls") or 0) >= 1
                and int(row.get("tool_errors") or 0) == 0,
            }
        )
    result["status"] = "PASS" if result["valid"] else "FAIL"


def _run_quality_workload(
    cell: dict[str, Any], workload_id: str, root: Path, build: str, pipeline: str, *, compare: bool
) -> dict[str, Any]:
    plan_path, source_plan, selections, _plan = _wfe_plan(
        cell, root, build, workload_id, compare=compare
    )
    campaign_id = (
        "engine_eval_"
        + hashlib.sha256(
            f"{build}:{_cell_id(cell)}:{workload_id}:{uuid.uuid4().hex}".encode()
        ).hexdigest()[:24]
    )
    runs = _run_wfe_selections(
        cell, selections, plan_path, campaign_id, root, build, pipeline, compare
    )
    arms = _read_wfe_arm_rows(runs, selections)
    result: dict[str, Any] = {
        "status": "PASS",
        "valid": True,
        "pass_rule": _protocol_workload(workload_id).get("pass"),
        "source_wfe_plan": source_plan,
        "wfe_plan": str(plan_path),
        "campaign_id": campaign_id,
        "runs": runs,
        "arms": arms,
    }
    _grade_quality_result(
        result, arms, compare, single_outcome=workload_id == "quality-seat" and not compare
    )
    return result


def _mix_fields(as_json: bool) -> dict[str, Any]:
    """JSON leg is tool-less, like production hunt; chat leaves workspace tools alone."""
    if not as_json:
        return {}
    return {"response_format": {"type": "json_object"}, "tools": []}


def _mix_request(
    target: dict[str, Any], pipeline: str, label: str, as_json: bool
) -> dict[str, Any]:
    """One mix request. An engine HTTP rejection is a failed row, not a raised crash."""
    message = (
        f"Return only a JSON object with keys ok=true and slot={label}."
        if as_json
        else f"Reply exactly OK for request {label}."
    )
    try:
        result = _pipeline_request(
            target, pipeline, [{"role": "user", "content": message}], **_mix_fields(as_json)
        )
    except CandidateHTTPError as exc:
        return {
            "label": label,
            "valid": False,
            "reason": str(exc),
            "upstream_http": {"status": exc.status, "body": exc.body},
            "workspace": target["workspace"],
            "backend": target["backend"],
            "expected_model": target["expected_model"],
        }
    if as_json:
        try:
            parsed = json.loads(result["text"])
            result["json_valid"] = parsed.get("ok") is True and parsed.get("slot") == label
        except json.JSONDecodeError:
            result["json_valid"] = False
    result["label"] = label
    result["valid"] = _route_valid(result) and result.get("json_valid", True)
    return result


def _run_concurrency_workload(
    cell: dict[str, Any], root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    seats = ("hunt", "daily-moe", "task-router")
    if cell["seat"] not in seats:
        return {
            "status": "NOT_APPLICABLE",
            "valid": True,
            "reason": "cell seat is outside the registered mix",
        }
    chosen = [cell]
    for seat in seats:
        if seat == cell["seat"]:
            continue
        candidate = _valid_cell_for_seat(seat, build, root, {item["engine"] for item in chosen})
        if candidate is None:
            raise Stage3BlockedError(
                f"no distinct current-build canary-qualified engine for {seat}"
            )
        chosen.append(candidate)
    by_seat = {item["seat"]: item for item in chosen}
    with _running_cells(chosen, root, build) as (_infos, host_prep):
        specs = []
        for index in range(8):
            specs.append((by_seat["hunt"], f"json-{index}", True))
        for index in range(2):
            specs.append((by_seat["daily-moe"], f"chat-{index}", False))
            specs.append((by_seat["task-router"], f"router-{index}", False))

        def send(spec: tuple[dict[str, Any], str, bool]) -> dict[str, Any]:
            return _mix_request(spec[0], pipeline, spec[1], spec[2])

        with ThreadPoolExecutor(max_workers=12) as pool:
            requests = list(pool.map(send, specs))
    failed = [row for row in requests if not row["valid"]]
    return {
        "status": "PASS" if not failed else "FAIL",
        "valid": not failed,
        "pass_rule": _protocol_workload("concurrency-mix").get("pass"),
        "request_shapes": {
            "json": "response_format json_object and tools []; production hunt declares no tools",
            "chat": "no response_format; workspace tools stay, matching auto-daily",
        },
        "cells": [
            {"engine": item["engine"], "seat": item["seat"], "port": item["port"]}
            for item in chosen
        ],
        "requests": requests,
        "failures": [row["label"] for row in failed],
        "host_prep": host_prep,
    }


def _context_readback(payload: dict[str, Any], expected_model: str) -> dict[str, Any]:
    row = _model_row(payload, expected_model)
    keys = (
        "context_length",
        "max_model_len",
        "max_context",
        "max_context_length",
        "context_window",
        "ctx_size",
        "n_ctx",
        "max_seq_len",
    )
    return {key: row[key] for key in keys if key in row}


def _long_context_tokens(cell: dict[str, Any]) -> int | None:
    """Protocol windows name the bench workspace; the seat slug is the same window."""
    windows = {
        str(row["seat"]): int(row["context_tokens"])
        for row in (_protocol_workload("long-context").get("windows") or [])
    }
    for key in (cell.get("workspace"), cell.get("seat")):
        if key in windows:
            return windows[key]
    aliases = {
        name.removeprefix("bench-engine-"): tokens
        for name, tokens in windows.items()
        if str(name).startswith("bench-engine-")
    }
    seat = cell.get("seat")
    if seat in aliases:
        return aliases[seat]
    return None


def _run_long_context(
    cell: dict[str, Any], root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    protocol = _protocol_workload("long-context")
    context_tokens = _long_context_tokens(cell)
    if context_tokens is None:
        return {
            "status": "NOT_APPLICABLE",
            "valid": True,
            "reason": "seat has no registered long-context window",
        }
    cfg = h2h.load_config()
    tokenizer = _candidate_tokenizer(cfg, cell)
    if tokenizer is None:
        raise Stage3BlockedError("checkpoint tokenizer.json is not available locally")
    source = h2h.prefill_text(int(context_tokens * h2h.CHARS_PER_TOKEN * 2))
    marker_pos = int(len(source) * 0.72)
    match = re.search(r"\b[A-Za-z_][A-Za-z0-9_]{5,}\b", source[marker_pos:])
    if match is None:
        raise Stage3BlockedError("repository source has no retrievable long-context needle")
    needle = match.group(0)
    context = source[:marker_pos] + f"\n\nNeedle record: {needle}\n\n" + source[marker_pos:]
    question = (
        "Return only the exact identifier from the Needle record near the middle of this context."
    )
    target_tokens = context_tokens - 256
    lo, hi, best = 0, len(context), ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = context[:mid]
        count = instrument.count_tokens(candidate + "\n" + question, tokenizer)
        if count is None:
            raise Stage3BlockedError("tokenizer could not count the long-context prompt")
        if count <= target_tokens:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    input_tokens = instrument.count_tokens(best + "\n" + question, tokenizer)
    if input_tokens is None or input_tokens < context_tokens * 0.9:
        raise Stage3BlockedError(
            f"local repository text only fills {input_tokens} tokens of {context_tokens}"
        )
    with _running_cells([cell], root, build, context_tokens=context_tokens) as (
        _infos,
        host_prep,
    ):
        models = _models_payload(cell["base"])
        settings = _context_readback(models["json"], cell["expected_model"])
        url = f"{cell['base'].rstrip('/')}/v1/chat/completions"
        request = {
            "model": cell["expected_model"],
            "messages": [{"role": "user", "content": best + "\n" + question}],
            "temperature": 0,
            "max_tokens": 128,
            "stream": False,
        }
        response = instrument._one_chat(url, request, instrument._pipeline_headers())
    setting_values = [int(value) for value in settings.values() if isinstance(value, (int, float))]
    context_ok = context_tokens in setting_values
    needle_ok = needle in response.get("text", "")
    valid = context_ok and needle_ok
    return {
        "status": "PASS" if valid else "FAIL",
        "valid": valid,
        "pass_rule": protocol.get("pass"),
        "request_path": url,
        "context_tokens": context_tokens,
        "input_tokens": input_tokens,
        "context_readback": settings,
        "models_response": models,
        "needle": needle,
        "answer": response.get("text", ""),
        "route": "direct engine request; engine context readback and needle response are recorded",
        "host_prep": host_prep,
    }


def _process_sample(cell: dict[str, Any]) -> dict[str, Any]:
    """Sample engine-specific resident memory and independent macOS wired pages."""
    cfg = h2h.load_config()
    port = cell.get("observe_port") or cell.get("port")
    pid = h2h.pid_on_port(port) if port else None
    if not pid:
        raise Stage3BlockedError(f"no process is listening on {port}")
    rows = instrument.parse_ps_tree(
        subprocess.check_output(["ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=10)
    )
    footprint = None
    model_row = {}
    if cfg["engines"][cell["engine"]].get("requires") != "gguf":
        raw = subprocess.check_output(["footprint", "-p", str(pid)], text=True, timeout=10)
        footprint = instrument.parse_footprint(raw).get("phys_footprint_gb")
        models = _models_payload(cell["base"])
        model_row = _model_row(models["json"], cell["expected_model"])
    vm = instrument.parse_vm_stat(subprocess.check_output(["vm_stat"], text=True, timeout=10))
    wired = vm.get("wired_pages")
    page = vm.get("page_bytes")
    swap = h2h.swap_now().get("used_mb")
    tree_rss = instrument.tree_rss_gb(rows, pid)
    resident_bytes = next(
        (
            model_row.get(key)
            for key in ("bytes_resident", "resident_bytes", "memory_bytes")
            if isinstance(model_row.get(key), (int, float)) and model_row[key] > 0
        ),
        None,
    )
    is_gguf = cfg["engines"][cell["engine"]].get("requires") == "gguf"
    primary_gb = (
        tree_rss
        if is_gguf
        else (float(resident_bytes) / 1024**3 if resident_bytes is not None else footprint)
    )
    primary_source = (
        "process-tree RSS; llama.cpp maps the GGUF into its process"
        if is_gguf
        else "engine /v1/models resident-bytes field"
        if resident_bytes is not None
        else "macOS footprint phys_footprint"
    )
    return {
        "candidate_resident_gb": primary_gb,
        "candidate_resident_source": primary_source,
        "engine_resident_bytes": resident_bytes,
        "tree_rss_gb": tree_rss,
        "phys_footprint_gb": footprint,
        "vm_wired_gb": wired * page / (1024**3) if wired is not None and page else None,
        "swap_used_mb": swap,
    }


def _run_soak_workload(
    cell: dict[str, Any], root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    protocol = _protocol_workload("soak")
    duration_s = int(protocol.get("duration_min", 45)) * 60
    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    next_sample_s = 300
    with _running_cells([cell], root, build) as (_infos, host_prep):
        while time.monotonic() - started < duration_s:
            _pipeline_request(
                cell,
                pipeline,
                [{"role": "user", "content": "Reply exactly OK."}],
                max_tokens=8,
            )
            elapsed = int(time.monotonic() - started)
            if elapsed >= next_sample_s:
                samples.append({"elapsed_s": elapsed, **_process_sample(cell)})
                checkpoint = (
                    root
                    / "engine_eval"
                    / "stage3"
                    / build
                    / f"{_cell_id(cell)}--soak.progress.json"
                )
                _write_json(checkpoint, {"cell": _cell_id(cell), "samples": samples})
                next_sample_s += 300
            time.sleep(min(60, max(1, duration_s - int(time.monotonic() - started))))
        samples.append({"elapsed_s": duration_s, **_process_sample(cell)})
    plateau, final = samples[0], samples[-1]
    readings = ("candidate_resident_gb", "vm_wired_gb")
    deltas = {
        key: abs(float(plateau[key]) - float(final[key]))
        for key in readings
        if plateau.get(key) is not None and final.get(key) is not None
    }
    expected = set(readings)
    valid = expected <= set(deltas) and all(delta <= 2.0 for delta in deltas.values())
    return {
        "status": "PASS" if valid else "FAIL",
        "valid": valid,
        "pass_rule": protocol.get("pass"),
        "duration_min": duration_s / 60,
        "samples": samples,
        "candidate_resident_source": final["candidate_resident_source"],
        "independent_memory_source": "vm_stat wired pages, compared with the 5-minute plateau",
        "plateau_to_final_gb": deltas,
        "tolerance_gb": 2.0,
        "host_prep": host_prep,
    }


def _run_co_residence(
    cell: dict[str, Any], root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    seats = ("task-router", "daily-moe", "hunt")
    if cell["seat"] not in seats:
        return {
            "status": "NOT_APPLICABLE",
            "valid": True,
            "reason": "cell seat is outside the registered co-residence set",
        }
    chosen = [cell]
    for seat in seats:
        if seat == cell["seat"]:
            continue
        candidate = _valid_cell_for_seat(seat, build, root, {item["engine"] for item in chosen})
        if candidate is None:
            raise Stage3BlockedError(
                f"no distinct current-build canary-qualified engine for {seat}"
            )
        chosen.append(candidate)
    # Unload the production engines BEFORE the baseline: growth then measures
    # only the co-resident engines, not the release of a model they displaced.
    cfg = h2h.load_config()
    host_prep = _prepare_host(cfg)
    vm_before = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    residency_before = _candidate_residency(cfg)
    swap_before = h2h.swap_now().get("used_mb")
    with _running_cells(chosen, root, build, host_prep=host_prep) as (_infos, _prep):
        requests = [
            _pipeline_request(target, pipeline, [{"role": "user", "content": "Reply exactly OK."}])
            for target in chosen
        ]
        swap_after = h2h.swap_now().get("used_mb")
        residency_after = _candidate_residency(cfg)
        vm_after = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    growth = None if swap_before is None or swap_after is None else swap_after - swap_before
    delta = instrument.vm_deltas_gb(
        instrument.parse_vm_stat(vm_before), instrument.parse_vm_stat(vm_after)
    )
    swap_gate = (
        swap_after is not None
        and swap_after <= float(cfg["guard"]["max_start_swap_used_mb"])
        and growth is not None
        and growth <= float(cfg["guard"]["max_swap_growth_mb"])
    )
    valid = all(_route_valid(row) for row in requests) and swap_gate
    return {
        "status": "PASS" if valid else "FAIL",
        "valid": valid,
        "pass_rule": _protocol_workload("co-residence").get("pass"),
        "cells": [
            {"engine": row["engine"], "seat": row["seat"], "port": row["port"]} for row in chosen
        ],
        "requests": requests,
        "residency_before": residency_before,
        "residency_after": residency_after,
        "vm_stat_delta": delta,
        "swap_before_mb": swap_before,
        "swap_after_mb": swap_after,
        "swap_growth_mb": growth,
        "swap_gate": swap_gate,
        "host_prep": host_prep,
    }


def _execute_stage3_workload(
    cell: dict[str, Any], workload: str, root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    registered = _protocol_workload(workload)
    if not registered:
        raise Stage3BlockedError(f"workload {workload!r} is not registered in the protocol")
    eligible = {
        str(seat) for seat in registered.get("seats") or [] if str(seat).startswith("bench-engine-")
    }
    if eligible and cell["workspace"] not in eligible:
        return {
            "status": "NOT_APPLICABLE",
            "valid": True,
            "reason": f"{cell['workspace']} is outside this workload's registered seats",
        }
    all_issues = protocol_issues()
    issues = [*(all_issues.get("protocol") or []), *(all_issues.get(workload) or [])]
    if issues:
        raise Stage3BlockedError("; ".join(issues))
    if workload == "quality-seat":
        return _run_quality_workload(
            cell, workload, root, build, pipeline, compare=not _is_external(cell)
        )
    if workload == "tool-turn":
        not_applicable = _tool_surface_reason(cell)
        if not_applicable:
            return {
                "status": "NOT_APPLICABLE",
                "valid": True,
                "verdict": "not_applicable",
                "reason": f"tool turn: not applicable — {not_applicable}",
            }
        return _run_tool_turn(cell, root, build, pipeline)
    if workload == "concurrency-mix":
        return _run_concurrency_workload(cell, root, build, pipeline)
    if workload == "long-context":
        return _run_long_context(cell, root, build, pipeline)
    if workload == "co-residence":
        return _run_co_residence(cell, root, build, pipeline)
    if workload == "soak":
        return _run_soak_workload(cell, root, build, pipeline)
    raise Stage3BlockedError(f"workload {workload!r} has no task-specific runner mapping")


def _flag_non_comparable_quality(result: dict[str, Any], canary: dict[str, Any]) -> None:
    """A template difference makes this cell's quality comparison undecidable."""
    if "candidate_outcome" not in result and "incumbent_outcome" not in result:
        return
    template = (canary.get("evidence") or {}).get("template") or {}
    if not isinstance(template, dict) or template.get("quality_comparable") is not False:
        return
    detail = str(template.get("template_differs") or "rendered prompt differs from the incumbent")
    result.update(
        {
            "not_comparable": True,
            "status": "NOT_COMPARABLE",
            "reason": f"quality non-comparable: {detail}",
        }
    )


def _record_workload_swap(result: dict[str, Any], before: float | None) -> None:
    """Rule 4: growth past the protocol limit fails this workload and stops the run."""
    after = h2h.swap_now().get("used_mb")
    growth = None if before is None or after is None else after - before
    limit = float(h2h.load_config()["guard"]["max_swap_growth_mb"])
    result["swap_before_mb"] = before
    result["swap_after_mb"] = after
    result["swap_growth_mb"] = growth
    result["swap_growth_limit_mb"] = limit
    if growth is None or growth <= limit:
        return
    result["valid"] = False
    result["status"] = "FAIL"
    result["swap_gate"] = False
    result["swap_stop"] = True
    reading = (
        f"swap grew {growth:.0f}MB (before {before:.0f}MB, after {after:.0f}MB) > {limit:.0f}MB"
    )
    prior = str(result.get("reason") or "")
    result["reason"] = reading if not prior or prior == reading else f"{reading}; {prior}"


def run_stage3(
    cell: dict[str, Any],
    workload: str,
    build: str | None = None,
    pipeline: str = "http://127.0.0.1:9099",
) -> dict[str, Any]:
    """Run one protocol workload after its exact cell passes the current-build canary."""
    root = data_root()
    _configure_results(root)
    build = build or current_build()
    path = root / "engine_eval" / "stage3" / build / f"{_cell_id(cell)}--{workload}.json"
    swap_before = h2h.swap_now().get("used_mb")
    try:
        canary = _gate_canary(root, build, cell)
        if path.is_file():
            prior = json.loads(path.read_text(encoding="utf-8"))
            if (
                prior.get("build") == build
                and prior.get("workload") == workload
                and prior.get("cell_id") == _cell_id(cell)
                and prior.get("status") in {"PASS", "NOT_APPLICABLE"}
                and prior.get("valid") is True
            ):
                return prior
        result = _execute_stage3_workload(cell, workload, root, build, pipeline)
        result["canary"] = canary.get("receipt", str(canary_receipt_path(root, build, cell)))
        _flag_non_comparable_quality(result, canary)
    except Stage3BlockedError as exc:
        result = {"valid": False, "status": "BLOCKED", "reason": str(exc)}
    except CandidateHTTPError as exc:
        result = {
            "valid": False,
            "status": "FAIL",
            "reason": str(exc),
            "upstream_http": {"status": exc.status, "body": exc.body},
        }
    except (Exception, SystemExit) as exc:
        result = {"valid": False, "status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"}
    _record_workload_swap(result, swap_before)
    _stamp_outcome(result)
    result.update(
        {
            "build": build,
            "cell": {
                key: cell.get(key) for key in ("engine", "mode", "seat", "workspace", "model")
            },
            "cell_id": _cell_id(cell),
            "workload": workload,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    result["receipt"] = str(path)
    _write_json(path, result)
    return result


# Upper bounds for the plan print. Not measurements.
_WORKLOAD_ESTIMATE_S = {
    "quality-seat": 20 * 60,
    "tool-turn": 5 * 60,
    "long-context": 15 * 60,
    "concurrency-mix": 15 * 60,
    "co-residence": 10 * 60,
    "soak": 45 * 60,
}
_EARLY_WORKLOADS = ("quality-seat", "tool-turn")
_LATER_WORKLOADS = ("long-context", "concurrency-mix", "co-residence")
_EVAL_PORTS = range(11234, 11245)
_CELL_KEYS = (
    "seat",
    "workspace",
    "engine",
    "engine_kind",
    "mode",
    "model",
    "expected_model",
    "backend",
    "port",
    "observe_port",
    "base",
    "argv",
    "cwd",
    "launch_error",
)


def _outcome_reason(result: dict[str, Any]) -> str:
    """One line for a receipt that did not produce a reason of its own."""
    status = str(result.get("status") or ("PASS" if result.get("valid") else "FAIL"))
    parts = [f"status {status}"]
    for key in ("candidate_outcome", "incumbent_outcome", "tool_calls", "turns", "tool_errors"):
        if result.get(key) is not None:
            parts.append(f"{key}={result[key]}")
    return ", ".join(parts)


_VERDICT_BY_STATUS = {
    "PASS": "pass",
    "FAIL": "fail",
    "NOT_APPLICABLE": "not_applicable",
    "NOT_COMPARABLE": "not_comparable",
    "BLOCKED": "blocked",
}


def _stamp_outcome(result: dict[str, Any]) -> None:
    """Every receipt carries a pass/fail verdict and a one-line reason."""
    status = str(result.get("status") or ("PASS" if result.get("valid") is True else "FAIL"))
    result["verdict"] = _VERDICT_BY_STATUS.get(
        status, "pass" if result.get("valid") is True else "fail"
    )
    if not result.get("reason"):
        result["reason"] = _outcome_reason(result)


def _stage3_dir(root: Path, build: str) -> Path:
    return root / "engine_eval" / "stage3" / build


def _cell_summary_path(root: Path, build: str, cell: dict[str, Any]) -> Path:
    return _stage3_dir(root, build) / "cells" / f"{_cell_id(cell)}.json"


def _plan_workloads() -> list[str]:
    return [*_EARLY_WORKLOADS, *_LATER_WORKLOADS, "soak"]


def _notify(event: str, message: str) -> None:
    try:
        from tests.benchmarks.bench.notify import _send_bench_notification

        _send_bench_notification(message, title=f"engine-eval {event}")
    except Exception:
        return


def _public_cell(cell: dict[str, Any]) -> dict[str, Any]:
    return {key: cell.get(key) for key in _CELL_KEYS}


def incumbent_pair(seat: str) -> list[dict[str, Any]]:
    """oMLX is the deciding incumbent. Ollama is the failover pair, different bytes."""
    cfg = h2h.load_config()
    mapping = (cfg.get("engine_eval") or {}).get("seats", {})[seat]
    workspace = mapping["workspace"]
    model = mapping["model"]
    hint = str(_bench_workspaces()[workspace]["model_hint"])
    ollama_tag = str(cfg["models"][model]["ollama"])
    shared = {
        "seat": seat,
        "workspace": workspace,
        "engine_kind": "external",
        "mode": "plain",
        "model": model,
        "argv": [],
        "cwd": None,
        "launch_error": None,
        "port": None,
    }
    return [
        {
            **shared,
            "engine": "omlx",
            "expected_model": hint,
            "backend": "eval-openai-omlx-incumbent",
            "base": cfg["engines"]["omlx"]["base"],
            "observe_port": 8085,
        },
        {
            **shared,
            "engine": "ollama",
            "expected_model": ollama_tag,
            "backend": "eval-openai-ollama-incumbent",
            "base": cfg["engines"]["ollama"]["base"],
            "observe_port": 11434,
        },
    ]


def _valid_canary_cells(root: Path, build: str) -> list[dict[str, Any]]:
    chosen = []
    for cell in candidate_cells():
        path = canary_receipt_path(root, build, cell)
        if not path.is_file():
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("valid") is True and receipt.get("build") == build:
            chosen.append(cell)
    return chosen


def _plan_entry(cell: dict[str, Any], role: str) -> dict[str, Any]:
    workloads = _plan_workloads()
    estimate_s = sum(_WORKLOAD_ESTIMATE_S[name] for name in workloads)
    return {
        "role": role,
        "cell": _public_cell(cell),
        "workloads": workloads,
        "estimate_s": estimate_s,
        "estimate_note": "upper bound in seconds, not a measurement; later stages run only after earlier ones pass",
    }


def build_stage3_plan(
    build: str,
    seats: list[str] | None = None,
    skip_incumbents: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """List current-build valid canary cells and their incumbent pairs. Does not run.

    ``seats`` bounds the plan to those seats; ``skip_incumbents`` drops an incumbent
    engine's pair rows so a bounded rehearsal need not load it.
    """
    head = current_build()
    if build != head:
        raise Stage3BlockedError(f"canary build {build} is not the current build {head}")
    root = data_root()
    candidates = _valid_canary_cells(root, build)
    if seats:
        known = {cell["seat"] for cell in candidates}
        unknown = [seat for seat in seats if seat not in known]
        if unknown:
            raise Stage3BlockedError(
                f"no current-build valid canary cell for seat(s) {unknown}; valid: {sorted(known)}"
            )
        candidates = [cell for cell in candidates if cell["seat"] in seats]
    chosen = list(dict.fromkeys(cell["seat"] for cell in candidates))
    skipped = set(skip_incumbents)
    entries = [_plan_entry(cell, "candidate") for cell in candidates]
    for seat in chosen:
        entries.extend(
            _plan_entry(cell, "incumbent")
            for cell in incumbent_pair(seat)
            if cell["engine"] not in skipped
        )
    plan = {
        "build": build,
        "seats": chosen,
        "skip_incumbents": sorted(skipped),
        "estimate_note": "upper bound in seconds, not a measurement",
        "estimate_s": sum(int(entry["estimate_s"]) for entry in entries),
        "cells": entries,
    }
    _write_json(_stage3_dir(root, build) / "plan.json", plan)
    return plan


def _print_plan(plan: dict[str, Any]) -> None:
    print(
        f"build {plan['build']} cells {len(plan['cells'])} "
        f"estimate_s {plan['estimate_s']} ({plan['estimate_s'] / 3600:.1f}h upper bound, "
        f"not a measurement)",
        flush=True,
    )
    for entry in plan["cells"]:
        cell = entry["cell"]
        names = ",".join(entry["workloads"])
        print(
            f"{entry['role']} {_cell_selector(cell)} | {names} | {entry['estimate_s']}s",
            flush=True,
        )


def quiet_host_refusal() -> str | None:
    """Dispatch workers, a listener on an eval port, or the swap gate."""
    lines, err = host_quiet._process_lines()
    if err:
        return err
    dispatch = [
        row for row in host_quiet._scan_processes(lines) if row.get("kind") == "dispatch lane job"
    ]
    if dispatch:
        pids = ",".join(str(row.get("pid")) for row in dispatch)
        return f"dispatch lane job: {pids}"
    busy = [f"{port}:{h2h.pid_on_port(port)}" for port in _EVAL_PORTS if h2h.pid_on_port(port)]
    if busy:
        return "eval port busy " + ",".join(busy)
    okay, reason = h2h.start_gate(h2h.load_config())
    if not okay:
        return f"swap start gate: {reason}"
    return None


def _eval_listeners() -> list[str]:
    return [f"{port}:{h2h.pid_on_port(port)}" for port in _EVAL_PORTS if h2h.pid_on_port(port)]


def _cell_finished(root: Path, build: str, cell: dict[str, Any]) -> dict[str, Any] | None:
    path = _cell_summary_path(root, build, cell)
    if not path.is_file():
        return None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if receipt.get("finished") is True and receipt.get("build") == build:
        return receipt
    return None


def _checkpoint_path(root: Path, build: str) -> Path:
    return _stage3_dir(root, build) / "checkpoint.json"


def _write_checkpoint(
    root: Path, build: str, plan_path: str, completed: list[str], stopped: str | None
) -> None:
    _write_json(
        _checkpoint_path(root, build),
        {"build": build, "plan": plan_path, "completed": completed, "stopped": stopped},
    )


def _workload_failed(row: dict[str, Any]) -> bool:
    return row.get("valid") is not True


def _first_failure(workloads: dict[str, dict[str, Any]]) -> str:
    for row in workloads.values():
        if _workload_failed(row):
            return _one_line(str(row.get("reason") or row.get("status") or "invalid"))
    return "ok"


def _run_one_staged_workload(
    cell: dict[str, Any], name: str, root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    started = time.monotonic()
    result = run_stage3(cell, name, build=build, pipeline=pipeline)
    elapsed = round(time.monotonic() - started, 1)
    reason = _one_line(str(result.get("reason") or result.get("status") or ""))
    state = "pass" if result.get("valid") is True else "fail"
    print(f"{_cell_selector(cell)} | {name} | {state} | {reason} | {elapsed:.0f}s", flush=True)
    result["elapsed_s"] = elapsed
    result["reason_norm"] = normalise_reason(reason, cell)
    if (
        str(result.get("reason") or "").startswith("swap start gate")
        or result.get("swap_gate") is False
    ):
        result["swap_stop"] = True
    return result


def _run_staged_cell(cell: dict[str, Any], root: Path, build: str, pipeline: str) -> dict[str, Any]:
    workloads: dict[str, dict[str, Any]] = {}
    for name in _EARLY_WORKLOADS:
        workloads[name] = _run_one_staged_workload(cell, name, root, build, pipeline)
        if workloads[name].get("swap_stop"):
            break
    early_ok = len(workloads) == len(_EARLY_WORKLOADS) and all(
        not _workload_failed(workloads[name]) for name in _EARLY_WORKLOADS
    )
    if early_ok:
        for name in _LATER_WORKLOADS:
            workloads[name] = _run_one_staged_workload(cell, name, root, build, pipeline)
            if workloads[name].get("swap_stop"):
                break
    earlier = (*_EARLY_WORKLOADS, *_LATER_WORKLOADS)
    all_earlier_ok = all(
        name in workloads and not _workload_failed(workloads[name]) for name in earlier
    )
    if all_earlier_ok:
        workloads["soak"] = _run_one_staged_workload(cell, "soak", root, build, pipeline)
    reason = _first_failure(workloads)
    receipt = {
        "build": build,
        "cell": _public_cell(cell),
        "cell_id": _cell_id(cell),
        "finished": True,
        "valid": reason == "ok",
        "reason": reason,
        "reason_norm": normalise_reason(reason, cell),
        "swap_stop": any(row.get("swap_stop") for row in workloads.values()),
        "workloads": workloads,
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = _cell_summary_path(root, build, cell)
    receipt["receipt"] = str(path)
    _write_json(path, receipt)
    return receipt


def _refused_cell(cell: dict[str, Any], build: str, reason: str, root: Path) -> dict[str, Any]:
    receipt = {
        "build": build,
        "cell": _public_cell(cell),
        "cell_id": _cell_id(cell),
        "finished": True,
        "valid": False,
        "reason": reason,
        "reason_norm": normalise_reason(reason, cell),
        "swap_stop": reason.startswith("swap start gate"),
        "workloads": {},
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = _cell_summary_path(root, build, cell)
    receipt["receipt"] = str(path)
    _write_json(path, receipt)
    print(f"{_cell_selector(cell)} | quiet | fail | {reason} | 0s", flush=True)
    return receipt


def _cells_should_stop(results: list[dict[str, Any]]) -> str | None:
    if any(row.get("swap_stop") for row in results):
        return next(str(row.get("reason")) for row in results if row.get("swap_stop"))
    if len(results) < 2 or results[-1].get("valid") is True:
        return None
    prev = results[-2]
    if prev.get("valid") is not True and prev.get("reason_norm") == results[-1].get("reason_norm"):
        return f"2 consecutive cells: {results[-1].get('reason_norm')}"
    return None


def _quality_not_worse(result: dict[str, Any]) -> bool | None:
    if result.get("not_comparable") is True:
        return None
    row = (result.get("workloads") or {}).get("quality-seat") or {}
    cand = row.get("candidate_outcome")
    inc = row.get("incumbent_outcome")
    if cand is None or inc is None:
        return None
    return cand == "PASS" or inc == "FAIL"


def _speed_beats_noise(result: dict[str, Any]) -> bool | None:
    speed = result.get("speed_tps")
    noise = result.get("noise") if isinstance(result.get("noise"), dict) else {}
    if speed is None or "run_a_tps" not in noise or "run_b_tps" not in noise:
        return None
    floor = max(float(noise["run_a_tps"]), float(noise["run_b_tps"]))
    return float(speed) > floor


def _flag_from_workload(result: dict[str, Any], name: str) -> bool | None:
    row = (result.get("workloads") or {}).get(name)
    if not isinstance(row, dict) or "valid" not in row:
        return None
    if row.get("status") == "NOT_APPLICABLE":
        return None
    return row.get("valid") is True


def _matrix_verdict(result: dict[str, Any]) -> str:
    checks = (
        _quality_not_worse(result),
        _speed_beats_noise(result),
        _flag_from_workload(result, "soak"),
        _flag_from_workload(result, "co-residence"),
    )
    if any(item is None for item in checks) or not all(checks):
        return "Unproven — keep the incumbent"
    return "pass"


def _summary_rows(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    incumbents = {
        row["cell"]["seat"]: row
        for row in results
        if (row.get("cell") or {}).get("engine") == "omlx"
    }
    table = []
    for result in results:
        cell = result.get("cell") or {}
        if cell.get("engine") in {"omlx", "ollama"}:
            continue
        incumbent = incumbents.get(cell.get("seat"))
        table.append(
            {
                "seat": str(cell.get("seat")),
                "candidate": _cell_selector(cell),
                "incumbent": _cell_selector(incumbent["cell"]) if incumbent else "pending",
                "quality": str(_quality_not_worse(result)),
                "speed": str(_speed_beats_noise(result)),
                "memory": str(_flag_from_workload(result, "soak")),
                "verdict": _matrix_verdict(result),
            }
        )
    return table


def _print_summary(rows: list[dict[str, str]]) -> None:
    print("seat | candidate | incumbent | quality | speed | memory | verdict", flush=True)
    for row in rows:
        print(
            " | ".join(
                row[key]
                for key in (
                    "seat",
                    "candidate",
                    "incumbent",
                    "quality",
                    "speed",
                    "memory",
                    "verdict",
                )
            ),
            flush=True,
        )


def _load_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    head = current_build()
    if plan.get("build") != head:
        raise Stage3BlockedError(f"plan build {plan.get('build')} is not the current build {head}")
    return plan


def execute_stage3_plan(plan_path: str, pipeline: str) -> int:
    """Run a printed plan. Skip finished cells. Stop on a repeated reason or the swap gate."""
    path = Path(plan_path)
    plan = _load_plan(path)
    build = str(plan["build"])
    root = data_root()
    _configure_results(root)
    results: list[dict[str, Any]] = []
    completed: list[str] = []
    stop_reason = None
    _notify("start", f"stage3 {build} cells={len(plan.get('cells') or [])}")
    try:
        for entry in plan.get("cells") or []:
            cell = entry["cell"]
            prior = _cell_finished(root, build, cell)
            if prior is not None:
                print(f"{_cell_selector(cell)} | skip | completed | 0s", flush=True)
                results.append(prior)
                completed.append(_cell_id(cell))
                continue
            refusal = quiet_host_refusal()
            if refusal:
                receipt = _refused_cell(cell, build, refusal, root)
                results.append(receipt)
                completed.append(_cell_id(cell))
                if receipt.get("swap_stop"):
                    stop_reason = refusal
                    break
            else:
                receipt = _run_staged_cell(cell, root, build, pipeline)
                results.append(receipt)
                completed.append(_cell_id(cell))
                if receipt.get("swap_stop"):
                    stop_reason = str(receipt.get("reason"))
                    break
            stop_reason = _cells_should_stop(results)
            if stop_reason:
                break
    finally:
        _write_checkpoint(root, build, str(path), completed, stop_reason)
    listeners = _eval_listeners()
    rows = _summary_rows(results)
    _print_summary(rows)
    print(
        f"cells {len(results)} stopped={stop_reason or 'no'} listeners={listeners or 'none'}",
        flush=True,
    )
    if stop_reason:
        _notify("stop-on-failure", f"stage3 {build} stopped: {stop_reason}")
    else:
        _notify("finish", f"stage3 {build} cells={len(results)}")
    if listeners or stop_reason or any(row.get("valid") is not True for row in results):
        return 2
    return 0


def _select_cell(args: argparse.Namespace) -> dict[str, Any]:
    cell = next(
        (
            item
            for item in candidate_cells()
            if item["engine"] == args.engine
            and item["mode"] == args.mode
            and item["seat"] == args.seat
        ),
        None,
    )
    if cell is None:
        raise Stage3BlockedError(
            f"no approved candidate cell: {args.engine}/{args.mode}/{args.seat}"
        )
    return cell


def main(argv: list[str] | None = None) -> int:
    """Dispatch candidate cell, canary, or fail-closed Stage 3 work."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    canary = sub.add_parser("canary")
    canary.add_argument("--pipeline", default="http://127.0.0.1:9099")
    canary.add_argument("--cell", default=None, help="engine:mode:seat — run one cell")
    cell = sub.add_parser("cell")
    cell.add_argument("--engine", required=True)
    cell.add_argument("--mode", choices=("plain", "spec"), required=True)
    cell.add_argument("--seat", required=True)
    cell.add_argument("--pipeline", default="http://127.0.0.1:9099")
    stage3 = sub.add_parser("stage3")
    stage3.add_argument("--engine", required=True)
    stage3.add_argument("--mode", choices=("plain", "spec"), required=True)
    stage3.add_argument("--seat", required=True)
    stage3.add_argument("--workload", required=True)
    stage3.add_argument("--pipeline", default="http://127.0.0.1:9099")
    plan = sub.add_parser("stage3-plan")
    plan.add_argument("--from-canary", required=True, dest="from_canary")
    plan.add_argument(
        "--seats",
        default=None,
        help="comma-separated seats to plan; every valid canary seat when omitted",
    )
    plan.add_argument(
        "--skip-incumbent",
        action="append",
        default=[],
        dest="skip_incumbents",
        choices=("omlx", "ollama"),
        help="leave this incumbent engine's pair rows out (repeatable)",
    )
    stage3_run = sub.add_parser("stage3-run")
    stage3_run.add_argument("--plan", required=True)
    stage3_run.add_argument("--pipeline", default="http://127.0.0.1:9099")
    args = parser.parse_args(argv)
    try:
        if args.command == "canary":
            _results, code = run_canary(args.pipeline, only=args.cell)
            return code
        if args.command == "stage3-plan":
            seats = [s.strip() for s in (args.seats or "").split(",") if s.strip()] or None
            built = build_stage3_plan(
                args.from_canary, seats=seats, skip_incumbents=args.skip_incumbents
            )
            _print_plan(built)
            return 0
        if args.command == "stage3-run":
            return execute_stage3_plan(args.plan, args.pipeline)
        selected = _select_cell(args)
        if args.command == "cell":
            result = run_cell(selected, args.pipeline)
        else:
            result = run_stage3(selected, args.workload, pipeline=args.pipeline)
        print(json.dumps(result, indent=2))
        return 0 if result.get("valid") else 2
    except (OSError, subprocess.CalledProcessError, ValueError, Stage3BlockedError) as exc:
        print(json.dumps({"valid": False, "status": "BLOCKED", "reason": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
