#!/usr/bin/env python3
"""MLX Model Switch Benchmark — measures load/unload/switch times for all MLX models.

Usage:
    python3 scripts/mlx-switch-benchmark.py              # benchmark all models
    python3 scripts/mlx-switch-benchmark.py --model mlx-community/Qwen3-Coder-Next-4bit  # single model
    python3 scripts/mlx-switch-benchmark.py --dry-run    # show plan without executing

This script:
1. Queries the MLX proxy for the list of available models
2. For each model: loads it (measuring time), unloads it (measuring time)
3. Records results in a structured table and writes to /tmp/mlx_switch_benchmark.json
4. Sends a notification when complete (if NOTIFICATIONS_ENABLED=true)

The data helps:
- Set accurate timeouts in the acceptance test suite
- Identify models that cause GPU crashes (OOM, Metal errors)
- Plan model switching order to minimize total test time
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
            type=EventType.CONFIG_ERROR,  # closest existing type
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


def _wait_for_state(target: str, timeout: int = 120) -> tuple[bool, dict]:
    """Wait for MLX proxy to reach the target state.

    Returns (success, health_data).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{MLX_URL}/health", timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get("state") == target:
                    return True, data
        except Exception:
            pass
        time.sleep(1)
    return False, {}


def _wait_for_ready(timeout: int = 120) -> tuple[bool, dict]:
    """Wait for MLX proxy to be ready (loaded model or no model)."""
    return _wait_for_state("ready", timeout)


def _wait_for_none(timeout: int = 60) -> tuple[bool, dict]:
    """Wait for MLX proxy to have no server running (unloaded)."""
    return _wait_for_state("none", timeout)


def _get_model_list() -> list[str]:
    """Get list of available MLX models from the proxy."""
    try:
        r = httpx.get(f"{MLX_URL}/v1/models", timeout=10)
        if r.status_code == 200:
            return [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        print(f"  ❌ Failed to get model list: {e}")
    return []


def _is_vlm_model(model: str) -> bool:
    """Check if a model is a VLM (requires mlx_vlm server)."""
    vlm_indicators = ["gemma-4", "Qwen3-VL", "llava", "Qwopus", "Qwen3.5"]
    return any(ind in model for ind in vlm_indicators)


def _trigger_load(model: str) -> bool:
    """Trigger model loading by sending a minimal chat request."""
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
        return r.status_code == 200
    except Exception as e:
        print(f"  ❌ Load request failed: {e}")
        return False


def _trigger_unload() -> bool:
    """Trigger model unload via the proxy."""
    try:
        # The MLX proxy doesn't have an /unload endpoint, so we need to
        # kill the active server process. The proxy will detect this and
        # transition to "none" or "down" state.
        # We can also send a request to a non-existent model to force unload.
        # For now, we'll use pkill on the mlx_lm_server or mlx_vlm_server.
        health = httpx.get(f"{MLX_URL}/health", timeout=5).json()
        active = health.get("active_server")
        if not active:
            return True  # Already unloaded

        # Kill the active server
        port = 18082 if active == "vlm" else 18081
        subprocess.run(
            ["pkill", "-f", f"mlx_{active}.server.*{port}"],
            capture_output=True,
            timeout=5,
        )
        return True
    except Exception as e:
        print(f"  ❌ Unload failed: {e}")
        return False


def benchmark_model(model: str, dry_run: bool = False) -> dict:
    """Benchmark a single model: load and unload timing.

    Returns a dict with timing results.
    """
    is_vlm = _is_vlm_model(model)
    server_type = "mlx_vlm" if is_vlm else "mlx_lm"

    result = {
        "model": model,
        "server_type": server_type,
        "is_vlm": is_vlm,
        "load_time_s": None,
        "unload_time_s": None,
        "load_success": False,
        "unload_success": False,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY RUN] {model} ({server_type})")
        return result

    print(f"\n  ── Benchmarking: {model} ({server_type}) ──")

    # Step 1: Ensure we start from a clean state
    print("    Ensuring clean state...")
    _trigger_unload()
    time.sleep(3)

    # Step 2: Load the model
    print(f"    Loading {model}...")
    load_start = time.time()
    load_success = _trigger_load(model)
    load_time = time.time() - load_start
    result["load_time_s"] = round(load_time, 1)
    result["load_success"] = load_success

    if load_success:
        # Wait for proxy to report ready
        ready, health_data = _wait_for_ready(timeout=60)
        if ready:
            loaded_model = health_data.get("loaded_model", "unknown")
            print(f"    ✅ Loaded in {load_time:.1f}s (model: {loaded_model})")
        else:
            print(f"    ⚠️  Load succeeded but proxy not ready after {load_time:.1f}s")
            result["error"] = "proxy not ready after load"
    else:
        print(f"    ❌ Load failed after {load_time:.1f}s")
        result["error"] = "load request failed"
        return result

    # Step 3: Unload the model
    print(f"    Unloading {model}...")
    unload_start = time.time()
    unload_success = _trigger_unload()
    unload_time = time.time() - unload_start
    result["unload_time_s"] = round(unload_time, 1)
    result["unload_success"] = unload_success

    if unload_success:
        # Wait for proxy to report no server
        none, _ = _wait_for_none(timeout=60)
        if none:
            print(f"    ✅ Unloaded in {unload_time:.1f}s")
        else:
            print(f"    ⚠️  Unload initiated but proxy still active after {unload_time:.1f}s")
            result["error"] = result.get("error") or "proxy still active after unload"
    else:
        print(f"    ❌ Unload failed after {unload_time:.1f}s")
        result["error"] = result.get("error") or "unload request failed"

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="MLX Model Switch Benchmark")
    parser.add_argument("--model", help="Benchmark a single model (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--output", default=RESULTS_FILE, help="Output JSON file path")
    args = parser.parse_args()

    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║  MLX Model Switch Benchmark                                       ║")
    print(
        f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                     ║"
    )
    print("╚═══════════════════════════════════════════════════════════════════╝")

    # Check MLX proxy is reachable
    try:
        r = httpx.get(f"{MLX_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"❌ MLX proxy unhealthy: HTTP {r.status_code}")
            sys.exit(1)
        state = r.json().get("state", "unknown")
        print(f"  MLX proxy state: {state}")
    except Exception as e:
        print(f"❌ MLX proxy unreachable: {e}")
        sys.exit(1)

    # Get model list
    models = [args.model] if args.model else _get_model_list()
    if not models:
        print("❌ No models found")
        sys.exit(1)

    print(f"  Models to benchmark: {len(models)}")
    if args.dry_run:
        print("  [DRY RUN — no actual loading/unloading]")

    # Benchmark each model
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
    print("\n" + "=" * 80)
    print(f"{'Model':<55} {'Server':<12} {'Load':<8} {'Unload':<8} {'Status':<8}")
    print("=" * 80)

    for r in results:
        load_s = f"{r['load_time_s']:.1f}s" if r["load_time_s"] else "N/A"
        unload_s = f"{r['unload_time_s']:.1f}s" if r["unload_time_s"] else "N/A"
        status = "✅" if r["load_success"] and r["unload_success"] else "❌"
        if r.get("error"):
            status = f"⚠️ {r['error'][:15]}"
        print(f"{r['model']:<55} {r['server_type']:<12} {load_s:<8} {unload_s:<8} {status}")

    print("=" * 80)
    print(f"Total time: {total_time:.1f}s")

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_time_s": round(total_time, 1),
        "models_benchmarked": len(results),
        "dry_run": args.dry_run,
        "results": results,
    }
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {args.output}")

    # Send notification
    success_count = sum(1 for r in results if r["load_success"] and r["unload_success"])
    _send_notification(
        f"Benchmark complete: {success_count}/{len(results)} models tested in {total_time:.0f}s. "
        f"Results: {args.output}"
    )


if __name__ == "__main__":
    main()
