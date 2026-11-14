#!/usr/bin/env python3
"""Run managed engine-eval canaries and guard Stage 3 receipts."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
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


def _unload_production_model(engine: str, model: str, cfg: dict[str, Any]) -> None:
    base = h2h.base_url(cfg, engine)
    if engine == "ollama":
        h2h.http_json(
            f"{base}/api/generate",
            {"model": model, "keep_alive": 0, "stream": False},
            timeout=60,
        )
        return
    h2h.http_json(f"{base}/v1/models/{quote(model, safe='')}/unload", {}, timeout=60)


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


def _candidate_body(cell: dict[str, Any]) -> dict[str, Any]:
    """Build the same two-request preflight/noise probe for every cell."""
    return {
        "model": cell["workspace"],
        "messages": [
            {
                "role": "user",
                "content": (
                    "Reply with exactly OK in visible text and invoke get_weather for Boston."
                ),
            }
        ],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "tools": instrument._TOOL_SPEC,
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        "think": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "portal_backend": cell["backend"],
    }


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
    if engine == "mlx-serve":
        match = re.search(r"\bprompt=(\d+) tokens\b", log_text)
    elif engine == "mlx_lm.server":
        match = re.search(r"Prompt processing progress: \d+/(\d+)", log_text)
    else:
        match = re.search(r"\bprompt_tokens[=: ]+(\d+)\b", log_text)
    return int(match.group(1)) if match else None


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
    return {
        "requests": [body, body],
        "outputs": [_candidate_output(row["message"]) for row in ctx["rows"]],
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
        "rendered_prompt_token_count": _candidate_prompt_token_count(cell["engine"], log_text),
        "rendered_prompt_token_count_source": "engine stderr/stdout log",
    }


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
    return left_count is not None and right_count is not None and left_count != right_count


def _classify_candidate_outputs(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[str, list[str]]:
    if not _outputs_are_stable(left) or not _outputs_are_stable(right):
        return "sampling_or_nondeterminism", ["repeated output differed with temperature 0"]
    if _effective_temperature_nonzero(left, right):
        return "sampling_field_not_honored", ["an engine read back a nonzero effective temperature"]
    if _rendered_prompt_counts_differ(left, right):
        return "chat_template_rendering_mismatch", [
            "same request rendered to different prompt token counts"
        ]
    if (left.get("outputs") or [None])[0] != (right.get("outputs") or [None])[0]:
        return "greedy_output_mismatch_unexplained", [
            "greedy outputs differ with no prompt-length explanation"
        ]
    return "match", []


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
        classification = "sampling_request_mismatch"
        findings.append("parity requests are not identical greedy requests with fixed max_tokens")
    else:
        classification, output_findings = _classify_candidate_outputs(left, right)
        findings.extend(output_findings)
    left_max_tokens = left.get("max_tokens", left_request.get("max_tokens"))
    return {
        "valid": classification == "match",
        "classification": classification,
        "requested_temperature": 0,
        "max_tokens": left_max_tokens,
        "outputs_equal": (left.get("outputs") or [None])[0] == (right.get("outputs") or [None])[0],
        "rendered_prompt_token_counts": {
            "left": left.get("rendered_prompt_token_count"),
            "right": right.get("rendered_prompt_token_count"),
        },
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
    rows = []
    memory_models_response = None
    memory = None
    for index in range(2):
        rows.append(_candidate_request(url, body))
        if index == 0:
            memory_models_response = _models_payload(cell["base"])
            memory = _candidate_memory(
                vm_before,
                cell["port"],
                cell["engine"],
                cfg["engines"][cell["engine"]],
                _model_row(memory_models_response["json"], cell["expected_model"]),
            )
    resident_after = _candidate_residency(cfg)
    log = instrument._pipeline_log_since(log_since)
    first_message = rows[0]["message"]
    request_served_model = rows[0].get("engine_model")
    preflight = instrument.grade_preflight(
        instrument._visible_reply(first_message),
        instrument.tool_from_message(first_message),
        request_served_model if request_served_model == cell["expected_model"] else None,
    )
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
        "log": log,
        "engine_log_text": _candidate_engine_log_text(started_info or {}),
        "preflight": preflight,
        "tokenizer": tokenizer,
        "started_info": started_info or {},
    }


def _candidate_evidence_sources(cell: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = {
        "engine_models": f"POST /v1/chat/completions response.model ({OPENAI_CHAT_SOURCE})",
        "served_model_id": f"POST /v1/chat/completions response.model ({OPENAI_CHAT_SOURCE})",
        "pipeline_route": "Pipeline x-portal-route, logs, and response model",
        "tokens": "Pipeline usage and the registered checkpoint tokenizer.json",
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
        "tokens": {
            "engine_completion": ctx["rows"][0]["tokens"],
            "tokenizer_completion": instrument.count_tokens(
                ctx["rows"][0]["text"], ctx["tokenizer"]
            )
            if ctx["tokenizer"]
            else None,
        },
        "noise": instrument._pair_noise([(row["tokens"], row["elapsed"]) for row in ctx["rows"]]),
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
            "preflight": "think-off and get_weather call through the Pipeline",
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


def normalise_reason(text: str) -> str:
    """Collapse ids and counts so the same failure matches across cells."""
    text = _one_line(text)
    text = re.sub(r"eval-openai[A-Za-z0-9_.-]*", "eval-backend", text)
    text = re.sub(r"\b\d+\b", "N", text)
    return text[:300]


def _stamp_reason(receipt: dict[str, Any]) -> None:
    failures = [str(item) for item in receipt.get("failures") or []]
    if receipt.get("valid") is True and not failures:
        receipt["reason"] = "ok"
    else:
        receipt["reason"] = _one_line(
            failures[0] if failures else receipt.get("reason") or "invalid"
        )
    receipt["reason_norm"] = normalise_reason(str(receipt["reason"]))
    if "structural readiness" in str(receipt["reason"]):
        receipt["structural_readiness"] = True


def _cell_selector(cell: dict[str, Any]) -> str:
    return f"{cell['engine']}:{cell['mode']}:{cell['seat']}"


def _progress(cell: dict[str, Any], valid: bool, reason: str, elapsed_s: float) -> None:
    state = "valid" if valid else "invalid"
    print(f"{_cell_selector(cell)} | {state} | {reason} | {elapsed_s:.0f}s", flush=True)


def _canary_should_stop(results: list[dict[str, Any]]) -> str | None:
    """Two consecutive invalid cells with one reason, or a blind readiness check."""
    if results and results[-1].get("structural_readiness"):
        return "structural readiness check cannot pass"
    last_evidence = results[-1].get("evidence") if results else None
    last_template = last_evidence.get("template") if isinstance(last_evidence, dict) else None
    last_parity = last_template.get("parity") if isinstance(last_template, dict) else None
    failures = results[-1].get("failures") if results else []
    non_parity_failures = [
        failure
        for failure in failures or []
        if not str(failure).startswith("template: paired greedy parity is pending")
    ]
    if (
        isinstance(last_parity, dict)
        and not last_parity.get("comparisons")
        and not non_parity_failures
    ):
        return None
    if len(results) < 2 or results[-1].get("valid") is True:
        return None
    prev = results[-2]
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


def _reconcile_candidate_parity(
    root: Path, build: str, results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not results:
        return results
    family_keys = {
        tuple(str(cell.get(key) or "") for key in ("seat", "mode", "model", "workspace"))
        for result in results
        if ((result.get("evidence") or {}).get("template") or {}).get("same_checkpoint") is True
        for cell in [result.get("cell") or {}]
    }
    if not family_keys:
        return results
    all_cells = candidate_cells()
    updated = {}
    for family_key in family_keys:
        families = _candidate_parity_family(root, build, family_key, all_cells)
        comparisons = _candidate_family_comparisons(families)
        updated.update(_save_candidate_parity_comparisons(families, comparisons))
    return [updated.get(_cell_id(result.get("cell") or {}), result) for result in results]


def _candidate_parity_family(
    root: Path, build: str, family_key: tuple[str, ...], cells: list[dict[str, Any]]
) -> dict[str, tuple[Path, dict[str, Any], dict[str, Any]]]:
    families = {}
    for cell in cells:
        cell_key = tuple(str(cell.get(key) or "") for key in ("seat", "mode", "model", "workspace"))
        if cell_key != family_key:
            continue
        path = canary_receipt_path(root, build, cell)
        if not path.is_file():
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        evidence = receipt.get("evidence") or {}
        template = evidence.get("template") or {}
        parity = template.get("parity")
        if (
            receipt.get("build") == build
            and template.get("same_checkpoint") is True
            and isinstance(parity, dict)
        ):
            families[cell["engine"]] = (path, receipt, parity)
    return families


def _candidate_family_comparisons(
    families: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    comparisons = {engine: {} for engine in families}
    engines = sorted(families)
    for index, left_engine in enumerate(engines):
        for right_engine in engines[index + 1 :]:
            left, right = families[left_engine][2], families[right_engine][2]
            forward = _compare_candidate_parity(left, right)
            forward["engines"] = {"left": left_engine, "right": right_engine}
            reverse = _compare_candidate_parity(right, left)
            reverse["engines"] = {"left": right_engine, "right": left_engine}
            comparisons[left_engine][right_engine] = forward
            comparisons[right_engine][left_engine] = reverse
    return comparisons


def _save_candidate_parity_comparisons(
    families: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]],
    comparisons: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    updated = {}
    for engine, (path, receipt, _parity) in families.items():
        parity = receipt["evidence"]["template"]["parity"]
        parity["comparisons"] = comparisons[engine]
        if comparisons[engine]:
            parity["status"] = "compared"
        else:
            parity["status"] = "awaiting_peer"
            parity["comparisons"] = {
                "pending": {
                    "valid": False,
                    "classification": "awaiting_peer",
                    "findings": ["same-checkpoint peer cell receipt is missing for this build"],
                }
            }
        judged = instrument.judge_cell(receipt["evidence"])
        receipt["valid"] = judged["valid"]
        receipt["failures"] = judged["failures"]
        _stamp_reason(receipt)
        if json.loads(path.read_text(encoding="utf-8")) != receipt:
            _write_json(path, receipt)
        updated[_cell_id(receipt.get("cell") or {})] = receipt
    return updated


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
    results = _reconcile_candidate_parity(root, build, results)
    for receipt in results:
        cell = receipt.get("cell") or {}
        _progress(
            cell,
            bool(receipt.get("valid")),
            str(receipt.get("reason") or ""),
            float(receipt.get("elapsed_s") or 0),
        )
    summary = root / "engine_eval" / "canaries" / build / "table.json"
    _write_json(
        summary,
        {"build": build, "stopped": stop_reason, "cells": _canary_table(results)},
    )
    print(f"cells {len(results)} stopped={stop_reason or 'no'}", flush=True)
    invalid = any(item.get("valid") is not True for item in results) or bool(stop_reason)
    return results, 2 if invalid else 0


def _canary_table(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table = []
    for result in results:
        cell = result.get("cell") or {}
        table.append(
            {
                "cell": cell,
                "valid": result.get("valid"),
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
            f"WFE {arm['role']} exited {result.returncode}: {result.stderr[-1000:]}"
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


@contextlib.contextmanager
def _running_cells(
    cells: list[dict[str, Any]], root: Path, build: str, context_tokens: int | None = None
):
    """Start distinct canary-qualified managed engines and always verify shutdown."""
    cfg = h2h.load_config()
    managed = [cell for cell in cells if not _is_external(cell)]
    if len({cell["engine"] for cell in managed}) != len(managed):
        raise Stage3BlockedError("co-resident cells must use distinct fixed engine ports")
    for cell in cells:
        _gate_canary(root, build, cell)
        if not _is_external(cell) and h2h.pid_on_port(cell["port"]):
            raise Stage3BlockedError(f"candidate port {cell['port']} is already occupied")
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
            yield infos
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
        with _running_cells([cell], root, build):
            return _run_wfe_arm(*args, **options)
    return _run_wfe_arm(*args, **options)


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
    with _running_cells(chosen, root, build):
        specs = []
        for index in range(8):
            specs.append((by_seat["hunt"], f"json-{index}", True))
        for index in range(2):
            specs.append((by_seat["daily-moe"], f"chat-{index}", False))
            specs.append((by_seat["task-router"], f"router-{index}", False))

        def request(spec: tuple[dict[str, Any], str, bool]) -> dict[str, Any]:
            target, label, as_json = spec
            message = (
                f"Return only a JSON object with keys ok=true and slot={label}."
                if as_json
                else f"Reply exactly OK for request {label}."
            )
            extra = {"response_format": {"type": "json_object"}} if as_json else {}
            result = _pipeline_request(
                target, pipeline, [{"role": "user", "content": message}], **extra
            )
            if as_json:
                try:
                    parsed = json.loads(result["text"])
                    result["json_valid"] = parsed.get("ok") is True and parsed.get("slot") == label
                except json.JSONDecodeError:
                    result["json_valid"] = False
            result["label"] = label
            result["valid"] = _route_valid(result) and (result.get("json_valid", True))
            return result

        with ThreadPoolExecutor(max_workers=12) as pool:
            requests = list(pool.map(request, specs))
    failed = [row for row in requests if not row["valid"]]
    return {
        "status": "PASS" if not failed else "FAIL",
        "valid": not failed,
        "pass_rule": _protocol_workload("concurrency-mix").get("pass"),
        "cells": [
            {"engine": item["engine"], "seat": item["seat"], "port": item["port"]}
            for item in chosen
        ],
        "requests": requests,
        "failures": [row["label"] for row in failed],
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


def _run_long_context(
    cell: dict[str, Any], root: Path, build: str, pipeline: str
) -> dict[str, Any]:
    protocol = _protocol_workload("long-context")
    windows = {row["seat"]: int(row["context_tokens"]) for row in protocol.get("windows") or []}
    if cell["workspace"] not in windows:
        return {
            "status": "NOT_APPLICABLE",
            "valid": True,
            "reason": "seat has no registered long-context window",
        }
    context_tokens = windows[cell["seat"]]
    cfg = h2h.load_config()
    tokenizer = _candidate_tokenizer(cfg, cell)
    if tokenizer is None:
        raise Stage3BlockedError("checkpoint tokenizer.json is not available locally")
    source = h2h.prefill_text(context_tokens * h2h.CHARS_PER_TOKEN * 2)
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
    with _running_cells([cell], root, build, context_tokens=context_tokens):
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
    with _running_cells([cell], root, build):
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
    vm_before = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    residency_before = _candidate_residency(h2h.load_config())
    swap_before = h2h.swap_now().get("used_mb")
    with _running_cells(chosen, root, build):
        requests = [
            _pipeline_request(target, pipeline, [{"role": "user", "content": "Reply exactly OK."}])
            for target in chosen
        ]
        swap_after = h2h.swap_now().get("used_mb")
        residency_after = _candidate_residency(h2h.load_config())
        vm_after = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    growth = None if swap_before is None or swap_after is None else swap_after - swap_before
    delta = instrument.vm_deltas_gb(
        instrument.parse_vm_stat(vm_before), instrument.parse_vm_stat(vm_after)
    )
    swap_gate = (
        swap_after is not None
        and swap_after <= float(h2h.load_config()["guard"]["max_start_swap_used_mb"])
        and growth is not None
        and growth <= float(h2h.load_config()["guard"]["max_swap_growth_mb"])
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
        return _run_quality_workload(cell, workload, root, build, pipeline, compare=False)
    if workload == "concurrency-mix":
        return _run_concurrency_workload(cell, root, build, pipeline)
    if workload == "long-context":
        return _run_long_context(cell, root, build, pipeline)
    if workload == "co-residence":
        return _run_co_residence(cell, root, build, pipeline)
    if workload == "soak":
        return _run_soak_workload(cell, root, build, pipeline)
    raise Stage3BlockedError(f"workload {workload!r} has no task-specific runner mapping")


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
    "tool-turn": 10 * 60,
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


def build_stage3_plan(build: str) -> dict[str, Any]:
    """List current-build valid canary cells and their incumbent pairs. Does not run."""
    head = current_build()
    if build != head:
        raise Stage3BlockedError(f"canary build {build} is not the current build {head}")
    root = data_root()
    candidates = _valid_canary_cells(root, build)
    seats = list(dict.fromkeys(cell["seat"] for cell in candidates))
    entries = [_plan_entry(cell, "candidate") for cell in candidates]
    for seat in seats:
        entries.extend(_plan_entry(cell, "incumbent") for cell in incumbent_pair(seat))
    plan = {
        "build": build,
        "estimate_note": "upper bound in seconds, not a measurement",
        "estimate_s": sum(int(entry["estimate_s"]) for entry in entries),
        "cells": entries,
    }
    _write_json(_stage3_dir(root, build) / "plan.json", plan)
    return plan


def _print_plan(plan: dict[str, Any]) -> None:
    print(
        f"build {plan['build']} cells {len(plan['cells'])} "
        f"estimate_s {plan['estimate_s']} (upper bound, not a measurement)",
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
    result["reason_norm"] = normalise_reason(reason)
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
        "reason_norm": normalise_reason(reason),
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
        "reason_norm": normalise_reason(reason),
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
                "incumbent": _cell_selector(incumbent["cell"]) if incumbent else "missing",
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
    stage3_run = sub.add_parser("stage3-run")
    stage3_run.add_argument("--plan", required=True)
    stage3_run.add_argument("--pipeline", default="http://127.0.0.1:9099")
    args = parser.parse_args(argv)
    try:
        if args.command == "canary":
            _results, code = run_canary(args.pipeline, only=args.cell)
            return code
        if args.command == "stage3-plan":
            built = build_stage3_plan(args.from_canary)
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
