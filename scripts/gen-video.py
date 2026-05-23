#!/usr/bin/env python3
"""CLI for rapid video generation iteration via the portal video MCP."""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

MCP_URL = "http://localhost:8911"


def post(path: str, payload: dict) -> dict:
    data = json.dumps({"arguments": payload}).encode()
    req = urllib.request.Request(
        f"{MCP_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def submit(args: argparse.Namespace) -> str:
    payload: dict = {"prompt": args.prompt}
    if args.frames is not None:
        payload["frames"] = args.frames
    if args.steps is not None:
        payload["steps"] = args.steps
    if args.cfg is not None:
        payload["cfg"] = args.cfg
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.shift is not None:
        payload["shift"] = args.shift
    if args.sampler is not None:
        payload["sampler"] = args.sampler
    if args.negative:
        payload["negative_prompt"] = args.negative
    if args.width is not None:
        payload["width"] = args.width
    if args.height is not None:
        payload["height"] = args.height

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
            # Try to open with macOS open
            try:
                import subprocess
                subprocess.run(["open", url], check=False)
            except Exception:
                pass
            return
        elif status == "error":
            print(f"\nERROR: {result.get('message', result)}", file=sys.stderr)
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
        epilog="""
Examples:
  # Balanced quality run (recommended starting point):
  python3 scripts/gen-video.py "your prompt" --steps 30 --cfg 6.2 --shift 9.8

  # Fast iteration at 480p (25 steps, ~20 min):
  python3 scripts/gen-video.py "your prompt" --steps 25 --cfg 6.0 --shift 9.0 --width 832 --height 480

  # Best quality (35 steps, 720p):
  python3 scripts/gen-video.py "your prompt" --steps 35 --cfg 6.5 --shift 10.0

  # Maximum motion (higher shift):
  python3 scripts/gen-video.py "your prompt" --steps 32 --cfg 6.0 --shift 10.5

  # With negative prompt:
  python3 scripts/gen-video.py "your prompt" --negative "blurry, deformed, static pose, censored, watermark"

  # Fixed seed for reproducible comparisons:
  python3 scripts/gen-video.py "your prompt" --steps 30 --seed 42

  # Submit and exit — poll manually later:
  python3 scripts/gen-video.py "your prompt" --no-wait
""",
    )
    parser.add_argument("prompt", help="Text prompt for video generation")
    parser.add_argument("--steps", type=int, default=None, help="Inference steps (default: 30)")
    parser.add_argument("--cfg", type=float, default=None, help="CFG scale (default: 6.2; range 5.5–7.0)")
    parser.add_argument("--frames", type=int, default=None, help="Number of frames (default: 41 ≈ 5s at 8fps)")
    parser.add_argument("--width", type=int, default=None, help="Width in pixels (default: 1280)")
    parser.add_argument("--height", type=int, default=None, help="Height in pixels (default: 720)")
    parser.add_argument("--shift", type=float, default=None, help="Sample shift (default: 9.8; range 8–11, higher = more motion)")
    parser.add_argument("--sampler", type=str, default=None, help="Sampler name (default: unipc; dpm++_2m also works)")
    parser.add_argument("--negative", type=str, default=None, metavar="TEXT", help="Negative prompt")
    parser.add_argument("--seed", type=int, default=None, help="Seed (-1 = random)")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between status polls (default: 30)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and print job_id, then exit immediately")
    parser.add_argument("--status", metavar="JOB_ID", help="Poll an existing job by ID instead of submitting")

    args = parser.parse_args()

    if args.status:
        poll(args.status, args.poll_interval)
        return

    print(f"Submitting: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    parts = []
    if args.steps is not None:
        parts.append(f"steps={args.steps}")
    if args.cfg is not None:
        parts.append(f"cfg={args.cfg}")
    if args.shift is not None:
        parts.append(f"shift={args.shift}")
    if args.sampler is not None:
        parts.append(f"sampler={args.sampler}")
    if args.frames is not None:
        parts.append(f"frames={args.frames}")
    if args.width is not None or args.height is not None:
        w = args.width or 1280
        h = args.height or 720
        parts.append(f"{w}×{h}")
    if args.seed is not None:
        parts.append(f"seed={args.seed}")
    if parts:
        print("  " + "  ".join(parts))

    job_id = submit(args)

    if args.no_wait:
        print(f"job_id: {job_id}")
        print(f"Poll later: python3 scripts/gen-video.py --status {job_id}")
        return

    poll(job_id, args.poll_interval)


if __name__ == "__main__":
    main()
