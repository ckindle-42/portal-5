#!/usr/bin/env python3
"""MLX Model Switch Benchmark — two modes: raw server vs proxy.

Usage:
    python3 scripts/mlx-switch-benchmark.py --mode raw        # direct server start/stop
    python3 scripts/mlx-switch-benchmark.py --mode proxy      # through the MLX proxy (like acceptance tests)
    python3 scripts/mlx-switch-benchmark.py --mode both       # run both, compare results
    python3 scripts/mlx-switch-benchmark.py --model mlx-community/Qwen3-Coder-Next-4bit  # single model
    python3 scripts/mlx-switch-benchmark.py --dry-run          # show plan without executing

Mode: raw
    Direct mlx_lm.server / mlx_vlm.server start/stop timing.
    Measures what the machine is capable of — baseline.

Mode: proxy
    Sends requests through the MLX proxy at :8081 (exactly like acceptance tests).
    Measures what actually happens in production — includes proxy overhead,
    server switching (kill old, start new), and model warmup.

Comparison (both):
    Runs both modes and outputs a side-by-side table showing the gap
    between raw capability and proxy reality. This gap identifies
    where the proxy or switching logic adds overhead.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

LM_PORT = 18081
VLM_PORT = 18082
PROXY_PORT = 8081
RESULTS_FILE = "/tmp/mlx_switch_benchmark.json"

LM_MODELS = [
    "mlx-community/Qwen3-Coder-Next-4bit",
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit",
    "mlx-community/DeepSeek-Coder-V2-Lite-Instruct-8bit",
    "mlx-community/Devstral-Small-2505-8bit",
    "mlx-community/Dolphin3.0-Llama3.1-8B-8bit",
    "mlx-community/Llama-3.2-3B-Instruct-8bit",
    "lmstudio-community/Magistral-Small-2509-MLX-8bit",
    "mlx-community/Llama-3.3-70B-Instruct-4bit",
    "Jackrong/MLX-Qwopus3.5-27B-v3-8bit",
    "Jackrong/MLX-Qwopus3.5-9B-v3-8bit",
    "Jackrong/MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-8bit",
    "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
]

VLM_MODELS = [
    "mlx-community/gemma-4-31b-it-4bit",
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",
    "mlx-community/llava-1.5-7b-8bit",
]


def _load_env() -> None:
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _send_notification(message: str) -> None:
    if os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        from portal_pipeline.notifications.dispatcher import NotificationDispatcher
        from portal_pipeline.notifications.events import AlertEvent, EventType
        from portal_pipeline.notifications.channels.slack import SlackChannel
        from portal_pipeline.notifications.channels.telegram import TelegramChannel
        from portal_pipeline.notifications.channels.email import EmailChannel
        from portal_pipeline.notifications.channels.pushover import PushoverChannel
        from portal_pipeline.notifications.channels.webhook import WebhookChannel

        dispatcher = NotificationDispatcher()
        for ch in [SlackChannel, TelegramChannel, EmailChannel, PushoverChannel, WebhookChannel]:
            dispatcher.add_channel(ch())

        event = AlertEvent(
            type=EventType.CONFIG_ERROR,
            message=f"[MLX Benchmark] {message}",
            workspace="mlx-benchmark",
        )
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(dispatcher.dispatch(event))
        except RuntimeError:
            import asyncio as _asyncio

            _asyncio.run(dispatcher.dispatch(event))
    except Exception as e:
        print(f"  ⚠️  Notification failed: {e}")


WATCHDOG_PID_FILE = Path("/tmp/mlx-watchdog.pid")


def _kill_port(port: int) -> None:
    try:
        res = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for pid in res.stdout.strip().split("\n"):
            if pid:
                subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
    except Exception:
        pass


def _stop_watchdog() -> bool:
    """Stop the MLX watchdog if running. Returns True if watchdog was stopped."""
    if WATCHDOG_PID_FILE.exists():
        try:
            pid = int(WATCHDOG_PID_FILE.read_text().strip())
            subprocess.run(["kill", str(pid)], capture_output=True, timeout=5)
            # Wait for it to die
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.5)
                except ProcessLookupError:
                    break
            else:
                subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=5)
            WATCHDOG_PID_FILE.unlink(missing_ok=True)
            print("  ⏸️  MLX watchdog stopped")
            return True
        except (ProcessLookupError, ValueError, FileNotFoundError):
            WATCHDOG_PID_FILE.unlink(missing_ok=True)
    return False


def _start_watchdog() -> None:
    """Restart the MLX watchdog if it was running before the benchmark."""
    script_dir = Path(__file__).parent
    watchdog_script = script_dir / "mlx-watchdog.py"
    if watchdog_script.exists():
        subprocess.Popen(
            ["python3", str(watchdog_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        if WATCHDOG_PID_FILE.exists():
            print("  ▶️  MLX watchdog restarted")


def _wait_for_server(port: int, timeout: int = 300) -> tuple[bool, float, dict]:
    start = time.time()
    deadline = start + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            if r.status_code == 200:
                return True, round(time.time() - start, 1), r.json()
        except Exception:
            pass
        time.sleep(1)
    return False, round(time.time() - start, 1), {}


def _get_memory_pressure() -> str | None:
    try:
        r = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if "System-wide memory free percentage" in line:
                return line.strip()
    except Exception:
        return None


def _is_vlm(model: str) -> bool:
    return model.split("/")[-1] in {
        "gemma-4-31b-it-4bit",
        "Qwen3-VL-32B-Instruct-8bit",
        "llava-1.5-7b-8bit",
    }


# ── RAW mode: direct server start/stop ────────────────────────────────────────


def benchmark_raw(model: str, dry_run: bool = False) -> dict:
    """Benchmark raw server start/stop — no proxy."""
    vlm = _is_vlm(model)
    server_type = "mlx_vlm" if vlm else "mlx_lm"
    port = VLM_PORT if vlm else LM_PORT

    result = {
        "model": model,
        "server_type": server_type,
        "port": port,
        "mode": "raw",
        "load_time_s": None,
        "unload_time_s": None,
        "load_success": False,
        "unload_success": False,
        "health_data": None,
        "memory_before": None,
        "memory_after": None,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY RUN] {model} ({server_type} on :{port})")
        return result

    print(f"\n  ── RAW: {model} ({server_type} on :{port}) ──")
    result["memory_before"] = _get_memory_pressure()

    # Ensure port is free
    _kill_port(port)
    time.sleep(2)

    # Start server
    cmd = [
        "python3",
        "-m",
        f"{server_type}.server",
        "--port",
        str(port),
        "--host",
        "127.0.0.1",
        "--model",
        model,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    healthy, load_time, health_data = _wait_for_server(port, timeout=300)
    result["load_time_s"] = load_time
    result["load_success"] = healthy

    if healthy:
        result["health_data"] = health_data
        print(f"    ✅ Loaded in {load_time:.1f}s")
    else:
        result["error"] = f"no response in 300s (PID {proc.pid})"
        print(f"    ❌ Failed after {load_time:.1f}s")
        proc.kill()
        _kill_port(port)
        return result

    # Stop server
    stop_start = time.time()
    proc.terminate()
    try:
        proc.wait(timeout=30)
        result["unload_time_s"] = round(time.time() - stop_start, 1)
        result["unload_success"] = True
        print(f"    ✅ Unloaded in {result['unload_time_s']:.1f}s")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        result["unload_time_s"] = round(time.time() - stop_start, 1)
        result["unload_success"] = False
        result["error"] = "required SIGKILL"
        print(f"    ⚠️  SIGKILL after {result['unload_time_s']:.1f}s")

    _kill_port(port)
    time.sleep(2)
    result["memory_after"] = _get_memory_pressure()
    return result


# ── PROXY mode: through the MLX proxy ─────────────────────────────────────────


def benchmark_proxy(model: str, dry_run: bool = False, kill_proxy_before: bool = False) -> dict:
    """Benchmark through the MLX proxy — exactly like acceptance tests.

    Measures:
    - switch_type: cold_start, same_server, cross_server
    - switch_time: time proxy spends switching (state change to ready)
    - response_time: total time from request to first response byte
    """
    vlm = _is_vlm(model)
    server_type = "mlx_vlm" if vlm else "mlx_lm"

    result = {
        "model": model,
        "server_type": server_type,
        "mode": "proxy",
        "switch_type": None,
        "switch_time_s": None,
        "response_time_s": None,
        "success": False,
        "error": None,
        "proxy_before": None,
        "proxy_after": None,
        "memory_before": None,
        "memory_after": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY RUN] {model} ({server_type}) via proxy :{PROXY_PORT}")
        return result

    print(f"\n  ── PROXY: {model} ({server_type}) via :{PROXY_PORT} ──")
    result["memory_before"] = _get_memory_pressure()

    # Kill proxy servers if requested (forces cold start)
    if kill_proxy_before:
        print("    Killing proxy servers...")
        _kill_port(LM_PORT)
        _kill_port(VLM_PORT)
        time.sleep(3)

    # Capture proxy state before
    try:
        r = httpx.get(f"http://127.0.0.1:{PROXY_PORT}/health", timeout=5)
        result["proxy_before"] = r.json() if r.status_code == 200 else None
    except Exception:
        result["proxy_before"] = None

    before = result["proxy_before"] or {}
    server_before = before.get("active_server")
    model_before = before.get("loaded_model")

    # Determine switch type
    if server_before is None:
        result["switch_type"] = "cold_start"
    elif vlm and server_before != "vlm":
        result["switch_type"] = "cross_server"
    elif not vlm and server_before != "lm":
        result["switch_type"] = "cross_server"
    else:
        result["switch_type"] = "same_server"

    print(f"    Before: server={server_before}, model={model_before}")
    print(f"    Switch: {result['switch_type']}")

    # Send request through proxy
    req_start = time.time()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say PONG"}],
                "max_tokens": 5,
                "stream": False,
            },
            timeout=300,
        )
        result["response_time_s"] = round(time.time() - req_start, 1)

        if r.status_code == 200:
            result["success"] = True
            print(f"    ✅ Response in {result['response_time_s']:.1f}s")
        else:
            result["error"] = f"HTTP {r.status_code}: {r.text[:100]}"
            print(f"    ❌ HTTP {r.status_code}: {r.text[:100]}")
    except httpx.ReadTimeout:
        result["error"] = "timeout (300s)"
        result["response_time_s"] = 300.0
        print(f"    ❌ Timeout after 300s")
    except Exception as e:
        result["error"] = str(e)[:100]
        result["response_time_s"] = round(time.time() - req_start, 1)
        print(f"    ❌ Error: {e}")

    # Capture proxy state after
    try:
        r = httpx.get(f"http://127.0.0.1:{PROXY_PORT}/health", timeout=5)
        result["proxy_after"] = r.json() if r.status_code == 200 else None
    except Exception:
        result["proxy_after"] = None

    after = result["proxy_after"] or {}
    print(f"    After: server={after.get('active_server')}, model={after.get('loaded_model')}")

    # Estimate switch time from proxy state_duration
    if after.get("state") == "ready" and after.get("state_duration_sec") is not None:
        result["switch_time_s"] = round(after["state_duration_sec"], 1)

    result["memory_after"] = _get_memory_pressure()
    return result


# ── Main ──────────────────────────────────────────────────────────────────────


def _print_progress(current, total, mode, model, elapsed, server_type=""):
    """Print a rich progress indicator with mode, percentage, and ETA."""
    pct = (current / total) * 100
    bar_width = 40
    filled = int(bar_width * current / total)
    bar = "█" * filled + "░" * (bar_width - filled)
    eta = (elapsed / current * (total - current)) if current > 0 else 0
    eta_str = f"{eta:.0f}s" if eta < 60 else f"{eta / 60:.1f}m"
    mode_label = {"raw": "RAW", "proxy": "PROXY", "both": "BOTH"}.get(mode, mode.upper())
    short_model = model.split("/")[-1]
    print(f"\n  [{bar}] {pct:5.1f}% | {mode_label:>5} | {short_model:<45} | ETA: {eta_str}")
    if server_type:
        print(f"  {'':>6}({server_type})")


def run_benchmark(mode: str, models: list[str], dry_run: bool) -> tuple[list[dict], float]:
    results = []
    t0 = time.time()

    # Calculate total individual runs for progress tracking
    runs_per_model = 2 if mode == "both" else 1
    total_runs = len(models) * runs_per_model
    run_counter = 0

    for i, model in enumerate(models, 1):
        vlm = _is_vlm(model)
        server_type = "mlx_vlm" if vlm else "mlx_lm"

        if mode == "raw":
            run_counter += 1
            _print_progress(run_counter, total_runs, mode, model, time.time() - t0, server_type)
            r = benchmark_raw(model, dry_run=dry_run)
            results.append(r)
        elif mode == "proxy":
            run_counter += 1
            _print_progress(run_counter, total_runs, mode, model, time.time() - t0, server_type)
            r = benchmark_proxy(model, dry_run=dry_run, kill_proxy_before=(i == 1))
            results.append(r)
        else:
            # both: run raw first, then proxy
            run_counter += 1
            _print_progress(run_counter, total_runs, "raw", model, time.time() - t0, server_type)
            r_raw = benchmark_raw(model, dry_run=dry_run)
            results.append(r_raw)

            run_counter += 1
            _print_progress(run_counter, total_runs, "proxy", model, time.time() - t0, server_type)
            r_proxy = benchmark_proxy(model, dry_run=dry_run, kill_proxy_before=False)
            results.append(r_proxy)

        if not dry_run and i < len(models):
            print("    Waiting 10s for memory to settle...")
            time.sleep(10)

    return results, time.time() - t0


def print_summary(results: list[dict]) -> None:
    # Group by mode
    raw_results = [r for r in results if r.get("mode") == "raw"]
    proxy_results = [r for r in results if r.get("mode") == "proxy"]

    if raw_results and proxy_results:
        # Side-by-side comparison
        print("\n" + "=" * 130)
        print(
            f"{'Model':<55} {'Raw Load':<12} {'Raw Unload':<12} {'Proxy Resp':<12} {'Proxy Switch':<12} {'Proxy Type':<12}"
        )
        print("=" * 130)

        # Build lookup by model
        raw_by_model = {r["model"]: r for r in raw_results}
        proxy_by_model = {r["model"]: r for r in proxy_results}

        for model in sorted(set(list(raw_by_model.keys()) + list(proxy_by_model.keys()))):
            raw = raw_by_model.get(model, {})
            proxy = proxy_by_model.get(model, {})

            raw_load = (
                f"{raw.get('load_time_s', '?')}s" if raw.get("load_time_s") is not None else "N/A"
            )
            raw_unload = (
                f"{raw.get('unload_time_s', '?')}s"
                if raw.get("unload_time_s") is not None
                else "N/A"
            )
            proxy_resp = (
                f"{proxy.get('response_time_s', '?')}s"
                if proxy.get("response_time_s") is not None
                else "N/A"
            )
            proxy_switch = (
                f"{proxy.get('switch_time_s', '?')}s"
                if proxy.get("switch_time_s") is not None
                else "N/A"
            )
            proxy_type = proxy.get("switch_type") or "N/A"

            # Gap
            if raw.get("load_time_s") and proxy.get("response_time_s"):
                gap = proxy["response_time_s"] - raw["load_time_s"]
                if gap > 5:
                    proxy_resp += f" (+{gap:.0f}s)"

            print(
                f"{model:<55} {raw_load:<12} {raw_unload:<12} {proxy_resp:<12} {proxy_switch:<12} {proxy_type:<12}"
            )

        print("=" * 130)

    # Per-mode stats
    for mode_name, mode_results in [("raw", raw_results), ("proxy", proxy_results)]:
        if not mode_results:
            continue
        times_key = "load_time_s" if mode_name == "raw" else "response_time_s"
        times = [
            r[times_key]
            for r in mode_results
            if r.get(times_key) and r.get("load_success" if mode_name == "raw" else "success")
        ]
        if times:
            print(f"\n  {mode_name.upper()} ({len(times)} models):")
            print(
                f"    {'Load' if mode_name == 'raw' else 'Response'}:  min={min(times):.1f}s  max={max(times):.1f}s  avg={sum(times) / len(times):.1f}s"
            )

        if mode_name == "raw":
            unload_times = [
                r["unload_time_s"]
                for r in mode_results
                if r.get("unload_time_s") and r.get("unload_success")
            ]
            if unload_times:
                print(
                    f"    Unload: min={min(unload_times):.1f}s  max={max(unload_times):.1f}s  avg={sum(unload_times) / len(unload_times):.1f}s"
                )
        else:
            by_switch = {}
            for r in mode_results:
                st = r.get("switch_type", "unknown")
                if st not in by_switch:
                    by_switch[st] = []
                if r.get("response_time_s") and r.get("success"):
                    by_switch[st].append(r["response_time_s"])
            if by_switch:
                print(f"    By switch type:")
                for st, times in by_switch.items():
                    if times:
                        print(
                            f"      {st}: {len(times)} requests, avg={sum(times) / len(times):.1f}s, range={min(times):.1f}-{max(times):.1f}s"
                        )


def main() -> None:
    parser = argparse.ArgumentParser(description="MLX Model Switch Benchmark")
    parser.add_argument(
        "--mode",
        choices=["raw", "proxy", "both"],
        default="raw",
        help="Benchmark mode: raw (direct server), proxy (through MLX proxy), both (compare)",
    )
    parser.add_argument("--model", help="Benchmark a single model (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON file path")
    args = parser.parse_args()

    mode_label = {
        "raw": "Raw server start/stop",
        "proxy": "Through MLX proxy",
        "both": "Both modes — comparison",
    }
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║  MLX Model Switch Benchmark                                       ║")
    print(
        f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                     ║"
    )
    print(f"║  Mode: {mode_label[args.mode]:<52}║")
    print("╚═══════════════════════════════════════════════════════════════════╝")

    # Stop watchdog to prevent it from interfering with benchmark
    watchdog_was_running = _stop_watchdog()

    # Kill any existing MLX servers
    print("  Clearing existing MLX servers...")
    _kill_port(LM_PORT)
    _kill_port(VLM_PORT)
    time.sleep(3)

    models = [args.model] if args.model else LM_MODELS + VLM_MODELS
    print(f"  Models to benchmark: {len(models)}")
    if args.dry_run:
        print("  [DRY RUN — no actual loading/unloading]")

    results, total_time = run_benchmark(args.mode, models, args.dry_run)

    print_summary(results)
    print(f"\nTotal wall time: {total_time:.0f}s ({total_time / 60:.1f} min)")

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "total_wall_time_s": round(total_time, 1),
        "models_benchmarked": len(models),
        "dry_run": args.dry_run,
        "results": results,
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {args.output}")

    success = sum(1 for r in results if r.get("load_success") or r.get("success"))
    _send_notification(
        f"Benchmark ({args.mode}) complete: {success}/{len(results)} tested in {total_time / 60:.0f}min. "
        f"Results: {args.output}"
    )

    # Restart watchdog if it was running before
    if watchdog_was_running:
        _start_watchdog()


if __name__ == "__main__":
    main()
