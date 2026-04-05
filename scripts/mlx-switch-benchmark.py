#!/usr/bin/env python3
"""MLX Model Switch Benchmark — measures real-world switch times through the proxy.

Usage:
    python3 scripts/mlx-switch-benchmark.py              # benchmark all models
    python3 scripts/mlx-switch-benchmark.py --model mlx-community/Qwen3-Coder-Next-4bit  # single
    python3 scripts/mlx-switch-benchmark.py --dry-run    # show plan without executing
    python3 scripts/mlx-switch-benchmark.py --sequence   # test realistic switching sequence

How it works:
    The MLX proxy auto-switches between mlx_lm (port 18081) and mlx_vlm (port 18082)
    based on the requested model. Only one server runs at a time. This benchmark:

    1. Sends a minimal chat request through the proxy for each model
    2. Measures total time from request start to first response byte
    3. Records the switch type:
       - cold_start: no server was running, starting fresh
       - same_server: same server type (lm→lm or vlm→vlm), just model swap
       - cross_server: switching between lm and vlm (kill old, start new)
    4. Records success/failure, errors, memory pressure indicators

    This gives real-world data for:
    - Setting accurate timeouts in acceptance tests
    - Identifying models that cause GPU crashes
    - Understanding switching patterns and memory pressure
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

MLX_URL = "http://localhost:8081"
RESULTS_FILE = "/tmp/mlx_switch_benchmark.json"

# Models grouped by server type for efficient benchmarking
VLM_MODELS = [
    "mlx-community/gemma-4-31b-it-4bit",
    "mlx-community/Qwen3-VL-32B-Instruct-8bit",
    "mlx-community/llava-1.5-7b-8bit",
]

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


def _load_env() -> None:
    """Load .env if present."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _send_notification(message: str) -> None:
    """Send a notification if enabled."""
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


def _get_proxy_health() -> dict:
    """Get current MLX proxy health state."""
    try:
        r = httpx.get(f"{MLX_URL}/health", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def _get_proxy_state() -> str:
    """Get current MLX proxy state (ready, switching, degraded, down, none)."""
    health = _get_proxy_health()
    return health.get("state", "unknown")


def _get_active_server() -> str | None:
    """Get currently active server type (lm, vlm, or None)."""
    health = _get_proxy_health()
    return health.get("active_server")


def _get_loaded_model() -> str | None:
    """Get currently loaded model name."""
    health = _get_proxy_health()
    return health.get("loaded_model")


def _wait_for_ready(timeout: int = 120) -> bool:
    """Wait for MLX proxy to reach ready state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _get_proxy_state() == "ready":
            return True
        time.sleep(1)
    return False


def _wait_for_switching(timeout: int = 30) -> bool:
    """Wait for MLX proxy to enter switching state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = _get_proxy_state()
        if state == "switching":
            return True
        if state == "ready":
            return False  # Already ready, no switch needed
        time.sleep(0.5)
    return False


def _kill_all_mlx_servers() -> None:
    """Kill all MLX server processes to start from clean state."""
    for port in [18081, 18082]:
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
    time.sleep(3)


def benchmark_model(
    model: str,
    dry_run: bool = False,
    kill_before: bool = False,
) -> dict:
    """Benchmark a single model through the MLX proxy.

    Args:
        model: The model to benchmark
        dry_run: If True, just print the plan without executing
        kill_before: If True, kill all servers before this model (forces cold start)

    Returns:
        Dict with benchmark results
    """
    is_vlm = model.split("/")[-1] in {
        "gemma-4-31b-it-4bit",
        "Qwen3-VL-32B-Instruct-8bit",
        "llava-1.5-7b-8bit",
    }
    server_type = "mlx_vlm" if is_vlm else "mlx_lm"

    result = {
        "model": model,
        "server_type": server_type,
        "is_vlm": is_vlm,
        "switch_type": None,  # cold_start, same_server, cross_server
        "switch_time_s": None,  # time from request to proxy ready
        "response_time_s": None,  # time from request to first response byte
        "total_time_s": None,  # total time for the request
        "success": False,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY RUN] {model} ({server_type})")
        return result

    print(f"\n  ── Benchmarking: {model} ({server_type}) ──")

    # Get state before request
    health_before = _get_proxy_health()
    server_before = health_before.get("active_server")
    model_before = health_before.get("loaded_model")
    state_before = health_before.get("state")

    # Determine expected switch type
    if kill_before or server_before is None:
        result["switch_type"] = "cold_start"
    elif is_vlm and server_before != "vlm":
        result["switch_type"] = "cross_server"
    elif not is_vlm and server_before != "lm":
        result["switch_type"] = "cross_server"
    else:
        result["switch_type"] = "same_server"

    print(f"    Before: server={server_before}, model={model_before}, state={state_before}")
    print(f"    Expected switch: {result['switch_type']}")

    # Kill servers if requested (forces cold start)
    if kill_before:
        print("    Killing all MLX servers...")
        _kill_all_mlx_servers()

    # Send the request and measure timing
    print(f"    Sending request...")
    request_start = time.time()

    try:
        r = httpx.post(
            f"{MLX_URL}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say PONG"}],
                "max_tokens": 5,
                "stream": False,
            },
            timeout=300,
        )

        request_end = time.time()
        result["total_time_s"] = round(request_end - request_start, 1)

        if r.status_code == 200:
            result["success"] = True

            # Get state after request
            health_after = _get_proxy_health()
            server_after = health_after.get("active_server")
            model_after = health_after.get("loaded_model")

            # Estimate switch time (proxy enters switching state, then becomes ready)
            # The total time includes: switch time + model load time + inference time
            # For a minimal request, inference time is negligible
            result["response_time_s"] = result["total_time_s"]

            print(f"    ✅ Success in {result['total_time_s']:.1f}s")
            print(f"    After: server={server_after}, model={model_after}")
        else:
            result["error"] = f"HTTP {r.status_code}: {r.text[:100]}"
            print(f"    ❌ HTTP {r.status_code}: {r.text[:100]}")

    except httpx.ReadTimeout:
        result["error"] = "Request timed out (300s)"
        result["total_time_s"] = 300.0
        print(f"    ❌ Timeout after 300s")
    except Exception as e:
        result["error"] = str(e)[:100]
        result["total_time_s"] = round(time.time() - request_start, 1)
        print(f"    ❌ Error: {e}")

    return result


def run_sequence_benchmark(dry_run: bool = False) -> list[dict]:
    """Run a realistic sequence of model switches.

    This simulates how the acceptance test suite uses MLX models:
    1. Start with cold state
    2. Load a coding model (mlx_lm)
    3. Load a reasoning model (mlx_lm) - same server, different model
    4. Load a VLM model (mlx_vlm) - cross-server switch
    5. Load another VLM model (mlx_vlm) - same server, different model
    6. Switch back to coding model (mlx_lm) - cross-server switch
    7. Kill all servers, start fresh (cold start test)
    """
    print("\n━━━ Sequence Benchmark ━━━")
    print("Simulating realistic model switching pattern...")

    sequence = [
        # (model, kill_before, description)
        ("mlx-community/Qwen3-Coder-Next-4bit", True, "Cold start: coding model"),
        (
            "mlx-community/DeepSeek-R1-Distill-Qwen-32B-abliterated-4bit",
            False,
            "Same server: reasoning model",
        ),
        ("mlx-community/gemma-4-31b-it-4bit", False, "Cross-server: VLM model"),
        ("mlx-community/Qwen3-VL-32B-Instruct-8bit", False, "Same server: another VLM"),
        ("mlx-community/Devstral-Small-2505-8bit", False, "Cross-server: back to lm"),
        ("mlx-community/Llama-3.3-70B-Instruct-4bit", False, "Same server: heavy model"),
    ]

    results = []
    for model, kill_before, description in sequence:
        print(f"\n  [{description}]")
        result = benchmark_model(model, dry_run=dry_run, kill_before=kill_before)
        result["description"] = description
        results.append(result)

        # Brief pause between models
        if not dry_run:
            time.sleep(5)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="MLX Model Switch Benchmark")
    parser.add_argument("--model", help="Benchmark a single model (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--sequence", action="store_true", help="Run realistic switching sequence")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON file path")
    args = parser.parse_args()

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║  MLX Model Switch Benchmark                                       ║")
    print(
        f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                     ║"
    )
    print("╚═══════════════════════════════════════════════════════════════════╝")

    # Check MLX proxy is reachable
    health = _get_proxy_health()
    if not health:
        print("❌ MLX proxy unreachable at localhost:8081")
        print("   Make sure the MLX proxy is running: ./launch.sh status")
        sys.exit(1)

    state = health.get("state", "unknown")
    server = health.get("active_server", "none")
    model = health.get("loaded_model", "none")
    print(f"  MLX proxy: state={state}, server={server}, model={model}")

    if args.sequence:
        # Run sequence benchmark
        results = run_sequence_benchmark(dry_run=args.dry_run)
    else:
        # Run individual model benchmarks
        models = [args.model] if args.model else LM_MODELS + VLM_MODELS
        if not models:
            print("❌ No models found")
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

            # Brief pause between models
            if not args.dry_run and i < len(models):
                time.sleep(5)

        total_time = time.time() - t0_total

    # Print summary table
    print("\n" + "=" * 100)
    print(f"{'Model':<55} {'Server':<10} {'Switch':<12} {'Time':<8} {'Status':<8}")
    print("=" * 100)

    for r in results:
        time_s = f"{r['total_time_s']:.1f}s" if r["total_time_s"] else "N/A"
        switch = r.get("switch_type", "?")
        status = "✅" if r["success"] else "❌"
        if r.get("error"):
            status = f"⚠️ {r['error'][:15]}"
        print(f"{r['model']:<55} {r['server_type']:<10} {switch:<12} {time_s:<8} {status}")

    print("=" * 100)

    # Calculate statistics
    success_times = [r["total_time_s"] for r in results if r["success"] and r["total_time_s"]]
    if success_times:
        print(f"\n  Statistics (successful requests):")
        print(f"    Count: {len(success_times)}")
        print(f"    Min: {min(success_times):.1f}s")
        print(f"    Max: {max(success_times):.1f}s")
        print(f"    Avg: {sum(success_times) / len(success_times):.1f}s")

    # Group by switch type
    switch_types = {}
    for r in results:
        st = r.get("switch_type", "unknown")
        if st not in switch_types:
            switch_types[st] = []
        if r["success"] and r["total_time_s"]:
            switch_types[st].append(r["total_time_s"])

    print(f"\n  By switch type:")
    for st, times in switch_types.items():
        if times:
            print(
                f"    {st}: {len(times)} requests, avg {sum(times) / len(times):.1f}s, range {min(times):.1f}-{max(times):.1f}s"
            )

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_time_s": round(time.time() - t0_total, 1) if not args.dry_run else 0,
        "models_benchmarked": len(results),
        "dry_run": args.dry_run,
        "sequence": args.sequence,
        "results": results,
        "statistics": {
            "success_count": len(success_times),
            "min_time_s": min(success_times) if success_times else None,
            "max_time_s": max(success_times) if success_times else None,
            "avg_time_s": sum(success_times) / len(success_times) if success_times else None,
            "by_switch_type": {
                st: {
                    "count": len(times),
                    "avg_time_s": sum(times) / len(times) if times else None,
                    "min_time_s": min(times) if times else None,
                    "max_time_s": max(times) if times else None,
                }
                for st, times in switch_types.items()
            },
        },
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {args.output}")

    # Send notification
    success_count = sum(1 for r in results if r["success"])
    _send_notification(
        f"Benchmark complete: {success_count}/{len(results)} models tested. "
        f"Avg time: {output['statistics']['avg_time_s']:.1f}s. "
        f"Results: {args.output}"
    )


if __name__ == "__main__":
    main()
