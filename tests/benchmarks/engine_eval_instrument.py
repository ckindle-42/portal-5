#!/usr/bin/env python3
"""Fail a measured cell unless independent evidence matches what it claims.

Sources are the engine log, the engine endpoint, the Pipeline route header, and
the OS (process tree, Metal wired, vm_stat). The harness's own intent is not
evidence. A missing source is an invalid cell.

    uv run python tests/benchmarks/engine_eval_instrument.py self-test
    uv run python tests/benchmarks/engine_eval_instrument.py judge --evidence cell.json
    uv run python tests/benchmarks/engine_eval_instrument.py prove --help

``prove`` reads the running Ollama and oMLX services. It does not start, stop,
or restart them.
"""

from __future__ import annotations

import argparse
import ast
import json
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
TOKEN_ABS_TOLERANCE = 2

REQUIRED_CLAIMS = (
    "spec_method",
    "drafter_loaded",
    "context_tokens",
    "parallel_slots",
    "kv_dtype",
    "thinking",
    "temperature",
)
_TEMPLATE_REASONS = frozenset({"template", "bos", "stop"})
_SPEC_OFF = frozenset({"off", "plain", "none"})

_SETTINGS_RE = re.compile(r"Applied initial settings for ([^:]+): (\{.*\})\s*$")
_CHAT_MODEL_RE = re.compile(r"Chat completion: model=([^,\s]+)")
_ACCEPT_RE = re.compile(r"accept=\d+/\d+ \(([0-9.]+)%\)")
_N_CTX_RE = re.compile(r"n_ctx\s*=\s*(\d+)")
_N_SEQ_RE = re.compile(r"n_seq_max\s*=\s*(\d+)")
_OLLAMA_MODEL_RE = re.compile(r"\bmodel=([^\s]+)")
_ROUTE_RE = re.compile(r"^([^;]+);([^;]*);(.*)$")
_VM_PAGE_RE = re.compile(r"page size of (\d+) bytes")
_VM_PAGES_RE = re.compile(r"^Pages (.+?):\s+([\d.]+)\.?\s*$", re.M)
_FOOTPRINT_RE = re.compile(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", re.I)
_METAL_RE = re.compile(
    r"(?:IOAccelerator|Metal|graphics).{0,40}?([0-9.]+)\s*(KB|MB|GB)",
    re.I,
)


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


def parse_metal_wired_gb(footprint_text: str) -> float | None:
    """Sum of Metal/IOAccelerator wired sizes in a ``footprint`` report."""
    factor = {"KB": 1 / (1024**2), "MB": 1 / 1024, "GB": 1.0}
    total = 0.0
    found = False
    for match in _METAL_RE.finditer(footprint_text):
        total += float(match.group(1)) * factor[match.group(2).upper()]
        found = True
    return total if found else None


def method_a_gb(tree_rss_gb: float, metal_wired_gb: float) -> float:
    """Process-tree RSS plus Metal wired. The 11-13 footprint missed both pieces."""
    return tree_rss_gb + metal_wired_gb


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


def _check_settings(evidence: dict[str, Any], failures: list[str]) -> None:
    claimed = evidence.get("claimed")
    readback = evidence.get("readback")
    if not isinstance(claimed, dict) or not isinstance(readback, dict):
        _fail(failures, "settings: claimed or readback missing")
        return
    for key in REQUIRED_CLAIMS:
        if key not in claimed:
            _fail(failures, f"settings: {key} not claimed")
            continue
        if key not in readback:
            _fail(failures, f"settings: {key} unverifiable")
            continue
        if claimed[key] != readback[key]:
            _fail(failures, f"settings: {key} claimed {claimed[key]!r} read back {readback[key]!r}")
    spec = claimed.get("spec_method")
    if spec not in _SPEC_OFF and "acceptance" not in readback:
        _fail(failures, "settings: acceptance unverifiable")
    elif spec not in _SPEC_OFF and claimed.get("acceptance") != readback.get("acceptance"):
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
    if len(engine_models) < len(routes):
        _fail(failures, "route: engine log has fewer requests than the pipeline")
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


def _check_memory(evidence: dict[str, Any], failures: list[str]) -> None:
    memory = evidence.get("memory")
    if not isinstance(memory, dict) or not memory.get("tree_walked"):
        _fail(failures, "memory: process tree was not walked")
        return
    metal = memory.get("metal_wired_gb")
    rss = memory.get("tree_rss_gb")
    wired = memory.get("vm_wired_delta_gb")
    free = memory.get("vm_free_delta_gb")
    if metal is None:
        _fail(failures, "memory: Metal/IOAccelerator wired unread")
        return
    if rss is None or wired is None or free is None:
        _fail(failures, "memory: rss or vm_stat delta missing")
        return
    if not _agree(float(wired), float(free)):
        _fail(failures, "memory: vm_stat wired and free deltas disagree")
    combined = method_a_gb(float(rss), float(metal))
    if not _agree(combined, float(wired)):
        _fail(failures, f"memory: tree+metal {combined:.2f}GB vs wired delta {float(wired):.2f}GB")


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
        _fail(failures, f"tokens: engine {engine} vs tokenizer {local}")


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
    if template.get("match") is True:
        return
    reason = template.get("reason")
    if reason in _TEMPLATE_REASONS and template.get("note"):
        return
    _fail(failures, "template: outputs differ without a template, BOS, or stop explanation")


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
        "expected_model": model,
        "expected_workspace": "auto-daily",
        "expected_backend": "ollama-general",
        "routes": [{"header": f"auto-daily;ollama-general;{model}", "engine_model": model}],
        "engine_models": [model],
        "memory": {
            "tree_walked": True,
            "tree_rss_gb": 2.0,
            "metal_wired_gb": 14.0,
            "vm_wired_delta_gb": 16.0,
            "vm_free_delta_gb": 16.2,
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
    add("memory-no-metal", lambda ev: ev["memory"].__setitem__("metal_wired_gb", None), "Metal")
    add(
        "memory-disagree",
        lambda ev: ev["memory"].__setitem__("vm_wired_delta_gb", 40.0),
        "tree+metal",
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


def _models_in_window(engine: str, appended: str) -> list[str]:
    """Model ids the engine log named during the cell. The claim is not a source."""
    if engine == "omlx":
        return omlx_chat_models(appended)
    return _OLLAMA_MODEL_RE.findall(appended)


def _served_ids(engine_base: str) -> list[str] | None:
    """Ids from the engine's own ``/v1/models``. None when the endpoint is unreadable."""
    try:
        sent = _http_json(f"{engine_base.rstrip('/')}/v1/models", None, {}, 10)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    data = sent["json"].get("data") if isinstance(sent.get("json"), dict) else None
    if not isinstance(data, list):
        return None
    return [str(item["id"]) for item in data if isinstance(item, dict) and item.get("id")]


def _served_model_id(engine_base: str, expected: str) -> str | None:
    """The id the engine listed, preferring a path id so a path serve cannot pass."""
    ids = _served_ids(engine_base)
    if ids is None:
        return None
    for model_id in ids:
        if served_id_is_filesystem_path(model_id):
            return model_id
    return expected if expected in ids else None


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


def prove(argv: list[str]) -> int:
    """Collect one live cell and judge it. Does not start or stop an engine."""
    parser = argparse.ArgumentParser(description="Judge one live Ollama or oMLX cell")
    parser.add_argument("--engine", required=True, choices=("ollama", "omlx"))
    parser.add_argument("--model", required=True, help="Engine model id the cell claims")
    parser.add_argument("--mode", required=True, choices=("plain", "spec"))
    parser.add_argument(
        "--workspace", required=True, help="Pipeline workspace id (OWUI model field)"
    )
    parser.add_argument("--backend-id", required=True, help="Expected x-portal-route backend id")
    parser.add_argument("--pipeline", default="http://127.0.0.1:9099")
    parser.add_argument("--engine-base", required=True, help="Engine base URL, no path")
    parser.add_argument("--log", required=True, help="Engine log file")
    parser.add_argument(
        "--vm-before", required=True, help="vm_stat captured before this model was resident"
    )
    parser.add_argument(
        "--tokenizer", required=True, help="tokenizer.json of the checkpoint the engine loaded"
    )
    parser.add_argument("--claims", required=True, help="JSON object of claimed settings")
    parser.add_argument("--prompt", default="Reply with exactly: OK")
    args = parser.parse_args(argv)
    evidence = _collect_live_evidence(args)
    judged = judge_cell(evidence)
    print(
        json.dumps(
            {"instrument": judged, "readback": evidence["readback"], "routes": evidence["routes"]},
            indent=1,
        )
    )
    return 0 if judged["valid"] else 1


def _collect_live_evidence(args: argparse.Namespace) -> dict[str, Any]:
    """One cell from the pipeline, the engine log, and the OS. Missing sources stay missing."""
    claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    log_path = Path(args.log)
    offset = log_path.stat().st_size if log_path.is_file() else 0
    swap_before = _swap_used_mb()
    routes, texts, samples = _pipeline_pair(args)
    appended = _appended_log(log_path, offset)
    engine_models = _models_in_window(args.engine, appended)
    for route, model in zip(routes, engine_models, strict=False):
        route["engine_model"] = model
    memory = _memory_evidence(args, Path(args.vm_before))
    local = count_tokens(texts[0], Path(args.tokenizer)) if texts else None
    swap_after = _swap_used_mb()
    root = memory.pop("root")
    return {
        "engine": args.engine,
        "mode": args.mode,
        "claimed": claims,
        "readback": _live_readback(args, appended),
        "expected_model": args.model,
        "expected_workspace": args.workspace,
        "expected_backend": args.backend_id,
        "routes": routes,
        "engine_models": engine_models,
        "memory": memory,
        "tokens": {
            "engine_completion": samples[0][0] if samples else None,
            "tokenizer_completion": local,
        },
        "noise": _pair_noise(samples),
        "template": {"same_checkpoint": False},
        # A non-empty reply is not a preflight. The harness preflight row is the source.
        "preflight_verdict": None,
        "swap_samples_mb": [swap_before, swap_after]
        if swap_before is not None and swap_after is not None
        else [],
        "max_swap_growth_mb": 2048,
        "max_start_swap_used_mb": 4096,
        "served_model_id": _served_model_id(args.engine_base, args.model),
        "launch_argv": _process_argv(root),
    }


def _pipeline_pair(
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], list[str], list[tuple[int | None, float]]]:
    import os

    headers = {"Content-Type": "application/json"}
    key = os.environ.get("PIPELINE_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    routes: list[dict[str, Any]] = []
    texts: list[str] = []
    samples: list[tuple[int | None, float]] = []
    url = f"{args.pipeline.rstrip('/')}/v1/chat/completions"
    body = {
        "model": args.workspace,
        "messages": [{"role": "user", "content": args.prompt}],
        "temperature": 0,
        "max_tokens": 32,
        "stream": False,
    }
    for _ in range(2):
        started = time.monotonic()
        sent = _http_json(url, body, headers, 600)
        elapsed = time.monotonic() - started
        header = (
            sent["headers"].get("x-portal-route") or sent["headers"].get("X-Portal-Route") or ""
        )
        message = (sent["json"].get("choices") or [{}])[0].get("message") or {}
        texts.append(message.get("content") or "")
        usage = sent["json"].get("usage") or {}
        tokens = usage.get("completion_tokens")
        samples.append((tokens if isinstance(tokens, int) else None, elapsed))
        routes.append({"header": header, "engine_model": None})
    return routes, texts, samples


def _appended_log(log_path: Path, offset: int) -> str:
    if not log_path.is_file():
        return ""
    with log_path.open("rb") as handle:
        handle.seek(offset)
        return handle.read().decode("utf-8", "replace")


def _memory_evidence(args: argparse.Namespace, vm_before: Path) -> dict[str, Any]:
    try:
        before = parse_vm_stat(vm_before.read_text(encoding="utf-8"))
        after = parse_vm_stat(subprocess.check_output(["vm_stat"], text=True, timeout=10))
        deltas = vm_deltas_gb(before, after) or {}
        rows = parse_ps_tree(
            subprocess.check_output(["ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=10)
        )
    except (OSError, subprocess.CalledProcessError):
        deltas = {}
        rows = []
    root = _root_pid(args.engine)
    rss = tree_rss_gb(rows, root) if root else None
    metal = _metal_gb(rows, root) if root else None
    return {
        "tree_walked": root is not None and rss is not None,
        "tree_rss_gb": rss,
        "metal_wired_gb": metal,
        "root": root,
        **deltas,
    }


def _live_readback(args: argparse.Namespace, appended: str) -> dict[str, Any]:
    log_path = Path(args.log)
    full = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    window = full[-2_000_000:] + "\n" + appended
    if args.engine == "omlx":
        settings = parse_omlx_settings(window).get(args.model, {})
        readback: dict[str, Any] = {}
        if "mtp_enabled" in settings:
            readback["mtp_enabled"] = bool(settings["mtp_enabled"])
            readback["spec_method"] = "mtp" if settings["mtp_enabled"] else "off"
        if "dflash_enabled" in settings:
            readback["dflash_enabled"] = bool(settings["dflash_enabled"])
            readback["drafter_loaded"] = bool(settings["dflash_enabled"])
        if "temperature" in settings:
            readback["temperature"] = settings["temperature"]
        if "enable_thinking" in settings:
            readback["thinking"] = bool(settings["enable_thinking"])
        acceptance = parse_omlx_acceptance(appended)
        if acceptance is not None:
            readback["acceptance"] = acceptance
        return readback
    bound = parse_ollama_load(window).get(args.model, {})
    readback = {}
    if "context_tokens" in bound:
        readback["context_tokens"] = bound["context_tokens"]
    if "parallel_slots" in bound:
        readback["parallel_slots"] = bound["parallel_slots"]
    # A template line "thinking = 0" is init text, not this request's think flag.
    return readback


def _root_pid(engine: str) -> int | None:
    name = "omlx-server" if engine == "omlx" else "ollama"
    try:
        text = subprocess.check_output(["pgrep", "-x", name], text=True, timeout=10).split()
    except (subprocess.CalledProcessError, OSError):
        return None
    return int(text[0]) if text else None


def _metal_gb(rows: list[tuple[int, int, int]], root: int) -> float | None:
    by_parent: dict[int, list[int]] = {}
    for pid, ppid, _rss in rows:
        by_parent.setdefault(ppid, []).append(pid)
    seen = {root}
    stack = [root]
    while stack:
        pid = stack.pop()
        for child in by_parent.get(pid, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    total = 0.0
    found = False
    for pid in seen:
        text = subprocess.run(
            ["footprint", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
        wired = parse_metal_wired_gb(text)
        if wired is not None:
            total += wired
            found = True
    return total if found else None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"self-test", "judge", "prove"}:
        print(
            "usage: engine_eval_instrument.py self-test | judge --evidence FILE | prove ...",
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
    return prove(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
