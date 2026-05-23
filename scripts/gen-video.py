#!/usr/bin/env python3
"""CLI for rapid video generation iteration via the portal video MCP."""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

MCP_URL = "http://localhost:8911"


def _load_env_file() -> dict:
    """Load key=value pairs from .env in the repo root (best-effort)."""
    env: dict = {}
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(os.path.abspath(env_path)) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except OSError:
        pass
    return env


def _getenv(key: str, _cache: dict = {}) -> str:
    if not _cache:
        _cache.update(_load_env_file())
    return os.environ.get(key) or _cache.get(key, "")


def _notify(title: str, message: str, url: str = "") -> None:
    """Fire-and-forget Pushover + Telegram notifications. Errors are ignored."""
    _pushover(title, message, url)
    _telegram(f"{title}\n{message}" + (f"\n{url}" if url else ""))


def _pushover(title: str, message: str, url: str = "") -> None:
    token = _getenv("PUSHOVER_API_TOKEN")
    user = _getenv("PUSHOVER_USER_KEY")
    if not token or not user:
        return
    payload: dict = {"token": token, "user": user, "title": title, "message": message}
    if url:
        payload["url"] = url
        payload["url_title"] = "Open video"
    try:
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _telegram(message: str) -> None:
    token = _getenv("TELEGRAM_BOT_TOKEN")
    user_ids = _getenv("TELEGRAM_USER_IDS")
    if not token or not user_ids:
        return
    for chat_id in user_ids.split(","):
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            payload = json.dumps({"chat_id": chat_id, "text": message}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass


import urllib.parse

DEFAULT_NEGATIVE = (
    "blurry, deformed, extra limbs, bad anatomy, low quality, censored, "
    "clothes appearing, static pose, boring, overexposed, underexposed, "
    "text, watermark, logo, artifacts, distorted face, extra fingers, "
    "poorly drawn hands, mutated, ugly"
)

# Fast-iteration defaults — optimised for quick turnaround while dialling in prompts.
# Use --quality to switch to the quality preset (35 steps, 720p).
DEFAULTS = {
    "steps": 25,
    "cfg": 6.0,
    "shift": 9.0,
    "sampler": "uni_pc",
    "width": 832,
    "height": 480,
    "frames": 41,
}

QUALITY = {
    "steps": 35,
    "cfg": 6.5,
    "shift": 10.0,
    "sampler": "uni_pc",
    "width": 1280,
    "height": 720,
    "frames": 41,
}


def post(path: str, payload: dict) -> dict:
    data = json.dumps({"arguments": payload}).encode()
    req = urllib.request.Request(
        f"{MCP_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def submit(args: argparse.Namespace, base: dict) -> str:
    payload: dict = {
        "prompt": args.prompt,
        "negative_prompt": args.negative if args.negative is not None else DEFAULT_NEGATIVE,
        "steps": args.steps if args.steps is not None else base["steps"],
        "cfg": args.cfg if args.cfg is not None else base["cfg"],
        "shift": args.shift if args.shift is not None else base["shift"],
        "sampler": args.sampler if args.sampler is not None else base["sampler"],
        "width": args.width if args.width is not None else base["width"],
        "height": args.height if args.height is not None else base["height"],
        "frames": args.frames if args.frames is not None else base["frames"],
    }
    if args.seed is not None:
        payload["seed"] = args.seed

    result = post("/tools/start_video_generation", payload)
    job_id = result.get("job_id") or result.get("id")
    if not job_id:
        print(f"ERROR: no job_id in response: {result}", file=sys.stderr)
        sys.exit(1)
    return job_id


def poll(job_id: str, interval: int = 30) -> None:
    print(f"job_id: {job_id}", flush=True)
    print(f"ComfyUI: http://localhost:8188", flush=True)
    spinner = ["|", "/", "-", "\\"]
    i = 0
    start = time.time()
    while True:
        try:
            result = post("/tools/get_video_status", {"job_id": job_id})
        except Exception as e:
            print(f"\nPoll error: {e}", file=sys.stderr)
            time.sleep(interval)
            continue

        status = result.get("status", "unknown")
        elapsed = int(time.time() - start)
        mins, secs = divmod(elapsed, 60)

        if status == "complete":
            url = result.get("url", "")
            print(f"\n\nDone in {mins}m{secs:02d}s")
            print(f"URL: {url}")
            _notify("Video ready", f"Done in {mins}m{secs:02d}s", url)
            try:
                import subprocess
                subprocess.run(["open", url], check=False)
            except Exception:
                pass
            return
        elif status == "error":
            msg = result.get("message", str(result))
            print(f"\nERROR: {msg}", file=sys.stderr)
            _notify("Video failed", msg)
            sys.exit(1)
        else:
            spin = spinner[i % len(spinner)]
            print(f"\r{spin} {status} — {mins}m{secs:02d}s elapsed", end="", flush=True)
            i += 1
            time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit a video generation job to Portal and poll until done.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Defaults (fast iteration — ~20 min):
  steps={DEFAULTS['steps']}  cfg={DEFAULTS['cfg']}  shift={DEFAULTS['shift']}
  resolution={DEFAULTS['width']}x{DEFAULTS['height']}  sampler={DEFAULTS['sampler']}
  negative prompt: baked in (override with --negative "...")

Examples:
  # Fast prompt iteration (default):
  python3 scripts/gen-video.py "your prompt"

  # Quality run (720p, 35 steps):
  python3 scripts/gen-video.py "your prompt" --quality

  # Override specific params:
  python3 scripts/gen-video.py "your prompt" --steps 30 --cfg 6.2 --shift 9.8

  # Maximum motion:
  python3 scripts/gen-video.py "your prompt" --shift 10.5

  # Fixed seed for reproducible comparisons:
  python3 scripts/gen-video.py "your prompt" --seed 42

  # Override negative prompt:
  python3 scripts/gen-video.py "your prompt" --negative "blurry, watermark"

  # Submit and exit — poll manually later:
  python3 scripts/gen-video.py "your prompt" --no-wait

  # Poll an existing job:
  python3 scripts/gen-video.py --status <job_id>
""",
    )
    parser.add_argument("prompt", nargs="?", help="Text prompt for video generation")
    parser.add_argument("--quality", action="store_true", help="Use quality preset (35 steps, 720p) instead of fast defaults")
    parser.add_argument("--steps", type=int, default=None, help=f"Inference steps (fast default: {DEFAULTS['steps']})")
    parser.add_argument("--cfg", type=float, default=None, help=f"CFG scale (fast default: {DEFAULTS['cfg']}; range 5.5–7.0)")
    parser.add_argument("--frames", type=int, default=None, help=f"Number of frames (default: {DEFAULTS['frames']} ≈ 5s at 8fps)")
    parser.add_argument("--width", type=int, default=None, help=f"Width in pixels (fast default: {DEFAULTS['width']})")
    parser.add_argument("--height", type=int, default=None, help=f"Height in pixels (fast default: {DEFAULTS['height']})")
    parser.add_argument("--shift", type=float, default=None, help=f"Sample shift (fast default: {DEFAULTS['shift']}; range 8–11, higher = more motion)")
    parser.add_argument("--sampler", type=str, default=None, help="Sampler name (default: uni_pc; dpmpp_2m also works)")
    parser.add_argument("--negative", type=str, default=None, metavar="TEXT", help="Override negative prompt (default: baked-in quality negative)")
    parser.add_argument("--seed", type=int, default=None, help="Seed (-1 = random)")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between status polls (default: 30)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and print job_id, then exit immediately")
    parser.add_argument("--status", metavar="JOB_ID", help="Poll an existing job by ID instead of submitting")

    args = parser.parse_args()

    if args.status:
        poll(args.status, args.poll_interval)
        return

    if not args.prompt:
        parser.error("prompt is required when not using --status")

    base = QUALITY if args.quality else DEFAULTS
    preset_label = "quality" if args.quality else "fast"

    print(f"Submitting [{preset_label}]: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    parts = [
        f"steps={args.steps or base['steps']}",
        f"cfg={args.cfg or base['cfg']}",
        f"shift={args.shift or base['shift']}",
        f"{args.width or base['width']}x{args.height or base['height']}",
    ]
    if args.seed is not None:
        parts.append(f"seed={args.seed}")
    print("  " + "  ".join(parts))

    job_id = submit(args, base)

    if args.no_wait:
        print(f"job_id: {job_id}")
        print(f"Poll later: python3 scripts/gen-video.py --status {job_id}")
        return

    poll(job_id, args.poll_interval)


if __name__ == "__main__":
    main()
