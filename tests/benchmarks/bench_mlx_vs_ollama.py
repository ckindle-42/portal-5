#!/usr/bin/env python3
"""Portal 5 — MLX vs Ollama throughput benchmark.

Two modes:
  1. Matched-pair (default): one Llama-3.2-3B test comparing MLX vs Ollama on the
     same architecture to measure the raw backend speed delta.
  2. Full workspace sweep (--all-workspaces): tests every workspace's primary MLX
     model AND its Ollama counterpart/fallback so you can see the real end-to-end
     performance for each inference path the pipeline uses.

Usage:
    python3 tests/benchmarks/bench_mlx_vs_ollama.py
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --runs 5
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --all-workspaces
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --all-workspaces --runs 2
    python3 tests/benchmarks/bench_mlx_vs_ollama.py --workspace auto-coding
"""

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent.parent.resolve()

MLX_URL = "http://localhost:8081"
OLLAMA_URL = "http://localhost:11434"
PIPELINE_URL = "http://localhost:9099"

# ── Matched pair (mode 1) ──────────────────────────────────────────────────────
# Same architecture, different runtime — isolates backend speed difference.
MATCHED_MLX_MODEL = "mlx-community/Llama-3.2-3B-Instruct-8bit"
MATCHED_OLLAMA_MODEL = "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF"

# ── Workspace definitions (mode 2) ────────────────────────────────────────────
# Each workspace has:
#   mlx_model    — HF path, loaded by mlx-proxy (port 8081)
#   ollama_model — Ollama tag that serves as fallback when MLX is down
#   workspace_id — pipeline workspace ID (auto-coding, auto-spl, …)
#
# "primary" = MLX path (preferred); "counterpart" = Ollama fallback.
# Both are tested so you can see pipeline routing overhead + fallback latency.
WORKSPACE_MODELS = [
    {
        "workspace_id": "auto-coding",
        "mlx_model": "lmstudio-community/Devstral-Small-2507-MLX-4bit",
        "ollama_model": "hf.co/bartowski/Devstral-Small-2507-GGUF",
        "prompt": "Write a Python function that returns the n-th Fibonacci number using memoization.",
    },
    {
        "workspace_id": "auto-agentic",
        "mlx_model": "mlx-community/Qwen3-Coder-Next-4bit",
        "ollama_model": "qwen3-coder-next:30b-q5",
        "prompt": "List the steps an autonomous agent should take to refactor a Python monolith into microservices.",
    },
    {
        "workspace_id": "auto-spl",
        "mlx_model": "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
        "ollama_model": "qwen3-coder-next:30b-q5",
        "prompt": "Write a Splunk SPL query to count failed SSH login attempts per source IP over the last 24 hours.",
    },
    {
        "workspace_id": "auto-creative",
        "mlx_model": "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
        "ollama_model": "dolphin-llama3:8b",
        "prompt": "Write the opening paragraph of a cyberpunk noir story set in 2087 Tokyo.",
    },
    {
        "workspace_id": "auto-reasoning",
        "mlx_model": "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
        "ollama_model": "deepseek-r1:32b-q4_k_m",
        "prompt": "Solve step by step: A factory produces 240 widgets per hour. If efficiency drops 15% on weekends, how many widgets are produced in a 5-day week (Mon-Fri) + 2-day weekend at 8h/day?",
    },
    {
        "workspace_id": "auto-documents",
        "mlx_model": "mlx-community/phi-4-8bit",
        "ollama_model": "deepseek-r1:32b-q4_k_m",
        "prompt": "Create a structured outline for a technical specification document for a REST API.",
    },
    {
        "workspace_id": "auto-research",
        "mlx_model": "mlx-community/gemma-4-31b-it-4bit",
        "ollama_model": "deepseek-r1:32b-q4_k_m",
        "prompt": "Summarise the key differences between transformer and Mamba state space models.",
    },
    {
        "workspace_id": "auto-data",
        "mlx_model": "mlx-community/DeepSeek-R1-Distill-Qwen-32B-MLX-8Bit",
        "ollama_model": "deepseek-r1:32b-q4_k_m",
        "prompt": "Explain the difference between variance and standard deviation, and when to use each.",
    },
    {
        "workspace_id": "auto-compliance",
        "mlx_model": "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
        "ollama_model": "deepseek-r1:32b-q4_k_m",
        "prompt": "List the evidence items required to demonstrate compliance with NERC CIP-007 R2 patch management.",
    },
    {
        "workspace_id": "auto-mistral",
        "mlx_model": "lmstudio-community/Magistral-Small-2509-MLX-8bit",
        "ollama_model": "deepseek-r1:32b-q4_k_m",
        "prompt": "Analyse the strategic trade-offs between a monolithic and microservices architecture for a 10-engineer startup.",
    },
    {
        "workspace_id": "auto-security",
        "mlx_model": None,  # security workspace uses Ollama security models
        "ollama_model": "xploiter/the-xploiter",
        "prompt": "Describe three common privilege escalation techniques on Linux and how to detect them.",
    },
    {
        "workspace_id": "auto-redteam",
        "mlx_model": None,
        "ollama_model": "baronllm:q6_k",
        "prompt": "List three MITRE ATT&CK initial access techniques with their technique IDs.",
    },
    {
        "workspace_id": "auto-blueteam",
        "mlx_model": None,
        "ollama_model": "lily-cybersecurity:7b-q4_k_m",
        "prompt": "How do you detect lateral movement in a Windows enterprise network?",
    },
]

TEST_PROMPT = (
    "Explain the difference between TCP and UDP in exactly three sentences. "
    "Be precise and technical."
)


def _load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _check_backend(url: str, path: str, headers: dict | None = None) -> bool:
    try:
        r = httpx.get(f"{url}{path}", timeout=3.0, headers=headers or {})
        return r.status_code in (200, 503)  # 503 = MLX proxy idle but alive
    except Exception:
        return False


def _bench_openai_endpoint(
    base_url: str,
    model: str,
    prompt: str,
    label: str,
    headers: dict | None = None,
    timeout: float = 180.0,
) -> dict | None:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": 200,
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers=headers or {},
            )
            resp.raise_for_status()
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return None
    elapsed = time.perf_counter() - t0

    data = resp.json()
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    tps = completion_tokens / elapsed if elapsed > 0 else 0.0

    return {
        "label": label,
        "model": model,
        "elapsed_s": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tokens_per_sec": round(tps, 1),
    }


def _bench_ollama(model: str, prompt: str, label: str, timeout: float = 180.0) -> dict | None:
    """Benchmark Ollama via its native /api/generate endpoint (no OpenAI shim)."""
    import json as _json
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 200}}
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return None
    elapsed = time.perf_counter() - t0
    data = resp.json()
    completion_tokens = data.get("eval_count", 0)
    tps = completion_tokens / elapsed if elapsed > 0 else 0.0
    return {
        "label": label,
        "model": model,
        "elapsed_s": round(elapsed, 2),
        "completion_tokens": completion_tokens,
        "tokens_per_sec": round(tps, 1),
    }


def _get_unified_memory_gb() -> float | None:
    import subprocess
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        return round(int(out.strip()) / 1024**3, 1)
    except Exception:
        return None


def _print_result(r: dict) -> None:
    print(
        f"  {r['label']:30s}: {r['tokens_per_sec']:6.1f} t/s  "
        f"({r['completion_tokens']} tokens, {r['elapsed_s']}s)"
    )


def run_matched_pair(runs: int) -> None:
    """Mode 1: Compare MLX vs Ollama on the same 3B model architecture."""
    print("\n" + "=" * 70)
    print("Mode 1 — Matched Pair: MLX vs Ollama (Llama-3.2-3B)")
    print("=" * 70)

    mlx_available = _check_backend(MLX_URL, "/health")
    ollama_available = _check_backend(OLLAMA_URL, "/api/tags")

    print(f"MLX    ({MLX_URL}):    {'✅' if mlx_available else '⚠️  not running — skipping'}")
    print(f"Ollama ({OLLAMA_URL}): {'✅' if ollama_available else '⚠️  not running — skipping'}")
    print(f"Prompt: {TEST_PROMPT[:70]}...")
    print(f"Runs: {runs}\n")

    results = []
    for run in range(1, runs + 1):
        print(f"--- Run {run}/{runs} ---")
        if mlx_available:
            r = _bench_openai_endpoint(MLX_URL, MATCHED_MLX_MODEL, TEST_PROMPT, "MLX (Llama-3.2-3B-8bit)")
            if r:
                results.append(r)
                _print_result(r)
        if ollama_available:
            r = _bench_ollama(MATCHED_OLLAMA_MODEL, TEST_PROMPT, "Ollama (Llama-3.2-3B-abliterated)")
            if r:
                results.append(r)
                _print_result(r)

    print("\n" + "=" * 70 + "\nSUMMARY\n" + "=" * 70)
    for label in ["MLX (Llama-3.2-3B-8bit)", "Ollama (Llama-3.2-3B-abliterated)"]:
        runs_data = [r for r in results if r["label"] == label]
        if runs_data:
            avg_tps = sum(r["tokens_per_sec"] for r in runs_data) / len(runs_data)
            avg_elapsed = sum(r["elapsed_s"] for r in runs_data) / len(runs_data)
            print(f"  {label:40s}: avg {avg_tps:.1f} t/s  avg {avg_elapsed:.2f}s/req")

    mlx_runs = [r for r in results if r["label"].startswith("MLX")]
    ol_runs = [r for r in results if r["label"].startswith("Ollama")]
    if mlx_runs and ol_runs:
        mlx_avg = sum(r["tokens_per_sec"] for r in mlx_runs) / len(mlx_runs)
        ol_avg = sum(r["tokens_per_sec"] for r in ol_runs) / len(ol_runs)
        pct = ((mlx_avg - ol_avg) / ol_avg * 100) if ol_avg > 0 else 0
        direction = "faster" if pct >= 0 else "slower"
        print(f"\n  MLX is {abs(pct):.0f}% {direction} than Ollama on this hardware")
        print("  (Expected: 20-40% faster on M4 per CLAUDE.md)")


def run_workspace_sweep(runs: int, only_workspace: str | None = None) -> None:
    """Mode 2: Benchmark primary (MLX) + counterpart (Ollama fallback) for each workspace."""
    _load_env()
    api_key = os.environ.get("PIPELINE_API_KEY", "")
    pipeline_headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    mlx_available = _check_backend(MLX_URL, "/health")
    ollama_available = _check_backend(OLLAMA_URL, "/api/tags")
    pipeline_available = _check_backend(PIPELINE_URL, "/health", pipeline_headers)

    print("\n" + "=" * 70)
    print("Mode 2 — All Workspace Primary/Counterpart Benchmark")
    print("=" * 70)
    print(f"MLX proxy  ({MLX_URL}):    {'✅' if mlx_available else '⚠️  not available'}")
    print(f"Ollama     ({OLLAMA_URL}): {'✅' if ollama_available else '⚠️  not available'}")
    print(f"Pipeline   ({PIPELINE_URL}): {'✅' if pipeline_available else '⚠️  not available'}")
    print(f"Runs per path: {runs}\n")

    workspaces = WORKSPACE_MODELS
    if only_workspace:
        workspaces = [w for w in workspaces if w["workspace_id"] == only_workspace]
        if not workspaces:
            print(f"  ERROR: workspace '{only_workspace}' not found in WORKSPACE_MODELS")
            return

    all_results: list[dict] = []

    for ws in workspaces:
        ws_id = ws["workspace_id"]
        mlx_model = ws.get("mlx_model")
        ollama_model = ws.get("ollama_model")
        prompt = ws.get("prompt", TEST_PROMPT)

        print(f"\n━━━ {ws_id} ━━━")
        ws_results = []

        # Primary path: MLX proxy directly
        if mlx_model and mlx_available:
            print(f"  Primary   (MLX): {mlx_model.split('/')[-1]}")
            for run in range(1, runs + 1):
                r = _bench_openai_endpoint(MLX_URL, mlx_model, prompt, f"{ws_id}/mlx")
                if r:
                    ws_results.append(r)
                    if runs > 1:
                        _print_result(r)
            mlx_ws = [r for r in ws_results if r["label"] == f"{ws_id}/mlx"]
            if mlx_ws:
                avg = sum(r["tokens_per_sec"] for r in mlx_ws) / len(mlx_ws)
                print(f"  → MLX avg: {avg:.1f} t/s over {len(mlx_ws)} run(s)")
        elif mlx_model:
            print(f"  Primary   (MLX): SKIPPED (proxy not available)")

        # Counterpart path: Ollama fallback
        if ollama_model and ollama_available:
            print(f"  Counterpart (Ollama): {ollama_model}")
            for run in range(1, runs + 1):
                r = _bench_ollama(ollama_model, prompt, f"{ws_id}/ollama")
                if r:
                    ws_results.append(r)
                    if runs > 1:
                        _print_result(r)
            ol_ws = [r for r in ws_results if r["label"] == f"{ws_id}/ollama"]
            if ol_ws:
                avg = sum(r["tokens_per_sec"] for r in ol_ws) / len(ol_ws)
                print(f"  → Ollama avg: {avg:.1f} t/s over {len(ol_ws)} run(s)")
        elif ollama_model:
            print(f"  Counterpart (Ollama): SKIPPED (Ollama not available)")

        # Speed delta for this workspace
        mlx_ws = [r for r in ws_results if "/mlx" in r["label"]]
        ol_ws = [r for r in ws_results if "/ollama" in r["label"]]
        if mlx_ws and ol_ws:
            mlx_avg = sum(r["tokens_per_sec"] for r in mlx_ws) / len(mlx_ws)
            ol_avg = sum(r["tokens_per_sec"] for r in ol_ws) / len(ol_ws)
            pct = ((mlx_avg - ol_avg) / ol_avg * 100) if ol_avg > 0 else 0
            direction = "faster" if pct >= 0 else "slower"
            print(f"  → MLX is {abs(pct):.0f}% {direction} than Ollama for {ws_id}")

        all_results.extend(ws_results)

    # Final summary table
    print("\n" + "=" * 70)
    print("SUMMARY — All Workspaces")
    print("=" * 70)
    print(f"  {'Workspace':<22} {'Path':<12} {'Avg t/s':>8}  {'Runs':>5}  Model")
    print("  " + "-" * 66)
    for ws in workspaces:
        ws_id = ws["workspace_id"]
        for path_key, label_suffix in [("mlx_model", "/mlx"), ("ollama_model", "/ollama")]:
            model = ws.get(path_key)
            if not model:
                continue
            runs_data = [r for r in all_results if r["label"] == f"{ws_id}{label_suffix}"]
            if runs_data:
                avg_tps = sum(r["tokens_per_sec"] for r in runs_data) / len(runs_data)
                path_name = "MLX" if label_suffix == "/mlx" else "Ollama"
                model_short = model.split("/")[-1][:30]
                print(f"  {ws_id:<22} {path_name:<12} {avg_tps:>8.1f}  {len(runs_data):>5}  {model_short}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 — MLX vs Ollama benchmark")
    parser.add_argument("--runs", type=int, default=3, help="Number of timed runs per path (default: 3)")
    parser.add_argument("--all-workspaces", action="store_true", help="Benchmark all workspace primary+counterpart pairs")
    parser.add_argument("--workspace", type=str, default=None, help="Benchmark a single workspace (e.g. auto-coding)")
    args = parser.parse_args()

    mem = _get_unified_memory_gb()
    if mem:
        print(f"Unified Memory: {mem}GB")

    if args.all_workspaces or args.workspace:
        run_workspace_sweep(args.runs, only_workspace=args.workspace)
    else:
        run_matched_pair(args.runs)


if __name__ == "__main__":
    main()
