#!/usr/bin/env python3
"""Fail a measured cell unless independent evidence matches what it claims.

Each claim names an engine-reported source. A claim with no source is excluded
or invalidates the cell, with a reason. Launchd stdout
(``/opt/homebrew/var/log/omlx.log`` and ``ollama.log``) is not a source.
oMLX per-request lines are ``~/.omlx/logs/server.log``.

    uv run python tests/benchmarks/engine_eval_instrument.py self-test
    uv run python tests/benchmarks/engine_eval_instrument.py judge --evidence cell.json
    uv run python tests/benchmarks/engine_eval_instrument.py stage0 --engine ollama --seat daily-moe
    uv run python tests/benchmarks/engine_eval_instrument.py stage0 --engine omlx --seat hunt-reasoning

``stage0`` reads the running services. It does not start, stop, or unload them.
The orchestrator unloads the seat model first (Ollama ``keep_alive`` 0 on the
daily GGUF tag; oMLX ``POST /v1/models/gemma-4-26b-a4b-it-QAT-4bit/unload``).
``stage0`` then captures ``vm_stat`` itself before the first request. The first
response's ``x-portal-route`` must name the seat model or the command stops
before the second sample, preflight, and the memory comparison.

Ollama 0.40 has no ``/api/tokenize``. Token counts use the same-base
checkpoint's ``tokenizer.json``. ``completion_tokens`` is compared to the
tokenizer count of ``content`` plus ``reasoning`` and ``reasoning_content``,
with a tolerance for template and stop tokens.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import plistlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MEMORY_ABS_TOLERANCE_GB = 2.0
MEMORY_REL_TOLERANCE = 0.15
_ENGINE_BASES = {"ollama": "http://127.0.0.1:11434", "omlx": "http://127.0.0.1:8085"}
# Engine usage counts template and stop tokens the text tokenizer does not see.
TOKEN_ABS_TOLERANCE = 16

REQUIRED_CLAIMS = (
    "spec_method",
    "drafter_loaded",
    "context_tokens",
    "parallel_slots",
    "kv_dtype",
    "thinking",
    "temperature",
)
_SPEC_OFF = frozenset({"off", "plain", "none"})

_SETTINGS_RE = re.compile(r"Applied initial settings for ([^:]+): (\{.*\})\s*$")
_CHAT_MODEL_RE = re.compile(r"Chat completion: model=([^,\s]+)")
_ACCEPT_RE = re.compile(r"accept=\d+/\d+ \(([0-9.]+)%\)")
_N_CTX_RE = re.compile(r"n_ctx\s*=\s*(\d+)")
_N_SEQ_RE = re.compile(r"n_seq_max\s*=\s*(\d+)")
_OLLAMA_MODEL_RE = re.compile(r"\bmodel=([^\s]+)")
_ROUTE_RE = re.compile(r"^([^;]+);([^;]*);(.*)$")
_PIPE_SUCCEEDED_RE = re.compile(r"Backend (\S+) succeeded for workspace=(\S+) model=(\S+)")
_PIPE_STREAM_RE = re.compile(r"Stream routing: workspace=(\S+) backend=(\S+) model=(\S+)")
_PIPE_ROUTE_RE = re.compile(r"Routing workspace=(\S+) → backend=(\S+) model=(\S+)")
_PARAM_RE = re.compile(r"^([A-Za-z0-9_]+)\s+(\S+)")
_MTP_PATH_RE = re.compile(r"MTP path activated")
_ACCEPT_NA_RE = re.compile(r"accept=\d+/\d+ \((?:n/a|N/A)\)")
_LAUNCHD_LOGS = frozenset({"/opt/homebrew/var/log/omlx.log", "/opt/homebrew/var/log/ollama.log"})
_OLLAMA_PLIST = Path("/Library/LaunchDaemons/com.portal5.ollama.plist")
DAILY_SEAT = "daily-moe"
HUNT_SEAT = "hunt-reasoning"
_DAILY_OLLAMA = "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"
_DAILY_TOKENIZER = (
    Path("/Volumes/data01/omlx-models") / "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp"
)
_HUNT_OMLX = "gemma-4-26b-a4b-it-QAT-4bit"
_TOOL_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]
_VM_PAGE_RE = re.compile(r"page size of (\d+) bytes")
_VM_PAGES_RE = re.compile(r"^Pages (.+?):\s+([\d.]+)\.?\s*$", re.M)
_FOOT_ROW_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*([KMG]?B)\s+(\d+(?:\.\d+)?)\s*([KMG]?B)\s+"
    r"(\d+(?:\.\d+)?)\s*([KMG]?B)\s+\d+\s+(.+?)\s*$"
)
_PHYS_RE = re.compile(r"phys_footprint:\s*([\d.]+)\s*([KMG]?B)", re.I)
_GB = {"B": 1 / (1024**3), "KB": 1 / (1024**2), "MB": 1 / 1024, "GB": 1.0}


def _agree(left: float, right: float) -> bool:
    scale = max(abs(left), abs(right), 0.001)
    return abs(left - right) <= max(MEMORY_ABS_TOLERANCE_GB, MEMORY_REL_TOLERANCE * scale)


def _fail(failures: list[str], message: str) -> None:
    failures.append(message)


def parse_omlx_settings(log_text: str) -> dict[str, dict[str, Any]]:
    """Model id → dict from ``Applied initial settings`` lines. Last line wins."""
    found: dict[str, dict[str, Any]] = {}
    for line in log_text.splitlines():
        match = _SETTINGS_RE.search(line.strip())
        if not match:
            continue
        try:
            payload = ast.literal_eval(match.group(2))
        except (SyntaxError, ValueError):
            continue
        if isinstance(payload, dict):
            found[match.group(1).strip()] = payload
    return found


def parse_omlx_acceptance(log_text: str) -> float | None:
    """Last MTP acceptance percent in the text, if a request logged one."""
    found = _ACCEPT_RE.findall(log_text)
    return float(found[-1]) if found else None


def omlx_chat_models(log_text: str) -> list[str]:
    """Model ids on oMLX ``Chat completion`` lines, in order."""
    return _CHAT_MODEL_RE.findall(log_text)


def parse_ollama_load(log_text: str) -> dict[str, dict[str, Any]]:
    """Bind the latest ``n_ctx`` / ``n_seq_max`` to the next ``model=`` line."""
    pending: dict[str, Any] = {}
    found: dict[str, dict[str, Any]] = {}
    for line in log_text.splitlines():
        ctx = _N_CTX_RE.search(line)
        if (
            ctx
            and "n_ctx_train" not in line
            and "n_ctx_seq" not in line
            and "n_ctx_orig" not in line
        ):
            pending["context_tokens"] = int(ctx.group(1))
        slots = _N_SEQ_RE.search(line)
        if slots:
            pending["parallel_slots"] = int(slots.group(1))
        model = _OLLAMA_MODEL_RE.search(line)
        if model and pending:
            found[model.group(1)] = dict(pending)
            pending = {}
    return found


def reject_engine_log(path: str | Path) -> str | None:
    """Launchd stdout is not per-request evidence. ``server.log`` is."""
    text = str(path)
    if text in _LAUNCHD_LOGS:
        return f"{text} is launchd stdout, not per-request evidence"
    return None


def omlx_server_log() -> Path:
    return Path.home() / ".omlx" / "logs" / "server.log"


def seat_plan(seat: str, engine: str) -> dict[str, Any]:
    """Production baseline the workspace routing actually serves on this engine."""
    if engine == "ollama" and seat == DAILY_SEAT:
        return _daily_ollama_plan()
    if engine == "omlx" and seat == HUNT_SEAT:
        return _hunt_omlx_plan()
    raise KeyError(seat)


def _daily_ollama_plan() -> dict[str, Any]:
    """``auto-daily`` hints the Nemotron GGUF. ``general`` has no oMLX alias for it."""
    return {
        "seat": DAILY_SEAT,
        "engine": "ollama",
        "workspace": "auto-daily",
        "same_checkpoint": False,
        "pipeline_context_limit": 16384,
        "model": _DAILY_OLLAMA,
        "backend": "ollama-general",
        "base": "http://127.0.0.1:11434",
        "mode": "plain",
        "checkpoint": _DAILY_TOKENIZER,
        "claims": {
            "spec_method": "off",
            "drafter_loaded": False,
            "context_tokens": 32768,
            "parallel_slots": 1,
            "kv_dtype": "q8_0",
            "thinking": True,
            "temperature": 1.0,
        },
    }


def _hunt_omlx_plan() -> dict[str, Any]:
    """``hunt-reasoning`` aliases onto ``omlx-general``'s Gemma QAT id."""
    return {
        "seat": HUNT_SEAT,
        "engine": "omlx",
        "workspace": HUNT_SEAT,
        "same_checkpoint": False,
        "pipeline_context_limit": 8192,
        "model": _HUNT_OMLX,
        "backend": "omlx-general",
        "base": "http://127.0.0.1:8085",
        "mode": "plain",
        "checkpoint": Path("/Volumes/data01/omlx-models") / _HUNT_OMLX,
        "claims": {
            "spec_method": "off",
            "drafter_loaded": False,
            "context_tokens": 262144,
            "parallel_slots": 8,
            "kv_dtype": "unreported",
            "thinking": False,
            "temperature": 0.0,
        },
    }


def parse_ollama_ps(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``/api/ps`` rows keyed by model name."""
    found: dict[str, dict[str, Any]] = {}
    for item in payload.get("models") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not name:
            continue
        found[str(name)] = {
            "context_length": item.get("context_length"),
            "size": item.get("size"),
            "size_vram": item.get("size_vram"),
            "expires_at": item.get("expires_at"),
        }
    return found


def ps_refreshed(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[str]:
    """Models whose ``expires_at`` appeared or changed between two ``/api/ps`` reads."""
    names: list[str] = []
    for name, row in after.items():
        prev = before.get(name)
        if prev is None or prev.get("expires_at") != row.get("expires_at"):
            names.append(name)
    return names


def parse_ollama_show(payload: dict[str, Any]) -> dict[str, Any]:
    """Parameters and template from ``/api/show``. Thinking only when a parameter says so."""
    params: dict[str, Any] = {"template": payload.get("template") or ""}
    for line in str(payload.get("parameters") or "").splitlines():
        match = _PARAM_RE.match(line.strip())
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        if key == "num_ctx":
            params["num_ctx"] = int(raw)
        elif key == "temperature":
            params["temperature"] = float(raw)
        elif key in {"think", "enable_thinking"}:
            params["thinking"] = raw.lower() not in {"0", "false", "none"}
    return params


def parse_ollama_plist(data: dict[str, Any]) -> dict[str, Any]:
    """NUM_PARALLEL, KV cache type, and flash attention from the launchd plist."""
    env = data.get("EnvironmentVariables") or {}
    out: dict[str, Any] = {}
    if "OLLAMA_NUM_PARALLEL" in env:
        out["parallel_slots"] = int(env["OLLAMA_NUM_PARALLEL"])
    if "OLLAMA_KV_CACHE_TYPE" in env:
        out["kv_dtype"] = str(env["OLLAMA_KV_CACHE_TYPE"])
    if "OLLAMA_FLASH_ATTENTION" in env:
        out["flash_attention"] = str(env["OLLAMA_FLASH_ATTENTION"]) not in {"0", "false", "False"}
    return out


def parse_omlx_api_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_requests": payload.get("total_requests"),
        "loaded_models": list(payload.get("loaded_models") or []),
        "model_memory_used": payload.get("model_memory_used"),
    }


def parse_omlx_model_row(payload: dict[str, Any], model: str) -> dict[str, Any]:
    """One model from ``/v1/models/status``: loaded, declared context, weight bytes."""
    for row in payload.get("models") or []:
        if isinstance(row, dict) and row.get("id") == model:
            return {
                "loaded": row.get("loaded"),
                "context_tokens": row.get("model_context_length"),
                "engine_type": row.get("engine_type"),
                "thinking_default": row.get("thinking_default"),
                "actual_size": row.get("actual_size"),
                "estimated_size": row.get("estimated_size"),
            }
    return {}


def parse_pipeline_routes(log_text: str) -> list[tuple[str, str, str]]:
    """Per-request lines that name backend and model.

    Non-stream success is ``Backend … succeeded``. Streaming selection is
    ``Stream routing`` or ``Routing workspace=… → backend=… model=…``.
    ``Non-stream routing`` is only logged when ``enforce_hint`` is set, so an
    auto seat never emits it. Succeeded lines win when both shapes are present.
    """
    succeeded = [
        (workspace, backend, model)
        for backend, workspace, model in _PIPE_SUCCEEDED_RE.findall(log_text)
    ]
    if succeeded:
        return succeeded
    streamed = _PIPE_STREAM_RE.findall(log_text)
    if streamed:
        return streamed
    return _PIPE_ROUTE_RE.findall(log_text)


def acceptance_from_log(log_text: str) -> tuple[str, float | None]:
    """``rate`` with a percent, ``na`` when the engine logged n/a, else ``missing``."""
    percent = _ACCEPT_RE.findall(log_text)
    if percent:
        return "rate", float(percent[-1])
    if _ACCEPT_NA_RE.search(log_text):
        return "na", None
    return "missing", None


def resolve_tokenizer(
    engine: str,
    checkpoint: str | Path | None,
    matrix_tokenizer: str | Path | None,
) -> Path | None:
    """``tokenizer.json`` for the checkpoint, else the HF file the matrix records.

    ``checkpoint`` may be a directory, a ``tokenizer.json`` path, or a string.
    Ollama 0.40 does not serve ``/api/tokenize``; the GGUF seat uses the
    same-base checkpoint's ``tokenizer.json``.
    """
    del engine
    found = _tokenizer_file(checkpoint)
    if found is not None:
        return found
    return _tokenizer_file(matrix_tokenizer)


def _tokenizer_file(checkpoint: str | Path | None) -> Path | None:
    if checkpoint is None:
        return None
    path = Path(checkpoint)
    if path.is_file() and path.name == "tokenizer.json":
        return path
    if path.is_dir():
        candidate = path / "tokenizer.json"
        if candidate.is_file():
            return candidate
    if path.suffix == ".gguf":
        sibling = path.parent / "tokenizer.json"
        if sibling.is_file():
            return sibling
    return None


def _exclude(reason: str) -> dict[str, str]:
    return {"decision": "exclude", "reason": reason}


def _invalidate(reason: str) -> dict[str, str]:
    return {"decision": "invalidate", "reason": reason}


def parse_vm_stat(text: str) -> dict[str, int]:
    """Page counts from ``vm_stat`` plus ``page_bytes``."""
    page = _VM_PAGE_RE.search(text)
    pages = {
        match.group(1).strip().lower(): float(match.group(2))
        for match in _VM_PAGES_RE.finditer(text)
    }
    out: dict[str, int] = {}
    if page:
        out["page_bytes"] = int(page.group(1))
    for name, key in (("free", "free_pages"), ("wired down", "wired_pages")):
        if name in pages:
            out[key] = int(pages[name])
    return out


def vm_deltas_gb(before: dict[str, int], after: dict[str, int]) -> dict[str, float] | None:
    """Wired growth and free drop, in GB. None when either snapshot is incomplete."""
    page = before.get("page_bytes") or after.get("page_bytes")
    needed = ("wired_pages", "free_pages")
    if not page or any(key not in before or key not in after for key in needed):
        return None
    scale = page / (1024**3)
    return {
        "vm_wired_delta_gb": (after["wired_pages"] - before["wired_pages"]) * scale,
        "vm_free_delta_gb": (before["free_pages"] - after["free_pages"]) * scale,
    }


def parse_ps_tree(text: str) -> list[tuple[int, int, int]]:
    """Rows of ``pid ppid rss_kb`` from ``ps -axo pid=,ppid=,rss=``."""
    rows: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
        except ValueError:
            continue
    return rows


def tree_rss_gb(rows: list[tuple[int, int, int]], root_pid: int) -> float | None:
    """RSS of ``root_pid`` plus every descendant, in GB. None if the root is absent."""
    by_parent: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for pid, ppid, kb in rows:
        rss[pid] = kb
        by_parent.setdefault(ppid, []).append(pid)
    if root_pid not in rss:
        return None
    seen = {root_pid}
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        for child in by_parent.get(pid, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return sum(rss[pid] for pid in seen) / (1024**2)


def parse_footprint(footprint_text: str) -> dict[str, float | None]:
    """Read a ``footprint -p`` report. Sizes are columns; the category is last.

    IOAccelerator on this host is hundreds of KB. The GGUF shows up as clean
    mapped-file pages. Neither number is the Metal weight allocation.
    """
    ioaccelerator = 0.0
    clean_mapped = 0.0
    saw_io = False
    saw_mapped = False
    for line in footprint_text.splitlines():
        match = _FOOT_ROW_RE.match(line)
        if not match:
            continue
        dirty = float(match.group(1)) * _GB[match.group(2).upper()]
        clean = float(match.group(3)) * _GB[match.group(4).upper()]
        category = match.group(7).strip()
        if category == "IOAccelerator":
            ioaccelerator += dirty + clean
            saw_io = True
        elif category == "mapped file":
            clean_mapped += clean
            saw_mapped = True
    phys = _PHYS_RE.search(footprint_text)
    phys_gb = float(phys.group(1)) * _GB[phys.group(2).upper()] if phys else None
    return {
        "ioaccelerator_gb": ioaccelerator if saw_io else None,
        "clean_mapped_gb": clean_mapped if saw_mapped else None,
        "phys_footprint_gb": phys_gb,
    }


def served_id_is_filesystem_path(model_id: str) -> bool:
    """True when the id is a path (vLLM Metal served the checkpoint path → 404)."""
    return model_id.startswith("/") or model_id.startswith("~") or "/omlx-models/" in model_id


def count_tokens(text: str, tokenizer_json: Path) -> int | None:
    """Token count of ``text`` with the checkpoint tokenizer. None if it cannot load."""
    try:
        from tokenizers import Tokenizer
    except ImportError:
        return None
    if not tokenizer_json.is_file():
        return None
    tokenizer = Tokenizer.from_file(str(tokenizer_json))
    return len(tokenizer.encode(text).ids)


def _exclusion(evidence: dict[str, Any], key: str) -> dict[str, Any] | None:
    excluded = evidence.get("excluded_claims")
    if not isinstance(excluded, dict):
        return None
    rule = excluded.get(key)
    return rule if isinstance(rule, dict) else None


def _check_one_claim(
    key: str,
    evidence: dict[str, Any],
    claimed: dict[str, Any],
    readback: dict[str, Any],
    failures: list[str],
) -> None:
    sources = evidence.get("sources") if isinstance(evidence.get("sources"), dict) else {}
    rule = _exclusion(evidence, key)
    if key in readback:
        if key not in sources:
            _fail(failures, f"settings: {key} source unnamed")
        elif claimed.get(key) != readback[key]:
            _fail(failures, f"settings: {key} claimed {claimed[key]!r} read back {readback[key]!r}")
        return
    if rule and rule.get("reason") and rule.get("decision") == "exclude":
        return
    if rule and rule.get("reason") and rule.get("decision") == "invalidate":
        _fail(failures, f"settings: {key} invalidates the cell: {rule['reason']}")
        return
    if rule and not rule.get("reason"):
        _fail(failures, f"settings: {key} exclusion has no reason")
        return
    if key not in claimed:
        _fail(failures, f"settings: {key} not claimed")
        return
    _fail(failures, f"settings: {key} unverifiable")


def _check_settings(evidence: dict[str, Any], failures: list[str]) -> None:
    claimed = evidence.get("claimed")
    readback = evidence.get("readback")
    if not isinstance(claimed, dict) or not isinstance(readback, dict):
        _fail(failures, "settings: claimed or readback missing")
        return
    for key in REQUIRED_CLAIMS:
        _check_one_claim(key, evidence, claimed, readback, failures)
    for item in evidence.get("source_conflicts") or []:
        _fail(failures, f"settings: {item}")
    spec_rule = _exclusion(evidence, "spec_method")
    spec_off = claimed.get("spec_method") in _SPEC_OFF or (
        spec_rule and spec_rule.get("decision") == "exclude" and "spec_method" not in readback
    )
    if spec_off:
        return
    if "acceptance" not in readback:
        _fail(failures, "settings: acceptance unverifiable")
    elif "acceptance" in claimed and claimed["acceptance"] != readback["acceptance"]:
        _fail(failures, "settings: acceptance does not match the engine log")


def _check_route(evidence: dict[str, Any], failures: list[str]) -> None:
    expected = evidence.get("expected_model")
    workspace = evidence.get("expected_workspace")
    backend = evidence.get("expected_backend")
    routes = evidence.get("routes")
    if not expected or not isinstance(routes, list) or not routes:
        _fail(failures, "route: no per-request pipeline route")
        return
    engine_models = evidence.get("engine_models")
    if not isinstance(engine_models, list):
        _fail(failures, "route: engine log models missing")
        return
    foreign = sorted({model for model in engine_models if model != expected})
    if foreign:
        _fail(failures, f"route: foreign model in the engine log: {foreign}")
    if len(engine_models) != len(routes):
        _fail(failures, "route: engine request count does not match the pipeline")
    for index, route in enumerate(routes):
        header = str(route.get("header", ""))
        match = _ROUTE_RE.match(header)
        if not match:
            _fail(failures, f"route: request {index} has no x-portal-route")
            continue
        got_ws, got_backend, got_model = match.group(1), match.group(2), match.group(3)
        if got_ws != workspace or got_backend != backend or got_model != expected:
            _fail(failures, f"route: request {index} header {header!r}")
        if route.get("engine_model") != expected:
            _fail(failures, f"route: request {index} engine log model is not {expected}")
    _check_route_corroboration(evidence, routes, expected, failures)


def _check_route_corroboration(
    evidence: dict[str, Any], routes: list[Any], expected: str, failures: list[str]
) -> None:
    pipe = evidence.get("pipeline_models")
    if isinstance(pipe, list):
        foreign_pipe = sorted({model for model in pipe if model != expected})
        if foreign_pipe:
            _fail(failures, f"route: foreign model in the pipeline log: {foreign_pipe}")
        if len(pipe) != len(routes):
            _fail(failures, "route: pipeline log count does not match the requests")
    counter = evidence.get("request_counter")
    if not isinstance(counter, dict):
        return
    before, after = counter.get("before"), counter.get("after")
    if not isinstance(before, int) or not isinstance(after, int) or after - before < len(routes):
        _fail(failures, "route: total_requests did not advance")


def _check_memory(evidence: dict[str, Any], failures: list[str]) -> None:
    _check_residency(evidence, failures)
    memory = evidence.get("memory")
    if not isinstance(memory, dict) or not memory.get("tree_walked"):
        _fail(failures, "memory: process tree was not walked")
        return
    weight = memory.get("engine_weight_gb")
    rss = memory.get("tree_rss_gb")
    wired = memory.get("vm_wired_delta_gb")
    if weight is None:
        _fail(failures, "memory: engine weight unread")
        return
    if rss is None or wired is None:
        _fail(failures, "memory: tree RSS or vm_stat wired delta missing")
        return
    if not _agree(float(weight), float(wired)):
        resident_decimal = memory.get("engine_resident_decimal_gb")
        resident_detail = (
            f" ({float(resident_decimal):.2f}GB decimal)" if resident_decimal is not None else ""
        )
        tolerance = max(MEMORY_ABS_TOLERANCE_GB, MEMORY_REL_TOLERANCE * abs(float(weight)))
        _fail(
            failures,
            f"memory: engine resident {float(weight):.2f}GiB{resident_detail} vs wired delta "
            f"{float(wired):.2f}GiB (tolerance max(2GiB, 15%)={tolerance:.2f}GiB)",
        )


def _check_residency(evidence: dict[str, Any], failures: list[str]) -> None:
    residency = evidence.get("residency")
    if not isinstance(residency, dict):
        _fail(failures, "memory: engine residency snapshots missing")
        return
    before, after = residency.get("before"), residency.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        _fail(failures, "memory: engine residency snapshots missing")
        return
    cell_engine = evidence.get("engine")
    cell_model = evidence.get("expected_model")
    engines = sorted(set(before) | set(after))
    if not engines:
        _fail(failures, "memory: no engines in residency snapshots")
    for engine in engines:
        old, new = before.get(engine), after.get(engine)
        if not isinstance(old, dict) or not isinstance(new, dict):
            _fail(failures, f"memory: {engine} resident snapshot unreadable")
            continue
        changes = []
        for model in sorted(set(old) | set(new)):
            if engine == cell_engine and model == cell_model:
                continue
            if old.get(model) == new.get(model):
                continue
            if model not in old:
                changes.append(f"{model} loaded ({new[model]} bytes)")
            elif model not in new:
                changes.append(f"{model} unloaded (was {old[model]} bytes)")
            else:
                changes.append(f"{model} size changed ({old[model]} to {new[model]} bytes)")
        if changes:
            _fail(
                failures,
                f"memory: contaminated: {engine} resident set changed: {', '.join(changes)}",
            )


def _check_tokens(evidence: dict[str, Any], failures: list[str]) -> None:
    tokens = evidence.get("tokens")
    if not isinstance(tokens, dict):
        _fail(failures, "tokens: engine usage or tokenizer count missing")
        return
    engine = tokens.get("engine_completion")
    local = tokens.get("tokenizer_completion")
    if engine is None or local is None:
        _fail(failures, "tokens: engine usage or tokenizer count missing")
        return
    if abs(int(engine) - int(local)) > TOKEN_ABS_TOLERANCE:
        _fail(
            failures,
            f"tokens: engine {engine} vs tokenizer {local} "
            f"(tolerance {TOKEN_ABS_TOLERANCE} covers template and stop tokens)",
        )


def _check_noise(evidence: dict[str, Any], failures: list[str]) -> None:
    noise = evidence.get("noise")
    if not isinstance(noise, dict) or "run_a_tps" not in noise or "run_b_tps" not in noise:
        _fail(failures, "noise: back-to-back pair missing")
        return
    spread = abs(float(noise["run_a_tps"]) - float(noise["run_b_tps"]))
    if "later_delta_tps" not in noise:
        return
    later = abs(float(noise["later_delta_tps"]))
    if later <= spread and not noise.get("labeled_no_difference"):
        _fail(
            failures,
            f"noise: delta {later} is inside the spread {spread} and was not labeled no difference",
        )


def _check_template(evidence: dict[str, Any], failures: list[str]) -> None:
    template = evidence.get("template")
    if not isinstance(template, dict) or "same_checkpoint" not in template:
        _fail(failures, "template: parity not recorded")
        return
    if template.get("same_checkpoint") is False:
        return
    parity = template.get("parity")
    if isinstance(parity, dict) and parity.get("status") == "not_run" and parity.get("reason"):
        return
    comparisons = parity.get("comparisons") if isinstance(parity, dict) else None
    if not isinstance(comparisons, dict) or not comparisons:
        _fail(
            failures, "template: paired greedy parity is pending; incumbent parity was not measured"
        )
        return
    failed = [
        f"{peer}: {comparison.get('classification', 'unclassified')}"
        for peer, comparison in comparisons.items()
        if not isinstance(comparison, dict) or comparison.get("valid") is not True
    ]
    if not failed:
        return
    # A rendered-prompt difference is the cell's own recorded FINDING: the other
    # checks still decide validity and the quality comparison is non-comparable.
    # Any other mismatch stays a validity failure.
    waived = all(
        isinstance(comparison, dict)
        and comparison.get("classification") == "chat_template_rendering_mismatch"
        for comparison in comparisons.values()
    )
    if waived and template.get("quality_comparable") is False and template.get("template_differs"):
        return
    _fail(failures, f"template: paired greedy parity failed ({'; '.join(failed)})")


def _check_regressions(evidence: dict[str, Any], failures: list[str]) -> None:
    engine = evidence.get("engine")
    mode = evidence.get("mode")
    readback = evidence.get("readback") if isinstance(evidence.get("readback"), dict) else {}
    argv = evidence.get("launch_argv") or []
    if (
        engine == "omlx"
        and mode == "plain"
        and (
            readback.get("mtp_enabled") is not False or readback.get("dflash_enabled") is not False
        )
    ):
        _fail(failures, "regression: oMLX plain is not MTP-off and drafter-off in the engine log")
    if (
        engine == "splash"
        and mode == "plain"
        and ("--draft-model" in argv or readback.get("drafter_loaded") is not False)
    ):
        _fail(failures, "regression: Splash plain still carries a drafter")
    served = evidence.get("served_model_id")
    if not isinstance(served, str) or served_id_is_filesystem_path(served):
        _fail(failures, "regression: served model id is missing or is a filesystem path")
    if evidence.get("preflight_verdict") != "OK":
        _fail(failures, "regression: preflight is not OK")
    samples = evidence.get("swap_samples_mb")
    max_growth = evidence.get("max_swap_growth_mb")
    max_used = evidence.get("max_start_swap_used_mb")
    if not isinstance(samples, list) or not samples or max_growth is None or max_used is None:
        _fail(failures, "regression: swap samples missing")
        return
    growth = max(samples) - samples[0]
    if growth > max_growth:
        _fail(failures, f"regression: swap grew {growth}MB")
    if any(sample > max_used for sample in samples):
        _fail(failures, "regression: swap used during the cell passed the start ceiling")


def judge_cell(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``{valid, failures}``. Any failed check invalidates the cell."""
    if not evidence:
        return {"valid": False, "failures": ["instrument: no independent evidence"]}
    failures: list[str] = []
    _check_settings(evidence, failures)
    _check_route(evidence, failures)
    _check_memory(evidence, failures)
    _check_tokens(evidence, failures)
    _check_noise(evidence, failures)
    _check_template(evidence, failures)
    _check_regressions(evidence, failures)
    return {"valid": not failures, "failures": failures}


def golden_evidence() -> dict[str, Any]:
    """One cell whose evidence satisfies every check. The self-test's pass case."""
    claimed = {
        "spec_method": "off",
        "drafter_loaded": False,
        "context_tokens": 32768,
        "parallel_slots": 1,
        "kv_dtype": "fp16",
        "thinking": False,
        "temperature": 0.0,
    }
    model = "hf.co/example/Model:Q4_K_M-ctx32k"
    return {
        "engine": "ollama",
        "mode": "plain",
        "claimed": claimed,
        "readback": dict(claimed),
        "sources": dict.fromkeys(REQUIRED_CLAIMS, "fixture"),
        "expected_model": model,
        "expected_workspace": "auto-daily",
        "expected_backend": "ollama-general",
        "routes": [{"header": f"auto-daily;ollama-general;{model}", "engine_model": model}],
        "engine_models": [model],
        "memory": {
            "tree_walked": True,
            "tree_rss_gb": 2.0,
            "engine_weight_gb": 14.0,
            "engine_weight_source": "fixture",
            "vm_wired_delta_gb": 16.0,
            "vm_free_delta_gb": 16.2,
        },
        "residency": {
            "before": {"ollama": {}, "omlx": {}},
            "after": {"ollama": {}, "omlx": {}},
        },
        "tokens": {"engine_completion": 32, "tokenizer_completion": 33},
        "noise": {"run_a_tps": 50.0, "run_b_tps": 51.5},
        "template": {"same_checkpoint": False},
        "preflight_verdict": "OK",
        "swap_samples_mb": [100.0, 300.0],
        "max_swap_growth_mb": 2048,
        "max_start_swap_used_mb": 4096,
        "served_model_id": model,
        "launch_argv": ["ollama", "serve"],
    }


def defect_cases() -> list[tuple[str, dict[str, Any], str]]:
    """Each case must fail, and the failure list must contain ``needle``."""
    cases: list[tuple[str, dict[str, Any], str]] = []

    def add(name: str, mutate, needle: str) -> None:
        evidence = json.loads(json.dumps(golden_evidence()))
        mutate(evidence)
        cases.append((name, evidence, needle))

    add(
        "settings-mismatch",
        lambda ev: ev["readback"].__setitem__("context_tokens", 8192),
        "context_tokens",
    )
    add("settings-unverifiable", lambda ev: ev["readback"].pop("kv_dtype"), "kv_dtype unverifiable")
    add(
        "foreign-request",
        lambda ev: ev["engine_models"].append("other-model"),
        "foreign model",
    )
    add("memory-no-tree", lambda ev: ev["memory"].__setitem__("tree_walked", False), "process tree")
    add(
        "memory-no-engine-weight",
        lambda ev: ev["memory"].__setitem__("engine_weight_gb", None),
        "engine weight",
    )
    add(
        "memory-disagree",
        lambda ev: ev["memory"].__setitem__("vm_wired_delta_gb", 40.0),
        "engine resident",
    )
    add(
        "memory-contaminated-resident",
        lambda ev: ev["residency"]["after"]["omlx"].__setitem__("foreign-model", 1),
        "contaminated: omlx resident set changed",
    )
    add("tokens", lambda ev: ev["tokens"].__setitem__("tokenizer_completion", 90), "tokens:")
    add(
        "noise-unlabeled",
        lambda ev: ev["noise"].update({"later_delta_tps": 0.4, "labeled_no_difference": False}),
        "no difference",
    )
    add(
        "template-unexplained",
        lambda ev: ev["template"].update({"same_checkpoint": True, "match": False}),
        "template:",
    )
    add(
        "omlx-plain-mtp",
        lambda ev: ev.update(
            {
                "engine": "omlx",
                "mode": "plain",
                "readback": {**ev["readback"], "mtp_enabled": True, "dflash_enabled": False},
            }
        ),
        "oMLX plain",
    )
    add(
        "splash-plain-drafter",
        lambda ev: ev.update(
            {
                "engine": "splash",
                "mode": "plain",
                "launch_argv": ["splash", "serve", "--draft-model", "/tmp/draft"],
            }
        ),
        "Splash plain",
    )
    add(
        "vllm-served-path",
        lambda ev: ev.__setitem__(
            "served_model_id", "/Volumes/data01/omlx-models/Qwen3.8-27B-4bit"
        ),
        "filesystem path",
    )
    add("preflight-review", lambda ev: ev.__setitem__("preflight_verdict", "REVIEW"), "preflight")
    add("swap-ceiling", lambda ev: ev.__setitem__("swap_samples_mb", [100.0, 8000.0]), "swap used")
    return cases


def self_test() -> int:
    """Print one line per fixture. Exit 0 only when the golden passes and every defect fails."""
    golden = judge_cell(golden_evidence())
    print(f"PASS golden valid={golden['valid']} failures={golden['failures']}")
    ok = golden["valid"] and not golden["failures"]
    for name, evidence, needle in defect_cases():
        judged = judge_cell(evidence)
        hit = (not judged["valid"]) and any(needle in item for item in judged["failures"])
        print(f"{'PASS' if hit else 'FAIL'} defect {name} failures={judged['failures']}")
        ok = ok and hit
    labeled = json.loads(json.dumps(golden_evidence()))
    labeled["noise"]["later_delta_tps"] = 0.4
    labeled["noise"]["labeled_no_difference"] = True
    labeled_ok = judge_cell(labeled)["valid"]
    print(f"{'PASS' if labeled_ok else 'FAIL'} noise labeled no difference")
    return 0 if ok and labeled_ok else 1


def judge_path(path: Path) -> int:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    judged = judge_cell(evidence)
    print(json.dumps(judged, indent=1))
    return 0 if judged["valid"] else 1


def _http_json(
    url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
        return {"json": body, "headers": dict(response.headers)}


def _served_ids(engine_base: str) -> list[str] | None:
    """Ids from the engine's own ``/v1/models``. None when the endpoint is unreadable."""
    try:
        sent = _http_json(f"{engine_base.rstrip('/')}/v1/models", None, _engine_headers("omlx"), 10)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    data = sent["json"].get("data") if isinstance(sent.get("json"), dict) else None
    if not isinstance(data, list):
        return None
    return [str(item["id"]) for item in data if isinstance(item, dict) and item.get("id")]


def _pair_noise(samples: list[tuple[int | None, float]]) -> dict[str, float]:
    """Tok/s of two measured calls. Empty when either call has no usage or no duration."""
    rates: list[float] = []
    for tokens, elapsed in samples:
        if tokens is None or elapsed <= 0:
            return {}
        rates.append(float(tokens) / elapsed)
    if len(rates) < 2:
        return {}
    return {"run_a_tps": rates[0], "run_b_tps": rates[1]}


def _swap_used_mb() -> float | None:
    try:
        text = subprocess.check_output(["sysctl", "vm.swapusage"], text=True, timeout=10)
    except (subprocess.CalledProcessError, OSError):
        return None
    match = re.search(r"used = ([\d.]+)M", text)
    return float(match.group(1)) if match else None


def _process_argv(root: int | None) -> list[str]:
    if root is None:
        return []
    try:
        text = subprocess.check_output(
            ["ps", "-o", "command=", "-p", str(root)], text=True, timeout=10
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    return text.split()


def _put(
    readback: dict[str, Any],
    sources: dict[str, str],
    excluded: dict[str, dict[str, str]],
    key: str,
    value: Any,
    source: str,
    missing: str,
) -> None:
    if value is None:
        excluded[key] = _exclude(missing)
        return
    readback[key] = value
    sources[key] = source


def _ollama_spec(claims: dict[str, Any], excluded: dict[str, dict[str, str]]) -> None:
    if claims.get("spec_method") in _SPEC_OFF:
        excluded["spec_method"] = _exclude(
            "Ollama serves GGUF; no engine field reports a drafter or MTP"
        )
        excluded["drafter_loaded"] = _exclude(
            "Ollama serves GGUF; no engine field reports a drafter"
        )
        return
    excluded["spec_method"] = _invalidate("Ollama has no engine field that can show spec on")
    excluded["drafter_loaded"] = _invalidate(
        "Ollama has no engine field that can show a drafter loaded"
    )


def ollama_settings(
    spec: dict[str, Any], obs: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, str]], list[str]]:
    """Map Ollama claims onto /api/ps, /api/show, and the launchd plist."""
    readback: dict[str, Any] = {}
    sources: dict[str, str] = {}
    excluded: dict[str, dict[str, str]] = {}
    conflicts: list[str] = []
    show = obs.get("show") or {}
    plist = obs.get("plist") or {}
    row = (obs.get("ps") or {}).get(spec["model"]) or {}
    ctx = row.get("context_length")
    if isinstance(ctx, int):
        readback["context_tokens"] = ctx
        sources["context_tokens"] = "GET /api/ps context_length"
        if isinstance(show.get("num_ctx"), int) and show["num_ctx"] != ctx:
            conflicts.append("context_tokens /api/ps and /api/show num_ctx disagree")
    _put(
        readback,
        sources,
        excluded,
        "parallel_slots",
        plist.get("parallel_slots"),
        "com.portal5.ollama.plist OLLAMA_NUM_PARALLEL",
        "OLLAMA_NUM_PARALLEL is absent from the launchd plist",
    )
    _put(
        readback,
        sources,
        excluded,
        "kv_dtype",
        plist.get("kv_dtype"),
        "com.portal5.ollama.plist OLLAMA_KV_CACHE_TYPE",
        "OLLAMA_KV_CACHE_TYPE is absent from the launchd plist",
    )
    _put(
        readback,
        sources,
        excluded,
        "flash_attention",
        plist.get("flash_attention"),
        "com.portal5.ollama.plist OLLAMA_FLASH_ATTENTION",
        "OLLAMA_FLASH_ATTENTION is absent from the launchd plist",
    )
    _put(
        readback,
        sources,
        excluded,
        "temperature",
        show.get("temperature"),
        "GET /api/show parameters temperature",
        "Ollama /api/show parameters have no temperature; the seat value is a Pipeline injection",
    )
    _put(
        readback,
        sources,
        excluded,
        "thinking",
        show.get("thinking"),
        "GET /api/show parameters think",
        "Ollama /api/show does not report this request's think flag; template init is not that flag",
    )
    _ollama_spec(spec["claims"], excluded)
    excluded["pipeline_context_limit"] = _exclude(
        "seat context_limit is a Pipeline cap; /api/ps reports the baked context, and /v1 ignores runtime num_ctx"
    )
    return readback, sources, excluded, conflicts


def _omlx_mtp(
    applied: dict[str, Any],
    stored: dict[str, Any],
    log_text: str,
    readback: dict[str, Any],
    sources: dict[str, str],
    conflicts: list[str],
) -> str | None:
    mtp_log = applied.get("mtp_enabled")
    mtp_file = stored.get("mtp_enabled")
    if mtp_log is not None and mtp_file is not None and bool(mtp_log) != bool(mtp_file):
        conflicts.append("mtp_enabled server.log and model_settings.json disagree")
    if mtp_log is None:
        return None
    if bool(mtp_log) and _MTP_PATH_RE.search(log_text):
        readback["spec_method"] = "mtp"
        readback["mtp_enabled"] = True
        sources["spec_method"] = (
            "server.log Applied initial settings mtp_enabled + MTP path activated"
        )
        return "mtp"
    if bool(mtp_log):
        conflicts.append("mtp_enabled is true but the window has no MTP path activated line")
        return None
    readback["spec_method"] = "off"
    readback["mtp_enabled"] = False
    sources["spec_method"] = "server.log Applied initial settings mtp_enabled false"
    return "off"


def _omlx_acceptance(
    log_text: str,
    spec_method: str | None,
    readback: dict[str, Any],
    sources: dict[str, str],
    conflicts: list[str],
) -> None:
    if spec_method != "mtp":
        return
    kind, rate = acceptance_from_log(log_text)
    if kind == "rate":
        readback["acceptance"] = rate
        sources["acceptance"] = "server.log accept= rate"
        return
    if kind == "na":
        conflicts.append("acceptance: engine logged accept n/a")
        return
    conflicts.append("acceptance: no accept= line in the server.log window")


def omlx_settings(
    spec: dict[str, Any], obs: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, str]], list[str]]:
    """Map oMLX claims onto server.log, model status, and the settings files."""
    readback: dict[str, Any] = {}
    sources: dict[str, str] = {}
    excluded: dict[str, dict[str, str]] = {}
    conflicts: list[str] = []
    log_text = obs.get("server_log") or ""
    applied = parse_omlx_settings(log_text).get(spec["model"], {})
    stored = (obs.get("model_settings") or {}).get(spec["model"], {})
    row = obs.get("model_row") or {}
    if row.get("loaded") is not True:
        conflicts.append("model not loaded on GET /v1/models/status")
    if row.get("context_tokens") is not None:
        readback["context_tokens"] = row["context_tokens"]
        sources["context_tokens"] = "GET /v1/models/status model_context_length"
    slots = (obs.get("global_settings") or {}).get("max_concurrent_requests")
    if isinstance(slots, int):
        readback["parallel_slots"] = slots
        sources["parallel_slots"] = "~/.omlx/settings.json scheduler.max_concurrent_requests"
    else:
        excluded["parallel_slots"] = _exclude("scheduler.max_concurrent_requests is absent")
    if "temperature" in applied:
        readback["temperature"] = applied["temperature"]
        sources["temperature"] = "~/.omlx/logs/server.log Applied initial settings"
        if "temperature" in stored and stored["temperature"] != applied["temperature"]:
            conflicts.append("temperature server.log and model_settings.json disagree")
    elif "temperature" in stored:
        conflicts.append("temperature is only in model_settings.json; server.log did not apply it")
    else:
        excluded["temperature"] = _exclude(
            "neither server.log nor model_settings.json reports temperature"
        )
    _omlx_flags(
        applied,
        stored,
        log_text,
        row,
        spec["claims"].get("spec_method"),
        readback,
        sources,
        excluded,
        conflicts,
    )
    return readback, sources, excluded, conflicts


def _omlx_flags(
    applied: dict[str, Any],
    stored: dict[str, Any],
    log_text: str,
    row: dict[str, Any],
    claimed_spec: Any,
    readback: dict[str, Any],
    sources: dict[str, str],
    excluded: dict[str, dict[str, str]],
    conflicts: list[str],
) -> None:
    spec_method = _omlx_mtp(applied, stored, log_text, readback, sources, conflicts)
    if spec_method is None and "spec_method" not in readback:
        if claimed_spec in _SPEC_OFF:
            excluded["spec_method"] = _exclude(
                "server.log has no applied mtp_enabled for this model"
            )
        else:
            excluded["spec_method"] = _invalidate(
                "server.log window has no Applied initial settings mtp_enabled"
            )
    _omlx_acceptance(log_text, spec_method, readback, sources, conflicts)
    drafter = (
        True
        if stored.get("dflash_enabled") is True or applied.get("dflash_enabled") is True
        else None
    )
    _put(
        readback,
        sources,
        excluded,
        "drafter_loaded",
        drafter,
        "model_settings.json or server.log dflash_enabled",
        "no dflash_enabled in server.log or model_settings.json; MTP is not a separate drafter flag",
    )
    thinking = None
    if "enable_thinking" in applied or "thinking" in applied:
        thinking = bool(applied.get("enable_thinking", applied.get("thinking")))
    _put(
        readback,
        sources,
        excluded,
        "thinking",
        thinking,
        "server.log Applied initial settings",
        "Applied initial settings has no enable_thinking; thinking_default is not this request",
    )
    kv = stored.get("turboquant_kv_scheme") if stored.get("turboquant_kv_enabled") is True else None
    _put(
        readback,
        sources,
        excluded,
        "kv_dtype",
        kv,
        "model_settings.json turboquant_kv_scheme",
        "model_settings.json does not name a KV dtype (turboquant_kv_enabled is not true)",
    )
    _put(
        readback,
        sources,
        excluded,
        "engine_type",
        row.get("engine_type"),
        "GET /v1/models/status engine_type",
        "GET /v1/models/status has no engine_type for this model",
    )
    _record_disabled_spec(applied, stored, readback, sources)
    excluded["pipeline_context_limit"] = _exclude(
        "seat context_limit is a Pipeline cap; /v1/models/status reports model_context_length"
    )


def _record_disabled_spec(
    applied: dict[str, Any],
    stored: dict[str, Any],
    readback: dict[str, Any],
    sources: dict[str, str],
) -> None:
    """Plain cells need an explicit off. Absence of an enable flag is that evidence."""
    mtp_on = (
        applied.get("mtp_enabled") is True
        or stored.get("mtp_enabled") is True
        or stored.get("vlm_mtp_enabled") is True
    )
    dflash_on = applied.get("dflash_enabled") is True or stored.get("dflash_enabled") is True
    if readback.get("mtp_enabled") is None and not mtp_on:
        readback["mtp_enabled"] = False
        sources["mtp_enabled"] = "server.log and model_settings.json did not enable MTP"
    if not dflash_on:
        readback["dflash_enabled"] = False
        sources["dflash_enabled"] = "server.log and model_settings.json did not enable a drafter"


def _check_sources(spec: dict[str, Any]) -> dict[str, str]:
    if spec["engine"] == "omlx":
        route = (
            "Pipeline Backend succeeded log + x-portal-route + "
            "server.log Chat completion + GET /api/status total_requests"
        )
        memory = (
            "GET /v1/models/status actual_size is the oMLX model weight; omlx-server process-tree "
            "RSS excludes these weights and is reported separately (do not add). Compare actual_size "
            "to vm_stat wired delta within max(2 GB, 15%); free delta informational because page "
            "cache can make it differ. Before/after Ollama /api/ps and oMLX /v1/models/status "
            "resident sets must be unchanged except for this cell's model."
        )
    else:
        route = "Pipeline Backend succeeded log + x-portal-route + GET /api/ps expires_at refresh"
        memory = (
            "Ollama process-tree RSS includes the llama-server GGUF weights; GET /api/ps size_vram "
            "reports that same residency (report RSS separately; do not add). Compare size_vram to "
            "vm_stat wired delta within max(2 GB, 15%); free delta informational because page cache "
            "can make it differ. Before/after Ollama /api/ps and oMLX /v1/models/status resident "
            "sets must be unchanged except for this cell's model."
        )
    return {
        "route": route,
        "memory": memory,
        "tokens": (
            "Pipeline usage.completion_tokens vs tokenizer.json of content + reasoning "
            f"(tolerance {TOKEN_ABS_TOLERANCE} for template and stop tokens)"
        ),
        "noise": "two back-to-back Pipeline requests",
        "preflight": "instrument think-off probe, tool-call probe, and served id",
        "swap": "sysctl vm.swapusage",
        "template": "excluded; same_checkpoint is false on this seat",
    }


def route_models(
    spec: dict[str, Any], obs: dict[str, Any]
) -> tuple[list[str], dict[str, Any] | None]:
    if spec["engine"] == "omlx":
        before = obs.get("total_requests_before")
        after = obs.get("total_requests_after")
        counter = None
        if isinstance(before, int) and isinstance(after, int):
            counter = {"before": before, "after": after, "source": "GET /api/status total_requests"}
        return omlx_chat_models(obs.get("server_log") or ""), counter
    models: list[str] = []
    for before_ps, after_ps in obs.get("ps_refresh_pairs") or []:
        models.extend(ps_refreshed(before_ps, after_ps))
    return models, None


def assemble_cell(spec: dict[str, Any], obs: dict[str, Any]) -> dict[str, Any]:
    """Build judge evidence from already-captured engine and OS observations."""
    if spec["engine"] == "omlx":
        readback, sources, excluded, conflicts = omlx_settings(spec, obs)
    else:
        readback, sources, excluded, conflicts = ollama_settings(spec, obs)
    models, counter = route_models(spec, obs)
    headers = list(obs.get("route_headers") or [])
    routes = [{"header": header, "engine_model": None} for header in headers]
    for route, model in zip(routes, models, strict=False):
        route["engine_model"] = model
    pipe = [model for _ws, _be, model in obs.get("pipeline_routes") or []]
    excluded["template"] = _exclude(
        "single-engine stage0; the Ollama GGUF and the oMLX checkpoint are different bytes"
    )
    return {
        "engine": spec["engine"],
        "mode": spec["mode"],
        "claimed": spec["claims"],
        "readback": readback,
        "sources": sources,
        "excluded_claims": excluded,
        "source_conflicts": conflicts,
        "expected_model": spec["model"],
        "expected_workspace": spec["workspace"],
        "expected_backend": spec["backend"],
        "routes": routes,
        "engine_models": models,
        "pipeline_models": pipe,
        "request_counter": counter,
        "memory": obs.get("memory") or {},
        "residency": obs.get("residency"),
        "tokens": obs.get("tokens") or {},
        "noise": obs.get("noise") or {},
        "template": {"same_checkpoint": spec["same_checkpoint"]},
        "preflight_verdict": (obs.get("preflight") or {}).get("verdict"),
        "preflight": obs.get("preflight") or {},
        "swap_samples_mb": obs.get("swap_samples_mb") or [],
        "max_swap_growth_mb": 2048,
        "max_start_swap_used_mb": 4096,
        "served_model_id": obs.get("served_model_id"),
        "launch_argv": obs.get("launch_argv") or [],
        "check_sources": _check_sources(spec),
    }


def grade_preflight(reply: str, tool: dict[str, Any], served: str | None) -> dict[str, Any]:
    """Think-off, a real tool call, and a non-path served id. Anything else is REVIEW."""
    served_ok = isinstance(served, str) and not served_id_is_filesystem_path(served)
    think_ok = reply.upper().startswith("OK") and "<think>" not in reply.lower()
    verdict = "OK" if served_ok and think_ok and tool.get("ok") else "REVIEW"
    return {
        "verdict": verdict,
        "think_off_reply": reply[:80],
        "tool_call": tool,
        "served_model_id": served,
    }


def tool_from_message(message: dict[str, Any]) -> dict[str, Any]:
    calls = message.get("tool_calls") or []
    if not calls:
        return {"ok": False, "why": "no tool_calls"}
    function = calls[0].get("function") or {}
    raw = function.get("arguments") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "why": "arguments not JSON"}
    ok = function.get("name") == "get_weather" and "boston" in str(raw).lower()
    return {"ok": ok, "name": function.get("name"), "arguments": raw}


def completion_text(message: dict[str, Any]) -> str:
    """Content plus each distinct reasoning field. The engine counts both."""
    content = str(message.get("content") or "")
    parts = [content] if content else []
    seen = {content}
    for key in ("reasoning", "reasoning_content", "thinking"):
        extra = message.get(key)
        if isinstance(extra, str) and extra and extra not in seen:
            seen.add(extra)
            parts.append(extra)
    for call in message.get("tool_calls") or []:
        function = call.get("function") if isinstance(call, dict) else None
        if isinstance(function, dict):
            parts.extend(
                str(value) for value in (function.get("name"), function.get("arguments")) if value
            )
    return "\n".join(parts)


def _visible_reply(message: dict[str, Any]) -> str:
    extra = (
        message.get("thinking")
        or message.get("reasoning")
        or message.get("reasoning_content")
        or ""
    )
    content = message.get("content") or ""
    if extra:
        return f"<think>{extra}{content}"
    return str(content)


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    sent = _http_json(url, None, headers, 60)
    body = sent["json"]
    if not isinstance(body, dict):
        raise ValueError(f"{url} did not return an object")
    return body


def _engine_headers(engine: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if engine == "omlx" and os.environ.get("OMLX_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OMLX_API_KEY']}"
    return headers


def _ollama_resident_snapshot(base: str) -> dict[str, int | float] | None:
    payload = _get_json(f"{base}/api/ps", {})
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    sizes = {}
    for row in models:
        if not isinstance(row, dict):
            return None
        name = row.get("name") or row.get("model")
        size = row.get("size_vram")
        if not name or not isinstance(size, (int, float)) or size <= 0:
            return None
        sizes[str(name)] = size
    return sizes


def _omlx_resident_snapshot(base: str) -> dict[str, int | float] | None:
    payload = _get_json(f"{base}/v1/models/status", _engine_headers("omlx"))
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    sizes = {}
    for row in models:
        if not isinstance(row, dict) or not row.get("id"):
            return None
        loaded = row.get("loaded")
        if not isinstance(loaded, bool):
            return None
        if loaded:
            size = row.get("actual_size")
            if not isinstance(size, (int, float)) or size <= 0:
                return None
            sizes[str(row["id"])] = size
    return sizes


def _resident_snapshot(engine: str, base: str) -> dict[str, int | float] | None:
    reader = _ollama_resident_snapshot if engine == "ollama" else _omlx_resident_snapshot
    try:
        return reader(base)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


def _resident_snapshots(spec: dict[str, Any]) -> dict[str, dict[str, int | float] | None]:
    return {
        engine: _resident_snapshot(
            engine, spec["base"] if spec["engine"] == engine else _ENGINE_BASES[engine]
        )
        for engine in ("ollama", "omlx")
    }


def _pipeline_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if os.environ.get("PIPELINE_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['PIPELINE_API_KEY']}"
    return headers


def _ollama_show(spec: dict[str, Any]) -> dict[str, Any]:
    sent = _http_json(
        f"{spec['base']}/api/show",
        {"name": spec["model"]},
        {"Content-Type": "application/json"},
        60,
    )
    body = sent["json"]
    if not isinstance(body, dict):
        raise ValueError("/api/show did not return an object")
    return parse_ollama_show(body)


def _observe_before(spec: dict[str, Any]) -> dict[str, Any]:
    if spec["engine"] == "ollama":
        return {
            "plist": parse_ollama_plist(plistlib.loads(_OLLAMA_PLIST.read_bytes())),
            "show": _ollama_show(spec),
            "ps": {},
            "ps_refresh_pairs": [],
        }
    log = omlx_server_log()
    rejected = reject_engine_log(log)
    if rejected:
        raise ValueError(rejected)
    headers = _engine_headers("omlx")
    status = parse_omlx_api_status(_get_json(f"{spec['base']}/api/status", headers))
    settings = json.loads(
        (Path.home() / ".omlx" / "model_settings.json").read_text(encoding="utf-8")
    )
    global_settings = json.loads(
        (Path.home() / ".omlx" / "settings.json").read_text(encoding="utf-8")
    )
    stored = (settings.get("models") or {}).get(spec["model"]) or {}
    slots = (global_settings.get("scheduler") or {}).get("max_concurrent_requests")
    return {
        "log_offset": log.stat().st_size if log.is_file() else 0,
        "log_path": log,
        "total_requests_before": status.get("total_requests"),
        "model_settings": {spec["model"]: stored},
        "global_settings": {"max_concurrent_requests": slots},
        "server_log": "",
    }


def _observe_after(spec: dict[str, Any]) -> dict[str, Any]:
    if spec["engine"] != "omlx":
        return {}
    headers = _engine_headers("omlx")
    status = parse_omlx_api_status(_get_json(f"{spec['base']}/api/status", headers))
    models = _get_json(f"{spec['base']}/v1/models/status", headers)
    return {
        "total_requests_after": status.get("total_requests"),
        "status_after": status,
        "model_row": parse_omlx_model_row(models, spec["model"]),
    }


def _one_chat(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    sent = _http_json(url, body, headers, 600)
    message = (sent["json"].get("choices") or [{}])[0].get("message") or {}
    usage = sent["json"].get("usage") or {}
    tokens = usage.get("completion_tokens")
    header = sent["headers"].get("x-portal-route") or sent["headers"].get("X-Portal-Route") or ""
    return {
        "header": header,
        "engine_model": sent["json"].get("model"),
        "text": completion_text(message),
        "tokens": tokens if isinstance(tokens, int) else None,
        "elapsed": time.monotonic() - started,
        "message": message,
    }


def _require_pinned_route(spec: dict[str, Any], header: str) -> None:
    """Stop before the rest of the cell when the first route is a different model."""
    expected = f"{spec['workspace']};{spec['backend']};{spec['model']}"
    match = _ROUTE_RE.match(header)
    got = match.groups() if match else ()
    if got != (spec["workspace"], spec["backend"], spec["model"]):
        raise ValueError(f"route: first x-portal-route {header!r} is not the seat {expected}")


def _measured_pair(spec: dict[str, Any], pipeline: str, obs: dict[str, Any]) -> dict[str, Any]:
    url = f"{pipeline.rstrip('/')}/v1/chat/completions"
    body = {
        "model": spec["workspace"],
        "messages": [{"role": "user", "content": "Name three planets, one per line."}],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "portal_backend": spec["backend"],
    }
    headers_out: list[str] = []
    texts: list[str] = []
    samples: list[tuple[int | None, float]] = []
    hdrs = _pipeline_headers()
    for index in range(2):
        before = None
        if spec["engine"] == "ollama":
            before = parse_ollama_ps(_get_json(f"{spec['base']}/api/ps", {}))
        sent = _one_chat(url, body, hdrs)
        if index == 0:
            _require_pinned_route(spec, str(sent["header"]))
        headers_out.append(str(sent["header"]))
        texts.append(str(sent["text"]))
        samples.append((sent["tokens"], float(sent["elapsed"])))
        if before is not None:
            after = parse_ollama_ps(_get_json(f"{spec['base']}/api/ps", {}))
            obs["ps"] = after
            obs["ps_refresh_pairs"].append((before, after))
    if spec["engine"] == "omlx":
        obs["server_log"] = _appended_log(obs["log_path"], int(obs["log_offset"]))
    return {"headers": headers_out, "texts": texts, "samples": samples}


def _appended_log(log_path: Path, offset: int) -> str:
    if not log_path.is_file():
        return ""
    with log_path.open("rb") as handle:
        handle.seek(offset)
        return handle.read().decode("utf-8", "replace")


def _memory_from_text(
    engine: str, vm_before: str, weight: tuple[float | None, str]
) -> dict[str, Any]:
    try:
        before = parse_vm_stat(vm_before)
        after = parse_vm_stat(subprocess.check_output(["vm_stat"], text=True, timeout=10))
        deltas = vm_deltas_gb(before, after) or {}
        rows = parse_ps_tree(
            subprocess.check_output(["ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=10)
        )
    except (OSError, subprocess.CalledProcessError):
        deltas = {}
        rows = []
    root = _root_pid(engine)
    rss = tree_rss_gb(rows, root) if root else None
    weight_gb, weight_source = weight
    return {
        "tree_walked": root is not None and rss is not None,
        "tree_rss_gb": rss,
        "engine_weight_gb": weight_gb,
        "engine_weight_source": weight_source,
        "root": root,
        **deltas,
    }


def _root_pid(engine: str) -> int | None:
    name = "omlx-server" if engine == "omlx" else "ollama"
    try:
        text = subprocess.check_output(["pgrep", "-x", name], text=True, timeout=10).split()
    except (subprocess.CalledProcessError, OSError):
        return None
    return int(text[0]) if text else None


def engine_weight_gb(spec: dict[str, Any], obs: dict[str, Any]) -> tuple[float | None, str]:
    """Bytes the engine itself attributes to weights, as GB, plus the field name."""
    if spec["engine"] == "ollama":
        row = (obs.get("ps") or {}).get(spec["model"]) or {}
        size = row.get("size_vram")
        if isinstance(size, (int, float)) and size > 0:
            return float(size) / (1024**3), "GET /api/ps size_vram"
        return None, ""
    row = obs.get("model_row") or {}
    status = obs.get("status_after") or {}
    for key, source in (
        ("actual_size", "GET /v1/models/status actual_size"),
        ("estimated_size", "GET /v1/models/status estimated_size"),
    ):
        size = row.get(key)
        if isinstance(size, (int, float)) and size > 0:
            return float(size) / (1024**3), source
    used = status.get("model_memory_used")
    if isinstance(used, (int, float)) and used > 0:
        return float(used) / (1024**3), "GET /api/status model_memory_used"
    return None, ""


def _served_for(spec: dict[str, Any]) -> str | None:
    if spec["engine"] == "ollama":
        payload = _get_json(f"{spec['base']}/api/tags", {})
        names = [
            str(item["name"])
            for item in payload.get("models") or []
            if isinstance(item, dict) and item.get("name")
        ]
    else:
        names = _served_ids(spec["base"]) or []
    for name in names:
        if served_id_is_filesystem_path(name):
            return name
    return spec["model"] if spec["model"] in names else None


def _think_off(spec: dict[str, Any]) -> str:
    messages = [{"role": "user", "content": "Reply with exactly: OK"}]
    if spec["engine"] == "ollama":
        sent = _http_json(
            f"{spec['base']}/api/chat",
            {
                "model": spec["model"],
                "messages": messages,
                "think": False,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 32},
            },
            {"Content-Type": "application/json"},
            600,
        )
        return _visible_reply(sent["json"].get("message") or {})
    sent = _one_chat(
        f"{spec['base']}/v1/chat/completions",
        {
            "model": spec["model"],
            "messages": messages,
            "temperature": 0,
            "max_tokens": 32,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        _engine_headers("omlx"),
    )
    return _visible_reply(sent["message"])


def _tool_probe(spec: dict[str, Any]) -> dict[str, Any]:
    messages = [{"role": "user", "content": "What is the weather in Boston? Use the tool."}]
    if spec["engine"] == "ollama":
        sent = _http_json(
            f"{spec['base']}/api/chat",
            {
                "model": spec["model"],
                "messages": messages,
                "tools": _TOOL_SPEC,
                "think": False,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 128},
            },
            {"Content-Type": "application/json"},
            600,
        )
        return tool_from_message(sent["json"].get("message") or {})
    sent = _one_chat(
        f"{spec['base']}/v1/chat/completions",
        {
            "model": spec["model"],
            "messages": messages,
            "tools": _TOOL_SPEC,
            "temperature": 0,
            "max_tokens": 128,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        _engine_headers("omlx"),
    )
    return tool_from_message(sent["message"])


def _run_preflight(spec: dict[str, Any]) -> dict[str, Any]:
    return grade_preflight(_think_off(spec), _tool_probe(spec), _served_for(spec))


def _tokenizer_count(spec: dict[str, Any], text: str) -> int | None:
    path = resolve_tokenizer(spec["engine"], spec.get("checkpoint"), None)
    if path is None:
        return None
    return count_tokens(text, path)


def _swap_pair(before: float | None) -> list[float]:
    after = _swap_used_mb()
    if before is None or after is None:
        return []
    return [before, after]


def _pipeline_log_since(since: str) -> str:
    return subprocess.check_output(
        ["docker", "logs", "--since", since, "portal5-pipeline"],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=60,
    )


def collect_stage0(spec: dict[str, Any], pipeline: str) -> dict[str, Any]:
    """Capture vm_stat, send the Pipeline pair, then preflight. Does not unload."""
    vm_before = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    swap_before = _swap_used_mb()
    resident_before = _resident_snapshots(spec)
    obs = _observe_before(spec)
    since = time.strftime("%Y-%m-%dT%H:%M:%S")
    measured = _measured_pair(spec, pipeline, obs)
    obs.update(_observe_after(spec))
    text = measured["texts"][0] if measured["texts"] else ""
    preflight = _run_preflight(spec)
    resident_after = _resident_snapshots(spec)
    memory = _memory_from_text(spec["engine"], vm_before, engine_weight_gb(spec, obs))
    root = memory.pop("root")
    obs.update(
        {
            "route_headers": measured["headers"],
            "pipeline_routes": parse_pipeline_routes(_pipeline_log_since(since)),
            "memory": memory,
            "residency": {"before": resident_before, "after": resident_after},
            "tokens": {
                "engine_completion": measured["samples"][0][0] if measured["samples"] else None,
                "tokenizer_completion": _tokenizer_count(spec, text),
            },
            "noise": _pair_noise(measured["samples"]),
            "swap_samples_mb": _swap_pair(swap_before),
            "preflight": preflight,
            "served_model_id": preflight.get("served_model_id"),
            "launch_argv": _process_argv(root),
        }
    )
    return assemble_cell(spec, obs)


def _print_verdict(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=1))


def stage0(argv: list[str]) -> int:
    """One command for a production baseline. The orchestrator unloads first."""
    parser = argparse.ArgumentParser(description="Prove one production baseline cell")
    parser.add_argument("--engine", required=True, choices=("ollama", "omlx"))
    parser.add_argument("--seat", required=True)
    parser.add_argument("--pipeline", default="http://127.0.0.1:9099")
    args = parser.parse_args(argv)
    try:
        spec = seat_plan(args.seat, args.engine)
    except KeyError:
        _print_verdict(
            {"verdict": {"valid": False, "failures": [f"instrument: unknown seat {args.seat}"]}}
        )
        return 2
    try:
        evidence = collect_stage0(spec, args.pipeline)
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        KeyError,
    ) as exc:
        _print_verdict(
            {"verdict": {"valid": False, "failures": [f"instrument: {type(exc).__name__}: {exc}"]}}
        )
        return 1
    judged = judge_cell(evidence)
    _print_verdict(
        {
            "verdict": judged,
            "sources": evidence.get("sources"),
            "excluded_claims": evidence.get("excluded_claims"),
            "check_sources": evidence.get("check_sources"),
            "readback": evidence.get("readback"),
            "preflight": evidence.get("preflight"),
            "memory": evidence.get("memory"),
            "residency": evidence.get("residency"),
            "tokens": evidence.get("tokens"),
            "source_conflicts": evidence.get("source_conflicts"),
        }
    )
    return 0 if judged["valid"] else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"self-test", "judge", "stage0"}:
        print(
            "usage: engine_eval_instrument.py self-test | judge --evidence FILE | "
            "stage0 --engine ollama --seat daily-moe | "
            "stage0 --engine omlx --seat hunt-reasoning",
            file=sys.stderr,
        )
        return 2
    if argv[0] == "self-test":
        return self_test()
    if argv[0] == "judge":
        parser = argparse.ArgumentParser()
        parser.add_argument("--evidence", required=True, type=Path)
        args = parser.parse_args(argv[1:])
        return judge_path(args.evidence)
    return stage0(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
