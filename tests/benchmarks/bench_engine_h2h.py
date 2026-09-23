#!/usr/bin/env python3
"""Engine × model head-to-head: Ollama vs oMLX vs mlx-serve vs Rapid-MLX vs
vllm-mlx vs mlx_lm.server, on MiMo-V2.6-Distill-9B, Laguna-XS.2 and VulnLLM-R-7B.

Governing doc: docs/MIMO_V26_DISTILL_9B_BRINGUP_V1.md ("Head-to-head test plan
V2"). Registry: tests/benchmarks/engine_h2h.yaml. This harness is the speed +
security lane; the agentic coding lane is WFE (tests/wfe/plans/mimo_h2h_*.yaml,
with WFE_ENGINE / WFE_CHAT_BASE_URL for the MLX engines).

RULES THE HARNESS ENFORCES (doc "Rules (all runs)"):
  1. One request in flight, ever — every call is sequential, and a lock file
     refuses a second harness process.
  3. Refuses to start a measurement when swap is already too full.
  4. Samples swap + Ollama CPU split during every measurement; a row whose swap
     grew past the ceiling, or whose Ollama model spilled to CPU, is INVALID.
And: one engine holds a given model at a time (`switch` evicts it from Ollama,
restarts oMLX clean, and stops any managed engine before starting the next).

Typical sequence for one model on one engine (see the doc for the full order):

  H=tests/benchmarks/bench_engine_h2h.py
  uv run python $H doctor                                  # tools, dirs, swap baseline
  uv run python $H fetch-drafters                          # one-time
  uv run python $H build-prefill                           # one-time, fixed prompt files
  uv run python $H switch --engine rapid-mlx --model mimo --mode plain
  uv run python $H preflight --engine rapid-mlx --model mimo
  uv run python $H sanity --engine prismml-llama --model bonsai_v1_8b
  uv run python $H speed --engine rapid-mlx --model mimo --mode plain
  uv run python $H security --engine rapid-mlx --model mimo --repeats 3
  uv run python $H stop --engine rapid-mlx
  uv run python $H summarize

Results: tests/benchmarks/results/engine_h2h/<model>.jsonl (append-only rows).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).parent / "engine_h2h.yaml"
FIXTURES = Path(__file__).parent / "fixtures" / "engine_h2h"
QUALITY_FIXTURE = Path(__file__).parent / "fixtures" / "bonsai_quality" / "quality.json"
RESULTS = Path(__file__).parent / "results" / "engine_h2h"
STATE_DIR = RESULTS / "state"
LOCK_FILE = Path("/tmp/portal5_engine_h2h.lock")

#: V1 engine-bench decode prompt (docs/MLX_SERVE_ENGINE_BENCH_V1.md), reused so
#: numbers line up with the splash and mlx-serve records.
DECODE_PROMPT = (
    "Write a detailed 400-word explanation of how TCP congestion control works, "
    "covering slow start, congestion avoidance, fast retransmit and fast recovery."
)
#: Repo files concatenated into the prefill prompt: real code, in a fixed order,
#: so every engine prefills byte-identical text.
PREFILL_SOURCES = [
    "tests/wfe/runner.py",
    "tests/wfe/campaign.py",
    "tests/benchmarks/bench_engine_concurrency.py",
    "portal/platform/inference/cluster_backends.py",
]
#: Rough chars-per-token for sizing only; the recorded number is the engine's own
#: prompt_tokens.
CHARS_PER_TOKEN = 3.6


# ── config ─────────────────────────────────────────────────────────────────


def load_config(path: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(path.read_text())
    cfg["mlx_root"] = os.path.expanduser(cfg["mlx_root"])
    cfg["drafter_root"] = os.path.expanduser(cfg["drafter_root"])
    for engine in cfg["engines"].values():
        if engine.get("server_path"):
            engine["server_path"] = os.path.expanduser(engine["server_path"])
    return cfg


def per_engine(value, engine: str):
    """A model field may be a scalar or an {engine: value, default: value} map."""
    if isinstance(value, dict):
        return value.get(engine, value.get("default"))
    return value


def spec_entry(cfg: dict, model: str, engine: str) -> dict | None:
    return (cfg["models"][model].get("spec") or {}).get(engine)


def local_dir_for(cfg: dict, repo: str | None) -> str | None:
    """Where fetch-drafters puts an HF repo: drafter_root/<repo basename>."""
    return f"{cfg['drafter_root']}/{repo.split('/')[-1]}" if repo else None


def model_dir_for(cfg: dict, model: str, engine: str, mode: str) -> str:
    m = cfg["models"][model]
    if engine == "prismml-mlx":
        return m["prismml_mlx"]
    if mode == "spec":
        s = spec_entry(cfg, model, engine) or {}
        return s.get("model_dir") or m["mlx"]
    return m["mlx"]


def model_supports_engine(cfg: dict, model: str, engine: str) -> bool:
    """Whether the registry provides the artifact this engine consumes."""
    requires = cfg["engines"][engine].get("requires")
    if requires:
        return bool(cfg["models"][model].get(requires))
    return True


def cached_hf_file(gguf: dict | None, label: str) -> str:
    """Resolve a registered Hugging Face file from the local cache only."""
    if not gguf:
        raise SystemExit(f"{label} has no file artifact in the registry")
    from huggingface_hub import try_to_load_from_cache

    path = try_to_load_from_cache(gguf["repo"], gguf["file"])
    if not isinstance(path, str):
        raise SystemExit(f"file is not cached: hf download {gguf['repo']} {gguf['file']}")
    return path


def gguf_path_for(cfg: dict, model: str) -> str:
    """Resolve one registered model GGUF from the local HF cache only."""
    return cached_hf_file(cfg["models"][model].get("gguf"), model)


def render_one(part, values: dict) -> str:
    """Replace only known `{name}` placeholders — spec args carry JSON braces."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), str(part))


def render(template: list[str], values: dict) -> list[str]:
    """Render argv parts, splicing a list-valued `{spec_args}` placeholder."""
    argv: list[str] = []
    for part in template:
        if part == "{spec_args}":
            argv.extend(render_one(arg, values) for arg in (values.get("spec_args") or []))
        else:
            argv.append(render_one(part, values))
    return argv


def launch_command(cfg: dict, engine: str, model: str, mode: str) -> tuple[list[str], str | None]:
    """The exact argv (and cwd) for a managed engine. Raises on a null spec cell."""
    e = cfg["engines"][engine]
    m = cfg["models"][model]
    if not model_supports_engine(cfg, model, engine):
        raise SystemExit(f"no {e.get('requires')} artifact for {engine} × {model}")
    model_dir = model if e.get("requires") == "gguf" else model_dir_for(cfg, model, engine, mode)
    spec = spec_entry(cfg, model, engine) if mode == "spec" else None
    values = {
        "mlx_root": cfg["mlx_root"],
        "model_dir": model_dir,
        "served": model_dir,
        "port": e.get("port", ""),
        "ctx": m["ctx"],
        "tool_parser": per_engine(m.get("tool_parser"), engine) or "auto",
        "drafter_path": local_dir_for(cfg, m.get("drafter")) or "",
        "draft_path": local_dir_for(cfg, m.get("draft_model")) or "",
        "gguf_path": gguf_path_for(cfg, model) if e.get("requires") == "gguf" else "",
        "draft_gguf_path": cached_hf_file(m.get("draft_gguf"), f"{model} drafter")
        if mode == "spec" and m.get("draft_gguf")
        else "",
        "llama_server": e.get("server_path", ""),
        "mlx_server_script": str(REPO / e["server_script"]) if e.get("server_script") else "",
        "python": str(Path.home() / "src/prismml-mlx/.venv/bin/python"),
        "spec_args": (spec or {}).get("args") or [],
    }
    if mode == "plain":
        argv = render(e["plain"], values)
    else:
        if spec is None:
            raise SystemExit(f"no spec path for {engine} × {model} (registry cell is null)")
        if "{spec_args}" in e["base_spec"]:
            argv = render(e["base_spec"], values)
        else:
            argv = render(e["base_spec"], values) + render(spec.get("args") or [], values)
    cwd = render_one(e["cwd"], values) if e.get("cwd") else None
    return argv, cwd


def base_url(cfg: dict, engine: str) -> str:
    e = cfg["engines"][engine]
    return e.get("base") or f"http://127.0.0.1:{e['port']}"


def served_id(cfg: dict, engine: str, model: str, mode: str) -> str:
    """The `model` field requests must carry. Ollama: its tag. Everything MLX:
    the directory name (managed engines get --served-model-name / a relative
    --model so the id is identical across engines)."""
    if engine == "ollama":
        return cfg["models"][model]["ollama"]
    if cfg["engines"][engine].get("requires") == "gguf":
        return model
    return model_dir_for(cfg, model, engine, mode)


def think_off_fields(engine: str) -> dict:
    """Thinking OFF in each engine's dialect (same intent everywhere).

    Keep Ollama's `think` switch required by this probe and its OpenAI-compatible
    `reasoning_effort` spelling for the other harness users. MLX engines take
    the chat template's own switch."""
    if engine == "ollama":
        return {"think": False, "reasoning_effort": "none"}
    return {"chat_template_kwargs": {"enable_thinking": False}}


def sampling_for(cfg: dict, model: str, thinking: bool = False) -> dict:
    key = "thinking_sampling" if thinking else "sampling"
    return dict(cfg["models"][model].get(key) or {})


# ── host probes ────────────────────────────────────────────────────────────


def _run(argv: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def parse_swapusage(text: str) -> dict:
    """`sysctl vm.swapusage` → {total_mb, used_mb}."""
    out = {}
    for key in ("total", "used"):
        m = re.search(rf"{key} = ([\d.]+)M", text)
        if m:
            out[f"{key}_mb"] = float(m.group(1))
    return out


def swap_now() -> dict:
    return parse_swapusage(_run(["sysctl", "vm.swapusage"]))


def parse_footprint(text: str) -> float | None:
    """`footprint -p PID` header line → GB."""
    m = re.search(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", text)
    if not m:
        return None
    return round(float(m.group(1)) / {"KB": 1024**2, "MB": 1024, "GB": 1}[m.group(2)], 2)


def pid_on_port(port: int) -> int | None:
    out = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"]).split()
    return int(out[0]) if out else None


def http_json(url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ollama_ps(cfg: dict) -> list[dict]:
    try:
        return http_json(f"{base_url(cfg, 'ollama')}/api/ps", timeout=10).get("models") or []
    except Exception:
        return []


def resident_gb(cfg: dict, engine: str, model: str) -> float | None:
    if engine == "ollama":
        tag = cfg["models"][model]["ollama"]
        for m in ollama_ps(cfg):
            if m.get("name") == tag:
                return round(m.get("size", 0) / 1024**3, 2)
        return None
    e = cfg["engines"][engine]
    if engine == "omlx":
        pid = _run(["pgrep", "-x", e["process_name"]]).split()
        pid = int(pid[0]) if pid else None
    else:
        pid = pid_on_port(e["port"])
    return parse_footprint(_run(["footprint", "-p", str(pid)], timeout=60)) if pid else None


# ── guard (rules 3 + 4) ────────────────────────────────────────────────────


class Guard:
    """Samples swap and (for Ollama) CPU split while a measurement runs."""

    def __init__(self, cfg: dict, engine: str, model: str):
        self.g = cfg["guard"]
        self.cfg, self.engine, self.model = cfg, engine, model
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _sample(self) -> dict:
        s = {"t": round(time.time(), 1), **swap_now()}
        if self.engine == "ollama":
            tag = self.cfg["models"][self.model]["ollama"]
            for m in ollama_ps(self.cfg):
                if m.get("name") == tag and m.get("size"):
                    s["gpu_fraction"] = round(m.get("size_vram", 0) / m["size"], 3)
        return s

    def _loop(self) -> None:
        while not self._stop.wait(self.g["sample_s"]):
            self.samples.append(self._sample())

    def __enter__(self) -> Guard:
        self.samples.append(self._sample())
        self._t.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._t.join(timeout=5)
        self.samples.append(self._sample())

    def verdict(self) -> dict:
        return guard_verdict(self.samples, self.g["max_swap_growth_mb"])


def guard_verdict(samples: list[dict], max_growth_mb: float) -> dict:
    used = [s["used_mb"] for s in samples if "used_mb" in s]
    growth = round(max(used) - used[0], 1) if used else None
    reasons = []
    if growth is not None and growth > max_growth_mb:
        reasons.append(f"swap grew {growth}MB (> {max_growth_mb}MB)")
    split = [s["gpu_fraction"] for s in samples if s.get("gpu_fraction", 1.0) < 1.0]
    if split:
        reasons.append(f"Ollama CPU split (gpu fraction {min(split)})")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "swap_start_mb": used[0] if used else None,
        "swap_growth_mb": growth,
        "samples": len(samples),
    }


def start_gate_verdict(swap: dict, max_used_mb: float) -> tuple[bool, str]:
    """Rule 3 on the absolute amount swapped: macOS sizes the swap total to fit usage."""
    if "used_mb" not in swap:
        return True, "swap: unreadable"
    msg = f"swap used {swap['used_mb']:.0f}MB of {swap.get('total_mb', 0):.0f}MB allocated"
    return swap["used_mb"] <= max_used_mb, msg


def start_gate(cfg: dict) -> tuple[bool, str]:
    return start_gate_verdict(swap_now(), cfg["guard"]["max_start_swap_used_mb"])


@contextlib.contextmanager
def single_flight():
    """Rule 1 across processes: a second harness run fails fast."""
    LOCK_FILE.touch(exist_ok=True)
    with LOCK_FILE.open("w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another bench_engine_h2h run holds the lock — rule 1") from None
        yield


# ── engine lifecycle ───────────────────────────────────────────────────────


def _state_file(engine: str) -> Path:
    return STATE_DIR / f"{engine}.json"


def wait_ready(url: str, timeout_s: float, process: subprocess.Popen | None = None) -> float:
    """Poll /v1/models until ready or fail promptly if its managed child exits."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        with contextlib.suppress(Exception):
            http_json(f"{url}/v1/models", timeout=3)
            return round(time.monotonic() - t0, 2)
        if process is not None:
            exit_code = process.poll()
            if exit_code is not None:
                raise SystemExit(
                    f"engine process exited during startup (exit {exit_code}) — see its log"
                )
        time.sleep(1)
    raise SystemExit(f"{url} not ready after {timeout_s}s")


def start_managed(cfg: dict, engine: str, model: str, mode: str) -> dict:
    argv, cwd = launch_command(cfg, engine, model, mode)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = RESULTS / "logs" / f"{engine}__{model}__{mode}__{_stamp()}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DO_NOT_TRACK": "1", "RAPID_MLX_TELEMETRY": "0"}
    with log.open("w") as fh:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, env=env, start_new_session=True
        )
    ready_s = wait_ready(base_url(cfg, engine), 900, proc)
    st = {
        "engine": engine,
        "model": model,
        "mode": mode,
        "control_model": cfg["models"][model].get("control"),
        "pid": proc.pid,
        "argv": argv,
        "log": str(log),
        "ready_s": ready_s,
        "started": _stamp(),
    }
    _state_file(engine).write_text(json.dumps(st, indent=1))
    return st


def stop_managed(cfg: dict, engine: str) -> None:
    sf = _state_file(engine)
    if not sf.exists():
        return
    pid = json.loads(sf.read_text())["pid"]
    sig = getattr(signal, "SIG" + cfg["engines"][engine].get("stop_signal", "INT"))
    for s, wait in ((sig, 60), (signal.SIGTERM, 30)):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, s)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                sf.unlink()
                return
            time.sleep(1)
    raise SystemExit(
        f"{engine} (pid {pid}) did not exit on {sig.name} or SIGTERM — investigate, not kill -9"
    )


def ollama_evict(cfg: dict, tag: str | None = None) -> list[str]:
    """keep_alive:0 then wait until /api/ps no longer lists it (all if tag None)."""
    targets = [m["name"] for m in ollama_ps(cfg) if tag is None or m["name"] == tag]
    for t in targets:
        with contextlib.suppress(Exception):
            http_json(f"{base_url(cfg, 'ollama')}/api/generate", {"model": t, "keep_alive": 0}, 60)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and any(m["name"] in targets for m in ollama_ps(cfg)):
        time.sleep(2)
    return targets


def ollama_create_gguf(cfg: dict, model: str) -> str | None:
    """Import one cached GGUF through the documented Ollama Modelfile path."""
    m = cfg["models"][model]
    if not m.get("gguf") or not m.get("ollama"):
        return None
    artifact = gguf_path_for(cfg, model)
    with tempfile.TemporaryDirectory(prefix="bonsai-ollama-") as td:
        build_dir = Path(td)
        (build_dir / "file.gguf").symlink_to(artifact)
        modelfile = build_dir / "Modelfile"
        modelfile.write_text(f"FROM ./file.gguf\nPARAMETER num_ctx {m['ctx']}\n")
        subprocess.run(
            ["ollama", "create", m["ollama"], "-f", str(modelfile)],
            check=True,
            timeout=3600,
        )
    return m["ollama"]


def ollama_create_derived(cfg: dict, model: str) -> str | None:
    """Create the context-sized Ollama control tag from its vendor Q4_K_M tag."""
    m = cfg["models"][model]
    source, target = m.get("ollama_from"), m.get("ollama")
    if not source or not target:
        return None
    content = f"FROM {source}\nPARAMETER num_ctx {m['ctx']}\n"
    with tempfile.NamedTemporaryFile("w", prefix="bonsai-control-", delete=False) as fh:
        fh.write(content)
        path = Path(fh.name)
    try:
        subprocess.run(["ollama", "create", target, "-f", str(path)], check=True, timeout=3600)
    finally:
        path.unlink(missing_ok=True)
    return target


def omlx_apply_settings(cfg: dict, model_id: str, settings: dict | None) -> Path:
    """Set (or clear) the harness-owned spec keys for one oMLX model, backing up
    the settings file once per call. `settings=None` clears them (plain mode)."""
    path = Path(os.path.expanduser(cfg["engines"]["omlx"]["settings_file"]))
    data = json.loads(path.read_text())
    backup = path.with_name(f"{path.name}.h2hbak.{_stamp()}")
    backup.write_text(json.dumps(data, indent=1))
    entry = data.setdefault("models", {}).setdefault(model_id, {})
    for k in ("mtp_enabled", "dflash_enabled", "dflash_draft_model", "dflash_max_ctx"):
        entry.pop(k, None)
    entry.update(settings or {})
    if not entry:
        data["models"].pop(model_id)
    path.write_text(json.dumps(data, indent=2))
    return backup


def omlx_restart(cfg: dict) -> float:
    argv = render(cfg["engines"]["omlx"]["restart"], {"uid": os.getuid()})
    subprocess.run(argv, check=True, timeout=60)
    time.sleep(3)  # the old process must release the port before readiness means anything
    return wait_ready(base_url(cfg, "omlx"), 300)


def switch(cfg: dict, engine: str, model: str, mode: str) -> dict:
    """Make `engine` the ONLY holder of `model` (mode-configured), clean slate."""
    if engine == "ollama" and mode != "plain":
        raise SystemExit("Ollama has no spec mode in this plan")
    for other, e in cfg["engines"].items():
        if e["kind"] == "managed":
            stop_managed(cfg, other)
    # Every Ollama model goes, the router included (the pipeline reloads it on
    # its next request): its memory belongs to the engine under test.
    evicted = ollama_evict(cfg)
    info: dict = {"engine": engine, "model": model, "mode": mode, "ollama_evicted": evicted}
    if engine != "omlx":
        # oMLX holds whatever it last served; a clean restart releases it.
        info["omlx_restart_s"] = omlx_restart(cfg)
    if engine == "ollama":
        imported = ollama_create_gguf(cfg, model)
        derived = ollama_create_derived(cfg, model) if not imported else None
        if imported or derived:
            info["ollama_import"] = imported or derived
        return info
    if engine == "omlx":
        return {**info, **omlx_configure(cfg, model, mode)}
    info["managed"] = start_managed(cfg, engine, model, mode)
    return info


def omlx_settings_for(cfg: dict, model: str, mode: str) -> dict | None:
    """The spec keys oMLX needs for this model, or None for plain."""
    if mode == "plain":
        return None
    s = spec_entry(cfg, model, "omlx")
    if s is None:
        raise SystemExit(f"no oMLX spec path for {model}")
    vals = {"drafter_path": local_dir_for(cfg, cfg["models"][model].get("drafter")) or ""}
    return {k: render_one(v, vals) if isinstance(v, str) else v for k, v in s["settings"].items()}


def omlx_configure(cfg: dict, model: str, mode: str) -> dict:
    settings = omlx_settings_for(cfg, model, mode)
    backup = omlx_apply_settings(cfg, model_dir_for(cfg, model, "omlx", mode), settings)
    return {"settings_backup": str(backup), "omlx_restart_s": omlx_restart(cfg)}


# ── requests ───────────────────────────────────────────────────────────────


def stream_chat(url: str, payload: dict, timeout: float = 1800) -> dict:
    """Stream one completion; return timing + usage. TTFT is to the first token
    of ANY kind (content, reasoning or tool call) — that is when prefill ended."""
    body = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(
        f"{url}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    first = last = None
    usage: dict = {}
    content, chunks = [], 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            ev = json.loads(line[5:])
            usage = ev.get("usage") or usage
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                piece = d.get("content") or d.get("reasoning_content") or d.get("reasoning")
                if piece or d.get("tool_calls"):
                    now = time.monotonic()
                    first = first or now
                    last = now
                    chunks += 1
                    if d.get("content"):
                        content.append(d["content"])
    return timing_row(t0, first, last, usage, chunks, "".join(content))


def timing_row(t0, first, last, usage, chunks, content) -> dict:
    ctoks = usage.get("completion_tokens") or chunks
    ptoks = usage.get("prompt_tokens")
    ttft = round(first - t0, 3) if first else None
    decode_s = (last - first) if (first and last and last > first) else None
    return {
        "ttft_s": ttft,
        "prompt_tokens": ptoks,
        "completion_tokens": ctoks,
        "usage_reported": bool(usage),
        "decode_tps": round((ctoks - 1) / decode_s, 2) if decode_s and ctoks > 1 else None,
        "prefill_tps": round(ptoks / ttft, 1) if (ptoks and ttft) else None,
        "total_s": round((last or time.monotonic()) - t0, 3),
        "content": content,
    }


def chat_once(url: str, payload: dict, timeout: float = 600) -> dict:
    return http_json(f"{url}/v1/chat/completions", {**payload, "stream": False}, timeout)


# ── fixtures ───────────────────────────────────────────────────────────────


def prefill_text(chars: int) -> str:
    parts, total = [], 0
    for rel in PREFILL_SOURCES:
        txt = f"\n\n# ===== {rel} =====\n" + (REPO / rel).read_text()
        parts.append(txt)
        total += len(txt)
        if total >= chars:
            break
    return "".join(parts)[:chars]


def build_prefill(cfg: dict) -> dict:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, m in cfg["models"].items():
        p = FIXTURES / f"prefill_{m['prefill_tokens']}.txt"
        if not p.exists():
            p.write_text(prefill_text(int(m["prefill_tokens"] * CHARS_PER_TOKEN)))
        out[name] = str(p)
    return out


def prefill_prompt(cfg: dict, model: str) -> str:
    p = FIXTURES / f"prefill_{cfg['models'][model]['prefill_tokens']}.txt"
    if not p.exists():
        raise SystemExit("run `build-prefill` first — every engine must prefill the same file")
    return p.read_text()


# ── measurements ───────────────────────────────────────────────────────────


def _payload(cfg, engine, model, mode, messages, max_tokens, *, thinking=False, **extra) -> dict:
    thinking_fields = (
        ({"think": True} if thinking and engine == "ollama" else {})
        if thinking
        else think_off_fields(engine)
    )
    return {
        "model": served_id(cfg, engine, model, mode),
        "messages": messages,
        "max_tokens": max_tokens,
        **thinking_fields,
        **sampling_for(cfg, model, thinking=thinking),
        **extra,
    }


def measure_speed(
    cfg: dict, engine: str, model: str, mode: str, rounds: int, max_tokens: int = 400
) -> dict:
    url = base_url(cfg, engine)
    # First request after `switch`; a managed engine's load time is its launch ready_s.
    ok = [{"role": "user", "content": "Reply with exactly: OK"}]
    res: dict = {"cold": stream_chat(url, _payload(cfg, engine, model, mode, ok, 8))}
    msgs = [{"role": "user", "content": DECODE_PROMPT}]
    res["decode"] = [
        stream_chat(url, _payload(cfg, engine, model, mode, msgs, max_tokens))
        for _ in range(rounds)
    ]
    body = prefill_prompt(cfg, model)
    res["prefill"] = []
    for _ in range(rounds):
        # A fresh nonce FIRST defeats every engine's prefix / SSD / radix cache,
        # so each round measures a real cold prefill of identical length.
        text = f"[run {uuid.uuid4()}]\n{body}\n\nSummarize the code above in one sentence."
        m = [{"role": "user", "content": text}]
        res["prefill"].append(stream_chat(url, _payload(cfg, engine, model, mode, m, 32)))
    for r in [res["cold"], *res["decode"], *res["prefill"]]:
        r.pop("content", None)
    res["resident_gb"] = resident_gb(cfg, engine, model)
    sf = _state_file(engine)
    res["launch_ready_s"] = json.loads(sf.read_text()).get("ready_s") if sf.exists() else None
    return res


def speed_summary(res: dict) -> dict:
    def med(xs):
        xs = sorted(x for x in xs if x is not None)
        return xs[len(xs) // 2] if xs else None

    return {
        "decode_tps_median": med([r["decode_tps"] for r in res["decode"]]),
        "prefill_tps_median": med([r["prefill_tps"] for r in res["prefill"]]),
        "prefill_ttft_median_s": med([r["ttft_s"] for r in res["prefill"]]),
        "prefill_prompt_tokens": med([r["prompt_tokens"] for r in res["prefill"]]),
        "cold_first_request_s": res["cold"]["total_s"],
        "launch_ready_s": res.get("launch_ready_s"),
        "resident_gb": res["resident_gb"],
    }


TOOL_SPEC = [
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


def check_tool_call(resp: dict) -> dict:
    msg = (resp.get("choices") or [{}])[0].get("message") or {}
    calls = msg.get("tool_calls") or []
    if not calls:
        return {"ok": False, "why": "no tool_calls", "content": (msg.get("content") or "")[:200]}
    fn = calls[0].get("function") or {}
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "why": "arguments not JSON", "raw": fn.get("arguments")}
    ok = (
        fn.get("name") == "get_weather" and isinstance(args, dict) and "boston" in str(args).lower()
    )
    return {"ok": ok, "name": fn.get("name"), "arguments": args}


def normalize_template(t: str | None) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def local_template(model_dir: Path) -> str | None:
    j = model_dir / "chat_template.jinja"
    if j.exists():
        return j.read_text()
    tc = model_dir / "tokenizer_config.json"
    if tc.exists():
        return json.loads(tc.read_text()).get("chat_template")
    return None


def source_template(repo: str) -> str | None:
    base = f"https://huggingface.co/{repo}/resolve/main"
    with (
        contextlib.suppress(Exception),
        urllib.request.urlopen(f"{base}/chat_template.jinja", timeout=30) as r,
    ):
        return r.read().decode()
    with (
        contextlib.suppress(Exception),
        urllib.request.urlopen(f"{base}/tokenizer_config.json", timeout=30) as r,
    ):
        return json.load(r).get("chat_template")
    return None


def gguf_chat_template(cfg: dict, model: str) -> str | None:
    """Read tokenizer.chat_template from a cached GGUF metadata header."""
    gguf_root = Path.home() / "src/prismml-llama.cpp/gguf-py"
    if gguf_root.is_dir() and str(gguf_root) not in sys.path:
        sys.path.insert(0, str(gguf_root))
    try:
        from gguf.gguf_reader import GGUFReader

        field = GGUFReader(gguf_path_for(cfg, model)).fields.get("tokenizer.chat_template")
    except Exception:
        return None
    if field is None:
        return None
    part = field.parts[field.data[0]] if len(field.data) else field.parts[-1]
    if hasattr(part, "tobytes"):
        raw = part.tobytes()
    elif isinstance(part, bytes):
        raw = part
    else:
        raw = str(part).encode()
    return raw.decode("utf-8", "replace").rstrip("\x00")


def template_check(cfg: dict, engine: str, model: str, mode: str) -> dict:
    if engine == "ollama":
        return {
            "ok": None,
            "note": "Ollama translates the source template to Go; check its off-mode and tool probes",
        }
    if cfg["engines"][engine].get("requires") == "gguf":
        local = gguf_chat_template(cfg, model)
        entry = cfg["models"][model]
        template_repo = entry.get("template_repo") or entry.get("base_repo") or entry["source_repo"]
        source = source_template(template_repo)
        if local is None or source is None:
            return {"ok": None, "note": "embedded or source template unavailable; compare by hand"}
        same = normalize_template(local) == normalize_template(source)
        return {
            "ok": same,
            "note": "" if same else "embedded GGUF template differs from the source template",
        }
    d = Path(cfg["mlx_root"]) / model_dir_for(cfg, model, engine, mode)
    entry = cfg["models"][model]
    template_repo = entry.get("template_repo") or entry.get("base_repo") or entry["source_repo"]
    local, src = local_template(d), source_template(template_repo)
    if src is None:
        return {"ok": None, "note": "source template unreachable — diff by hand"}
    same = normalize_template(local) == normalize_template(src)
    return {
        "ok": same,
        "local_dir": str(d),
        "note": "" if same else "DIFFERS from source — numbers invalid until reconciled",
    }


def preflight(cfg: dict, engine: str, model: str, mode: str) -> dict:
    url = base_url(cfg, engine)
    out: dict = {"served_id": served_id(cfg, engine, model, mode)}
    ids: list[str] = []
    with contextlib.suppress(Exception):
        ids = [m["id"] for m in http_json(f"{url}/v1/models", timeout=10).get("data") or []]
    out["listed"] = (
        None if cfg["engines"][engine].get("list_models_is_cache") else out["served_id"] in ids
    )
    ok_msgs = [{"role": "user", "content": "Reply with exactly: OK"}]
    try:
        r = chat_once(url, _payload(cfg, engine, model, mode, ok_msgs, 32, temperature=0))
        out["think_off_reply"] = ((r["choices"][0]["message"].get("content")) or "").strip()[:80]
    except Exception as e:
        out["think_off_reply"] = f"ERROR {e}"
    tool_msgs = [{"role": "user", "content": "What is the weather in Boston? Use the tool."}]
    try:
        r = chat_once(
            url, _payload(cfg, engine, model, mode, tool_msgs, 512, temperature=0, tools=TOOL_SPEC)
        )
        out["tool_call"] = check_tool_call(r)
    except Exception as e:
        out["tool_call"] = {"ok": False, "why": f"ERROR {e}"}
    out["template"] = template_check(cfg, engine, model, mode)
    template_ready = out["template"]["ok"] is True or (
        engine == "ollama" and out["template"]["ok"] is None
    )
    out["verdict"] = (
        "OK"
        if out["listed"] is not False
        and out["think_off_reply"].upper().startswith("OK")
        and "<think>" not in out["think_off_reply"].lower()
        and out["tool_call"]["ok"]
        and template_ready
        else "REVIEW"
    )
    return out


def score_compatibility_sanity(prompt_id: str, response: str) -> dict:
    text = response.strip()
    mojibake = ("\ufffd", "Ã", "Â", "â€", "ï¿", "ðŸ")
    clean = (
        bool(text)
        and not any(marker in text for marker in mojibake)
        and not any(ord(char) < 32 and char not in "\t\n\r" for char in text)
        and not re.search(r"(.)\1{7,}", text)
        and not re.search(r"\b(\w+)(?:\W+\1){3,}\b", text, re.I)
    )
    if prompt_id == "france":
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s]
        checks = {
            "nonempty_clean": clean,
            "mentions_paris": "paris" in text.lower(),
            "one_sentence": len(sentences) == 1,
        }
    elif prompt_id == "sort":
        expected = [1, 3, 7, 11, 19, 23, 42, 56, 70, 88]
        actual = [int(value) for value in re.findall(r"\d+", text)]
        checks = {"nonempty_clean": clean, "sorted_exactly": actual == expected}
    else:
        raise ValueError(f"unknown compatibility prompt: {prompt_id}")
    return {"status": "OK" if all(checks.values()) else "GARBAGE", "checks": checks}


def run_compatibility_sanity(cfg: dict, engine: str, model: str, mode: str) -> dict:
    import statistics

    prompts = {
        "france": "Capital of France? One sentence.",
        "sort": "Sort: 42 7 19 3 88 1 56 23 11 70",
    }
    outputs = []
    for prompt_id, prompt in prompts.items():
        payload = _payload(
            cfg,
            engine,
            model,
            mode,
            [{"role": "user", "content": prompt}],
            64,
        )
        try:
            timing = stream_chat(base_url(cfg, engine), payload, timeout=600)
            response = timing.pop("content")
            check = score_compatibility_sanity(prompt_id, response)
            outputs.append(
                {
                    "prompt_id": prompt_id,
                    "prompt": prompt,
                    "response": response,
                    **check,
                    "timing": timing,
                }
            )
        except Exception as exc:
            outputs.append(
                {"prompt_id": prompt_id, "prompt": prompt, "status": "REJECT", "error": str(exc)}
            )
    statuses = {output["status"] for output in outputs}
    verdict = "REJECT" if "REJECT" in statuses else "OK" if statuses == {"OK"} else "GARBAGE"
    rates = [o["timing"].get("decode_tps") for o in outputs if o.get("timing")]
    rates = [rate for rate in rates if rate is not None]
    return {
        "verdict": verdict,
        "tg_tps_median": statistics.median(rates) if rates else None,
        "outputs": outputs,
    }


# ── security lane ──────────────────────────────────────────────────────────

CWE_RE = re.compile(r"CWE[-\s]?(\d{1,4})", re.I)
NO_VULN_RE = re.compile(r"NO VULNERABILITY FOUND", re.I)


def score_security(expected_cwe: str | None, content: str) -> dict:
    """Automatic half of the score. CVSS band and mitigation quality are left for
    the operator (cvss_ok / mitigation_ok stay null) — a regex cannot judge them."""
    cwes = sorted({f"CWE-{int(n)}" for n in CWE_RE.findall(content or "")})
    if expected_cwe is None:
        clean_ok = bool(NO_VULN_RE.search(content or "")) and not cwes
        return {"cwes": cwes, "cwe_ok": clean_ok, "false_positive": not clean_ok}
    return {"cwes": cwes, "cwe_ok": expected_cwe in cwes, "false_positive": False}


def security_context() -> dict:
    """auto-security's own system prompt + sampling from config/portal.yaml. The
    WFE persona resolver picks `adversarysimulator` for this workspace, which is
    the wrong framing for CWE review, so the workspace prompt is used directly."""
    sys.path.insert(0, str(REPO))
    from tests.wfe.runner import workspace_context

    wsc = workspace_context("auto-security")
    ws = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]["auto-security"]
    return {"system_prompt": ws["owui_system_prompt"], "sampling": wsc["sampling"]}


def run_security(cfg: dict, engine: str, model: str, mode: str, repeats: int) -> list[dict]:
    fx = json.loads((FIXTURES / "security_prompts.json").read_text())
    ctx = security_context()
    samp = {k: ctx["sampling"][k] for k in ("temperature", "top_p") if k in ctx["sampling"]}
    url = base_url(cfg, engine)
    rows = []
    for p in fx["prompts"]:  # all prompts on this model, never interleaved with another
        for rep in range(repeats):
            msgs = [
                {"role": "system", "content": ctx["system_prompt"]},
                {"role": "user", "content": f"{fx['instruction']}\n\n```python\n{p['code']}```"},
            ]
            r = stream_chat(
                url, _payload(cfg, engine, model, mode, msgs, 2048, seed=1000 + rep, **samp)
            )
            content = r.pop("content")
            rows.append(
                {
                    "prompt_id": p["id"],
                    "repeat": rep,
                    "expected_cwe": p["expected_cwe"],
                    **score_security(p["expected_cwe"], content),
                    "cvss_ok": None,
                    "mitigation_ok": None,
                    "timing": r,
                    "response": content,
                }
            )
    return rows


def security_summary(rows: list[dict]) -> dict:
    vuln = [r for r in rows if r["expected_cwe"]]
    clean = [r for r in rows if not r["expected_cwe"]]
    return {
        "cwe_accuracy": round(sum(r["cwe_ok"] for r in vuln) / len(vuln), 3) if vuln else None,
        "clean_false_positives": sum(r["false_positive"] for r in clean),
        "clean_runs": len(clean),
    }


def _quality_lib():
    from tests.benchmarks.capability_lib import (
        extract_code_block,
        extract_final_answer,
        run_python_against_tests,
    )

    return extract_code_block, extract_final_answer, run_python_against_tests


def _normalized_answer(text: str) -> str:
    _, extract_final_answer, _ = _quality_lib()
    body = extract_final_answer(text)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    answer = lines[-1] if lines else body.strip()
    answer = re.sub(r"^(?:final answer|answer|result)\s*:\s*", "", answer, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", answer.lower())


def _score_exact(item: dict, response: str) -> dict:
    expected = re.sub(r"[^a-z0-9]+", "", item["expected"].lower())
    actual = _normalized_answer(response)
    ok = actual.endswith(expected)
    return {"score": float(ok), "ok": ok, "actual": actual[-120:]}


def _score_python(item: dict, response: str) -> dict:
    extract_code_block, _, run_python_against_tests = _quality_lib()
    source = extract_code_block(response, "python")
    if not source:
        return {"score": 0.0, "ok": False, "why": "no Python block"}
    passed, output = run_python_against_tests(source, item["test_source"], timeout=20)
    return {"score": float(passed), "ok": passed, "output": output[-500:]}


def _score_instruction(item: dict, response: str) -> dict:
    _, extract_final_answer, _ = _quality_lib()
    body = extract_final_answer(response).strip()
    checks = item["checks"]
    details: dict[str, bool] = {}
    if "json" in checks:
        candidate = body
        fenced = re.search(r"```(?:json)?\s*(.*?)```", body, re.S | re.I)
        if fenced:
            candidate = fenced.group(1).strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            value = None
        expected_type = checks["json"].get("type", "object")
        details["json"] = (
            isinstance(value, dict)
            if expected_type == "object"
            else isinstance(value, list)
            if expected_type == "array"
            else False
        )
        for key, expected in checks["json"].get("equals", {}).items():
            details[f"json.{key}"] = isinstance(value, dict) and value.get(key) == expected
        if "array_length" in checks["json"]:
            details["json.array_length"] = (
                isinstance(value, list) and len(value) == checks["json"]["array_length"]
            )
        if "array_members" in checks["json"]:
            details["json.array_members"] = (
                isinstance(value, list) and value == checks["json"]["array_members"]
            )
    if "line_count" in checks:
        details["line_count"] = (
            sum(bool(line.strip()) for line in body.splitlines()) == checks["line_count"]
        )
    if "line_prefix" in checks:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        details["line_prefix"] = bool(lines) and all(
            line.startswith(checks["line_prefix"]) for line in lines
        )
    details.update(
        {
            key: expected.lower() in body.lower()
            for key, expected in checks.items()
            if key == "contains" or key.startswith("contains_")
        }
    )
    if "ends_with" in checks:
        details["ends_with"] = body.endswith(checks["ends_with"])
    if "word_count_max" in checks:
        details["word_count_max"] = len(body.split()) <= checks["word_count_max"]
    if "starts_with" in checks:
        details["starts_with"] = body.startswith(checks["starts_with"])
    return {
        "score": sum(details.values()) / len(details) if details else 0.0,
        "ok": bool(details) and all(details.values()),
        "checks": details,
    }


def _score_summary(item: dict, response: str) -> dict:
    _, extract_final_answer, _ = _quality_lib()
    body = re.sub(r"\s+", " ", extract_final_answer(response)).lower()
    found = {term: term.lower() in body for term in item["required_terms"]}
    return {"score": sum(found.values()) / len(found), "ok": all(found.values()), "terms": found}


def score_quality(item: dict, response: str) -> dict:
    """Score one frozen Bonsai item with deterministic capability checks."""
    category = item["category"]
    scorer = {
        "arithmetic": _score_exact,
        "logic": _score_exact,
        "factual": _score_exact,
        "long_context": _score_exact,
        "python": _score_python,
        "instruction": _score_instruction,
        "summary": _score_summary,
    }.get(category)
    if scorer is None:
        raise ValueError(f"unknown quality category: {category}")
    return scorer(item, response)


def quality_summary(rows: list[dict]) -> dict:
    import statistics

    by_mode: dict[str, dict] = {}
    for thinking in (False, True):
        mode_rows = [row for row in rows if row["thinking"] is thinking]
        categories = sorted({row["category"] for row in mode_rows})
        category_scores = {
            category: [row["score"] for row in mode_rows if row["category"] == category]
            for category in categories
        }
        means = {
            category: round(statistics.fmean(values), 4)
            for category, values in category_scores.items()
        }
        spreads = {
            category: round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0
            for category, values in category_scores.items()
        }
        scores = [row["score"] for row in mode_rows]
        by_mode["thinking_on" if thinking else "thinking_off"] = {
            "mean": round(statistics.fmean(scores), 4) if scores else None,
            "spread": round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
            "categories": means,
            "category_spread": spreads,
            "items": len(scores),
        }
    return by_mode


def quality_items(cfg: dict, model: str, fixture: dict) -> list[dict]:
    entry = cfg["models"][model]
    is_27b = any(
        "27b" in str(value).lower()
        for value in (model, entry.get("base_repo"), entry.get("source_repo"))
    )
    return [item for item in fixture["items"] if item["category"] != "long_context" or is_27b]


def run_quality(cfg: dict, engine: str, model: str, mode: str, repeats: int) -> dict:
    fixture = json.loads(QUALITY_FIXTURE.read_text())
    items = quality_items(cfg, model, fixture)
    rows = []
    for thinking in (False, True):
        for ix, item in enumerate(items):
            if item["category"] == "long_context":
                prompt = fixture["long_context"] + "\n\n" + item["question"]
            else:
                prompt = item["prompt"]
            for repeat in range(repeats):
                max_tokens = 8192 if thinking else int(item.get("max_tokens", 512))
                payload = _payload(
                    cfg,
                    engine,
                    model,
                    mode,
                    [{"role": "user", "content": prompt}],
                    max_tokens,
                    thinking=thinking,
                    seed=910000 + ix * 100 + repeat + int(thinking) * 10000,
                )
                timing = stream_chat(base_url(cfg, engine), payload, timeout=1800)
                response = timing.pop("content")
                score = score_quality(item, response)
                rows.append(
                    {
                        "item_id": item["id"],
                        "category": item["category"],
                        "thinking": thinking,
                        "repeat": repeat,
                        "score": score["score"],
                        "score_detail": score,
                        "timing": timing,
                        "response": response,
                    }
                )
    return {"summary": quality_summary(rows), "rows": rows, "fixture": fixture["version"]}


# ── results ────────────────────────────────────────────────────────────────


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def engine_version(engine: str) -> str:
    argv = {
        "ollama": ["ollama", "--version"],
        "omlx": ["omlx", "--version"],
        "mlx-serve": ["mlx-serve", "--version"],
        "rapid-mlx": ["rapid-mlx", "--no-telemetry", "--version"],
        "vllm-mlx": [
            "uvx",
            "--from",
            "vllm-mlx==0.5.0",
            "python",
            "-c",
            "import vllm_mlx;print(vllm_mlx.__version__)",
        ],
        "mlx_lm.server": ["python3", "-c", "import mlx_lm;print(mlx_lm.__version__)"],
        "prismml-llama": [
            str(Path.home() / "src/prismml-llama.cpp/build/bin/llama-server"),
            "--version",
        ],
        "brew-llama": ["/opt/homebrew/bin/llama-server", "--version"],
        "prismml-mlx": [
            str(Path.home() / "src/prismml-mlx/.venv/bin/python"),
            "-c",
            "import mlx_lm;print(mlx_lm.__version__)",
        ],
    }[engine]
    return " ".join(_run(argv, 60).split()[-3:])


def append_row(model: str, row: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{model}.jsonl"
    with p.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return p


def base_row(cfg, kind, engine, model, mode) -> dict:
    sf = _state_file(engine)
    return {
        "kind": kind,
        "at": _stamp(),
        "engine": engine,
        "engine_version": engine_version(engine),
        "model": model,
        "mode": mode,
        "sampling": sampling_for(cfg, model),
        "thinking_sampling": sampling_for(cfg, model, thinking=True),
        "spec_method": (spec_entry(cfg, model, engine) or {}).get("method")
        if mode == "spec"
        else None,
        "served_id": served_id(cfg, engine, model, mode),
        "launch": json.loads(sf.read_text()) if sf.exists() else None,
    }


def load_rows(models: list[str]) -> list[dict]:
    rows = []
    for m in models:
        p = RESULTS / f"{m}.jsonl"
        if p.exists():
            rows += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return rows


def latest(rows: list[dict], kind: str) -> dict:
    """Latest VALID row per (model, engine, mode); falls back to the latest row."""
    out: dict = {}
    for r in rows:
        if r["kind"] != kind:
            continue
        key = (r["model"], r["engine"], r["mode"])
        prev = out.get(key)
        if prev is None or r.get("valid", True) or not prev.get("valid", True):
            out[key] = r
    return out


def fmt(v) -> str:
    return "—" if v is None else str(v)


def summarize(cfg: dict) -> str:
    rows = load_rows(list(cfg["models"]))
    spd, sec, pre = latest(rows, "speed"), latest(rows, "security"), latest(rows, "preflight")
    qual = latest(rows, "quality")
    compat = latest(rows, "compatibility")
    lines = [
        "## Phase 1 compatibility sanity\n",
        "| model | engine | verdict | TG tok/s | valid |",
        "|---|---|---|---:|---|",
    ]
    for (model, engine, mode), row in sorted(compat.items()):
        if mode != "plain":
            continue
        lines.append(
            f"| {model} | {engine} | {row.get('verdict')} | {fmt(row.get('tg_tps_median'))} | "
            f"{'yes' if row.get('valid') else 'INVALID'} |"
        )
    for model in cfg["models"]:
        lines += [
            f"\n### {model}\n",
            "| engine | mode | spec | decode tok/s | prefill tok/s | prefill TTFT s | cold s | resident GB | tool | template | valid | CWE acc | clean FP | quality off/on | % control off/on |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for (m, eng, mode), r in sorted(spd.items()):
            if m != model:
                continue
            s, p, q = r["summary"], pre.get((m, eng, mode), {}), sec.get((m, eng, mode), {})
            ql = qual.get((m, eng, mode), {}).get("summary", {})
            control_id = cfg["models"][m].get("control")
            control_ql = qual.get((control_id, "ollama", "plain"), {}).get("summary", {})
            off = (ql.get("thinking_off") or {}).get("mean")
            on = (ql.get("thinking_on") or {}).get("mean")
            control_off = (control_ql.get("thinking_off") or {}).get("mean")
            control_on = (control_ql.get("thinking_on") or {}).get("mean")
            pct_off = round(100 * off / control_off, 1) if off is not None and control_off else None
            pct_on = round(100 * on / control_on, 1) if on is not None and control_on else None
            lines.append(
                f"| {eng} | {mode} | {fmt(r.get('spec_method'))} | {fmt(s['decode_tps_median'])} | "
                f"{fmt(s['prefill_tps_median'])} | {fmt(s['prefill_ttft_median_s'])} | "
                f"{fmt(s['cold_first_request_s'])} | {fmt(s['resident_gb'])} | "
                f"{fmt((p.get('result') or {}).get('tool_call', {}).get('ok'))} | "
                f"{fmt((p.get('result') or {}).get('template', {}).get('ok'))} | "
                f"{'yes' if r.get('valid') else 'INVALID'} | "
                f"{fmt((q.get('summary') or {}).get('cwe_accuracy'))} | "
                f"{fmt((q.get('summary') or {}).get('clean_false_positives'))} | "
                f"{fmt(off)}/{fmt(on)} | {fmt(pct_off)}/{fmt(pct_on)} |"
            )
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────


def cmd_doctor(cfg: dict) -> int:
    ok = True
    for tool in (
        "ollama",
        "omlx",
        "mlx-serve",
        "rapid-mlx",
        "uvx",
        "mlx_lm.server",
        "footprint",
        "llama-server",
        "lsof",
    ):
        found = _run(["which", tool]).strip()
        print(f"{'OK ' if found else 'MISSING'} {tool} {found}")
        ok &= bool(found)
    prismllama = Path(cfg["engines"]["prismml-llama"]["server_path"])
    print(f"{'OK ' if prismllama.is_file() else 'BLOCKED'} prismml-llama {prismllama}")
    brewllama = Path(cfg["engines"]["brew-llama"]["server_path"])
    print(f"{'OK ' if brewllama.is_file() else 'BLOCKED'} brew-llama {brewllama}")
    mlx_server = REPO / cfg["engines"]["prismml-mlx"]["server_script"]
    print(f"{'OK ' if mlx_server.is_file() else 'MISSING'} prismml-mlx adapter {mlx_server}")
    ok &= mlx_server.is_file()
    mlx_python = Path.home() / "src/prismml-mlx/.venv/bin/python"
    print(f"{'OK ' if mlx_python.is_file() else 'BLOCKED'} prismml-mlx python {mlx_python}")
    for name, m in cfg["models"].items():
        for engine, e in cfg["engines"].items():
            if not model_supports_engine(cfg, name, engine):
                continue
            if e.get("requires") == "gguf":
                try:
                    artifact = gguf_path_for(cfg, name)
                    print(f"OK {name}: {artifact}")
                except SystemExit as exc:
                    print(f"NOT CACHED {name}: {exc}")
            elif e.get("requires") in {"mlx", "prismml_mlx"}:
                d = m.get(e["requires"])
                exists = bool(d and (Path(cfg["mlx_root"]) / d).is_dir())
                print(
                    f"{'OK ' if exists else 'NOT FETCHED'} {name}: {cfg['mlx_root']}/{d or 'unset'}"
                )
        for key in ("drafter", "draft_model"):
            if m.get(key):
                exists = Path(local_dir_for(cfg, m[key])).is_dir()
                print(
                    f"{'OK ' if exists else 'MISSING (fetch-drafters)'} {name} {key}: {local_dir_for(cfg, m[key])}"
                )
    gate, msg = start_gate(cfg)
    print(
        f"{'OK ' if gate else 'BLOCKED'} {msg} (start ceiling {cfg['guard']['max_start_swap_used_mb']}MB)"
    )
    print(_run(["rapid-mlx", "--no-telemetry", "telemetry", "status"]).strip().splitlines()[:1])
    return 0 if ok and gate else 1


def cmd_fetch_drafters(cfg: dict) -> int:
    for m in cfg["models"].values():
        for key in ("drafter", "draft_model"):
            if m.get(key):
                dest = local_dir_for(cfg, m[key])
                print(f"hf download {m[key]} -> {dest}")
                subprocess.run(["hf", "download", m[key], "--local-dir", dest], check=True)
                conf = json.loads((Path(dest) / "config.json").read_text())
                print(f"  format: {drafter_format(conf)}")
    return 0


def drafter_format(conf: dict) -> str:
    if (conf.get("dflash_config") or {}).get("target_layer_ids"):
        return "z-lab DFlash (dflash_config.target_layer_ids) — what MLX engines auto-detect"
    if conf.get("speculators_model_type"):
        return (
            f"`speculators` {conf.get('speculators_model_type')} (aux_hidden_state_layer_ids, "
            f"draft_vocab_size {conf.get('draft_vocab_size')}) — vLLM-CUDA format; MLX engines may reject it"
        )
    return f"plain model ({conf.get('model_type')}) — classic draft-model use"


def cmd_build_prefill(cfg: dict) -> int:
    print(json.dumps(build_prefill(cfg), indent=1))
    return 0


def cmd_summarize(cfg: dict) -> int:
    print(summarize(cfg))
    return 0


def cmd_commands(cfg: dict) -> int:
    for engine, engine_cfg in cfg["engines"].items():
        if engine_cfg["kind"] != "managed":
            continue
        for model in cfg["models"]:
            if not model_supports_engine(cfg, model, engine):
                continue
            for mode in ("plain", "spec"):
                with contextlib.suppress(SystemExit):
                    argv, cwd = launch_command(cfg, engine, model, mode)
                    prefix = f"(cwd {cwd}) " if cwd else ""
                    print(f"{engine:14s} {model:8s} {mode:5s} {prefix}{' '.join(argv)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("doctor", "fetch-drafters", "build-prefill", "summarize", "commands"):
        sub.add_parser(name)
    for name in (
        "switch",
        "preflight",
        "sanity",
        "speed",
        "security",
        "quality",
        "stop",
        "start-only",
    ):
        p = sub.add_parser(name)
        p.add_argument("--engine", required=True)
        if name != "stop":
            p.add_argument("--model", required=True)
        p.add_argument("--mode", choices=["plain", "spec"], default="plain")
        p.add_argument("--rounds", type=int, default=3)
        p.add_argument("--repeats", type=int, default=3)
        p.add_argument("--max-tokens", type=int, default=400)
    a = ap.parse_args(argv)
    cfg = load_config()
    handlers = {
        "doctor": cmd_doctor,
        "fetch-drafters": cmd_fetch_drafters,
        "build-prefill": cmd_build_prefill,
        "summarize": cmd_summarize,
        "commands": cmd_commands,
    }
    if a.cmd in handlers:
        return handlers[a.cmd](cfg)
    with single_flight():
        return dispatch(cfg, a)


def dispatch(cfg: dict, a) -> int:
    if a.cmd == "stop":
        stop_managed(cfg, a.engine)
        return 0
    if a.cmd == "switch":
        print(json.dumps(switch(cfg, a.engine, a.model, a.mode), indent=1))
        return 0
    if a.cmd == "start-only":
        print(json.dumps(start_managed(cfg, a.engine, a.model, a.mode), indent=1))
        return 0
    if a.cmd == "preflight":
        gate, msg = start_gate(cfg)
        if not gate:
            raise SystemExit(f"rule 3: {msg} — clear swap before measuring")
        with Guard(cfg, a.engine, a.model) as g:
            res = preflight(cfg, a.engine, a.model, a.mode)
        guard = g.verdict()
        append_row(
            a.model,
            {
                **base_row(cfg, "preflight", a.engine, a.model, a.mode),
                "result": res,
                "guard": guard,
                "valid": guard["valid"],
            },
        )
        print(json.dumps({**res, "guard": guard}, indent=1))
        return 0 if res["verdict"] == "OK" and guard["valid"] else 1
    if a.cmd == "sanity":
        if not model_supports_engine(cfg, a.model, a.engine):
            raise SystemExit(f"{a.engine} does not support {a.model}")
        gate, msg = start_gate(cfg)
        if not gate:
            raise SystemExit(f"rule 3: {msg} — clear swap before measuring")
        with Guard(cfg, a.engine, a.model) as g:
            result = run_compatibility_sanity(cfg, a.engine, a.model, a.mode)
        verdict = g.verdict()
        row = {
            **base_row(cfg, "compatibility", a.engine, a.model, a.mode),
            **result,
            "guard": verdict,
            "valid": verdict["valid"],
        }
        path = append_row(a.model, row)
        print(json.dumps({**result, "guard": verdict, "written": str(path)}, indent=1))
        return 0 if verdict["valid"] else 2
    gate, msg = start_gate(cfg)
    if not gate:
        raise SystemExit(f"rule 3: {msg} — clear swap before measuring")
    with Guard(cfg, a.engine, a.model) as g:
        if a.cmd == "speed":
            res = measure_speed(cfg, a.engine, a.model, a.mode, a.rounds, a.max_tokens)
            payload = {
                "summary": speed_summary(res),
                "raw": res,
                "decode_max_tokens": a.max_tokens,
            }
        elif a.cmd == "security":
            rows = run_security(cfg, a.engine, a.model, a.mode, a.repeats)
            payload = {"summary": security_summary(rows), "rows": rows}
        else:
            payload = run_quality(cfg, a.engine, a.model, a.mode, a.repeats)
    v = g.verdict()
    row = {
        **base_row(cfg, a.cmd, a.engine, a.model, a.mode),
        **payload,
        "guard": v,
        "valid": v["valid"],
    }
    path = append_row(a.model, row)
    print(json.dumps({"summary": payload["summary"], "guard": v, "written": str(path)}, indent=1))
    return 0 if v["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
