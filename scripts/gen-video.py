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
  # Quick 20-step test (fastest feedback):
  python3 scripts/gen-video.py "your prompt here" --steps 20

  # Quality run:
  python3 scripts/gen-video.py "your prompt here" --steps 50 --cfg 7.5

  # Fixed seed for reproducible comparisons:
  python3 scripts/gen-video.py "your prompt here" --steps 30 --seed 42

  # Longer clip (81 frames = ~10s at 8fps):
  python3 scripts/gen-video.py "your prompt here" --steps 20 --frames 81

  # Submit and exit — poll manually later:
  python3 scripts/gen-video.py "your prompt here" --no-wait
""",
    )
    parser.add_argument("prompt", help="Text prompt for video generation")
    parser.add_argument("--steps", type=int, default=None, help="Inference steps (default: MCP default, currently 50)")
    parser.add_argument("--cfg", type=float, default=None, help="CFG scale (default: 6.0)")
    parser.add_argument("--frames", type=int, default=None, help="Number of frames (default: MCP default, currently 41)")
    parser.add_argument("--seed", type=int, default=None, help="Seed (-1 = random)")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between status polls (default: 30)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and print job_id, then exit immediately")
    parser.add_argument("--status", metavar="JOB_ID", help="Poll an existing job by ID instead of submitting")

    args = parser.parse_args()

    if args.status:
        poll(args.status, args.poll_interval)
        return

    print(f"Submitting: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    if args.steps:
        print(f"  steps={args.steps}", end="")
    if args.cfg:
        print(f"  cfg={args.cfg}", end="")
    if args.frames:
        print(f"  frames={args.frames}", end="")
    if args.seed:
        print(f"  seed={args.seed}", end="")
    print()

    job_id = submit(args)

    if args.no_wait:
        print(f"job_id: {job_id}")
        print(f"Poll later: python3 scripts/gen-video.py --status {job_id}")
        return

    poll(job_id, args.poll_interval)


if __name__ == "__main__":
    main()
