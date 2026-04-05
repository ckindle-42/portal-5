#!/usr/bin/env python3
"""MLX Raw Model Load/Unload Benchmark — direct server timing, no proxy.

Usage:
    python3 scripts/mlx-switch-benchmark.py              # benchmark all models
    python3 scripts/mlx-switch-benchmark.py --model mlx-community/Qwen3-Coder-Next-4bit  # single
    python3 scripts/mlx-switch-benchmark.py --dry-run    # show plan without executing

What this measures:
    1. START time: how long from `python3 -m mlx_lm.server` (or mlx_vlm.server)
       to the server responding on its port — this is the raw model load time
    2. STOP time: how long from sending SIGTERM to the server process exiting
    3. Memory: peak memory usage during load (via `memory_pressure` on macOS)

    This is NOT through the proxy. This is raw server start/stop timing.
    The data is used to set accurate timeouts in acceptance tests and
    diagnose why MLX crashes under sustained load.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

LM_PORT = 18081
VLM_PORT = 18082
RESULTS_FILE = "/tmp/mlx_switch_benchmark.json"

# All MLX models — grouped by server type
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


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port."""
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


def _wait_for_server(port: int, timeout: int = 300) -> tuple[bool, float, dict]:
    """Wait for server on port to respond to /health.

    Returns (success, elapsed_seconds, health_data).
    """
    start = time.time()
    deadline = start + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
            if r.status_code == 200:
                elapsed = time.time() - start
                return True, round(elapsed, 1), r.json()
        except Exception:
            pass
        time.sleep(1)
    return False, round(time.time() - start, 1), {}


def _get_memory_pressure() -> str | None:
    """Get current memory pressure level on macOS."""
    try:
        r = subprocess.run(
            ["memory_pressure"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in r.stdout.splitlines():
            if "System-wide memory free percentage" in line:
                return line.strip()
    except Exception:
        return None


def benchmark_model(model: str, dry_run: bool = False) -> dict:
    """Benchmark raw load/unload time for a single model.

    1. Kill anything on the port
    2. Start the server with the model
    3. Measure time until /health responds (load time)
    4. Kill the server
    5. Measure time until port is free (unload time)
    """
    is_vlm = model.split("/")[-1] in {
        "gemma-4-31b-it-4bit",
        "Qwen3-VL-32B-Instruct-8bit",
        "llava-1.5-7b-8bit",
    }
    server_type = "mlx_vlm" if is_vlm else "mlx_lm"
    port = VLM_PORT if is_vlm else LM_PORT

    result = {
        "model": model,
        "server_type": server_type,
        "port": port,
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

    print(f"\n  ── {model} ({server_type} on :{port}) ──")

    # Memory before
    result["memory_before"] = _get_memory_pressure()

    # Step 1: Ensure port is free
    print(f"    Clearing port :{port}...")
    _kill_port(port)
    time.sleep(2)

    # Step 2: Start server and measure load time
    print(f"    Starting {server_type} with {model}...")
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
    proc_start = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    healthy, load_time, health_data = _wait_for_server(port, timeout=300)
    result["load_time_s"] = load_time
    result["load_success"] = healthy

    if healthy:
        result["health_data"] = health_data
        loaded = health_data.get("loaded_model", model)
        print(f"    ✅ Loaded in {load_time:.1f}s (reported: {loaded})")
    else:
        result["error"] = f"server did not respond within 300s (PID {proc.pid})"
        print(f"    ❌ Failed to start after {load_time:.1f}s")
        proc.kill()
        _kill_port(port)
        return result

    # Step 3: Kill server and measure unload time
    print(f"    Stopping server (PID {proc.pid})...")
    stop_start = time.time()
    proc.terminate()

    # Wait for process to exit
    try:
        proc.wait(timeout=30)
        unload_time = time.time() - stop_start
        result["unload_time_s"] = round(unload_time, 1)
        result["unload_success"] = True
        print(f"    ✅ Unloaded in {unload_time:.1f}s")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        unload_time = time.time() - stop_start
        result["unload_time_s"] = round(unload_time, 1)
        result["unload_success"] = False
        result["error"] = "required SIGKILL to stop"
        print(f"    ⚠️  Required SIGKILL after {unload_time:.1f}s")

    # Ensure port is free
    _kill_port(port)
    time.sleep(2)

    # Memory after
    result["memory_after"] = _get_memory_pressure()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="MLX Raw Model Load/Unload Benchmark")
    parser.add_argument("--model", help="Benchmark a single model (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON file path")
    args = parser.parse_args()

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║  MLX Raw Model Load/Unload Benchmark                              ║")
    print(
        f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                     ║"
    )
    print("║                                                                   ║")
    print("║  Direct server start/stop timing — no proxy                       ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")

    # Kill any existing MLX servers
    print("  Clearing existing MLX servers...")
    _kill_port(LM_PORT)
    _kill_port(VLM_PORT)
    time.sleep(3)

    models = [args.model] if args.model else LM_MODELS + VLM_MODELS
    if not models:
        print("❌ No models specified")
        sys.exit(1)

    print(f"  Models to benchmark: {len(models)}")
    if args.dry_run:
        print("  [DRY RUN — no actual loading/unloading]")

    results = []
    t0_total = time.time()

    for i, model in enumerate(models, 1):
        print(f"\n[{i}/{len(models)}]")
        result = benchmark_model(model, dry_run=args.dry_run)
        results.append(result)

        # Pause between models to let memory settle
        if not args.dry_run and i < len(models):
            print("    Waiting 10s for memory to settle...")
            time.sleep(10)

    total_time = time.time() - t0_total

    # Print summary table
    print("\n" + "=" * 110)
    print(f"{'Model':<60} {'Server':<10} {'Load':<10} {'Unload':<10} {'Status':<10}")
    print("=" * 110)

    for r in results:
        load_s = f"{r['load_time_s']:.1f}s" if r["load_time_s"] else "N/A"
        unload_s = f"{r['unload_time_s']:.1f}s" if r["unload_time_s"] else "N/A"
        if r["load_success"] and r["unload_success"]:
            status = "✅"
        elif r["load_success"]:
            status = "⚠️ load-ok"
        else:
            status = f"❌ {r.get('error', '')[:12]}"
        print(f"{r['model']:<60} {r['server_type']:<10} {load_s:<10} {unload_s:<10} {status}")

    print("=" * 110)
    print(f"Total wall time: {total_time:.0f}s ({total_time / 60:.1f} min)")

    # Statistics by server type
    for stype in ["mlx_lm", "mlx_vlm"]:
        times = [
            r["load_time_s"] for r in results if r["server_type"] == stype and r["load_success"]
        ]
        if times:
            print(f"\n  {stype} ({len(times)} models):")
            print(
                f"    Load:  min={min(times):.1f}s  max={max(times):.1f}s  avg={sum(times) / len(times):.1f}s"
            )
        unload_times = [
            r["unload_time_s"] for r in results if r["server_type"] == stype and r["unload_success"]
        ]
        if unload_times:
            print(
                f"    Unload: min={min(unload_times):.1f}s  max={max(unload_times):.1f}s  avg={sum(unload_times) / len(unload_times):.1f}s"
            )

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_wall_time_s": round(total_time, 1),
        "models_benchmarked": len(results),
        "dry_run": args.dry_run,
        "results": results,
        "statistics": {
            stype: {
                "count": len(
                    [r for r in results if r["server_type"] == stype and r["load_success"]]
                ),
                "load_times": {
                    "min": min(
                        (
                            r["load_time_s"]
                            for r in results
                            if r["server_type"] == stype and r["load_success"]
                        ),
                        default=None,
                    ),
                    "max": max(
                        (
                            r["load_time_s"]
                            for r in results
                            if r["server_type"] == stype and r["load_success"]
                        ),
                        default=None,
                    ),
                    "avg": sum(
                        r["load_time_s"]
                        for r in results
                        if r["server_type"] == stype and r["load_success"]
                    )
                    / max(
                        len(
                            [r for r in results if r["server_type"] == stype and r["load_success"]]
                        ),
                        1,
                    ),
                }
                if any(r["server_type"] == stype and r["load_success"] for r in results)
                else None,
            }
            for stype in ["mlx_lm", "mlx_vlm"]
        },
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {args.output}")

    # Notification
    success = sum(1 for r in results if r["load_success"])
    _send_notification(
        f"Raw benchmark complete: {success}/{len(results)} models tested in {total_time / 60:.0f}min. "
        f"Results: {args.output}"
    )


if __name__ == "__main__":
    main()
