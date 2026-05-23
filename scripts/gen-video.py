#!/usr/bin/env python3
"""CLI for rapid video generation iteration via the portal video MCP."""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

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


def _notify(title: str, message: str, comfyui_url: str = "") -> None:
    """Download finished video and send to Telegram; ping Pushover as text."""
    video_path = _download_video(comfyui_url) if comfyui_url else None
    _pushover(title, message)
    if video_path:
        _telegram_send_video(video_path, caption=f"{title} — {message}")
    else:
        _telegram_text(f"{title}\n{message}")


def _download_video(comfyui_url: str) -> str | None:
    """Download video from ComfyUI local endpoint. Returns local path or None."""
    try:
        req = urllib.request.Request(comfyui_url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
                f.write(resp.read())
                return f.name
    except Exception as e:
        print(f"\n[notify] download failed: {e}", file=sys.stderr)
        return None


def _pushover(title: str, message: str) -> None:
    token = _getenv("PUSHOVER_API_TOKEN")
    user = _getenv("PUSHOVER_USER_KEY")
    if not token or not user:
        return
    try:
        payload = {"token": token, "user": user, "title": title, "message": message}
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request("https://api.pushover.net/1/messages.json", data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _telegram_send_video(path: str, caption: str = "") -> None:
    """Send a video file to all configured Telegram user IDs."""
    token = _getenv("TELEGRAM_BOT_TOKEN")
    user_ids = _getenv("TELEGRAM_USER_IDS")
    if not token or not user_ids:
        return
    boundary = "boundary_portal_video"
    for chat_id in user_ids.split(","):
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            with open(path, "rb") as f:
                video_data = f.read()
            filename = os.path.basename(path)
            parts = []
            for name, value in [("chat_id", chat_id), ("caption", caption[:1024])]:
                parts.append(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                )
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="video"; filename="{filename}"\r\n'
                f"Content-Type: video/mp4\r\n\r\n"
            )
            body = "".join(parts).encode() + video_data + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendVideo",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            urllib.request.urlopen(req, timeout=120)
        except Exception as e:
            print(f"\n[notify] Telegram sendVideo failed: {e}", file=sys.stderr)
            _telegram_text(f"Video ready (upload failed): {caption}")


def _telegram_text(message: str) -> None:
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


DEFAULT_NEGATIVE = (
    "blurry, deformed, extra limbs, bad anatomy, low quality, censored, "
    "clothes appearing, static pose, boring, overexposed, underexposed, "
    "text, watermark, logo, artifacts, distorted face, extra fingers, "
    "poorly drawn hands, mutated, ugly"
)

PREVIEW = {
    "steps": 10,
    "cfg": 6.0,
    "shift": 9.0,
    "sampler": "uni_pc",
    "width": 832,
    "height": 480,
    "frames": 9,
}

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


def build_payload(prompt: str, args: argparse.Namespace, base: dict) -> dict:
    payload: dict = {
        "prompt": prompt,
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
    return payload


def submit_payload(payload: dict) -> str:
    result = post("/tools/start_video_generation", payload)
    job_id = result.get("job_id") or result.get("id")
    if not job_id:
        print(f"ERROR: no job_id in response: {result}", file=sys.stderr)
        sys.exit(1)
    return job_id


def poll(job_id: str, label: str = "", interval: int = 30) -> str | None:
    """Poll until complete. Returns the ComfyUI video URL or None on error."""
    print(f"job_id: {job_id}", flush=True)
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
            suffix = f" [{label}]" if label else ""
            print(f"\n\nDone in {mins}m{secs:02d}s{suffix}")
            print(f"URL: {url}")
            _notify(f"Video ready{suffix}", f"Done in {mins}m{secs:02d}s", url)
            try:
                import subprocess
                subprocess.run(["open", url], check=False)
            except Exception:
                pass
            return url
        elif status == "error":
            msg = result.get("message", str(result))
            suffix = f" [{label}]" if label else ""
            print(f"\nERROR{suffix}: {msg}", file=sys.stderr)
            _notify(f"Video failed{suffix}", msg)
            return None
        else:
            spin = spinner[i % len(spinner)]
            lbl = f" {label}" if label else ""
            print(f"\r{spin}{lbl} {status} — {mins}m{secs:02d}s elapsed", end="", flush=True)
            i += 1
            time.sleep(interval)


def run_batch(prompts: list[str], args: argparse.Namespace, base: dict) -> None:
    total = len(prompts)
    eta_each = base["steps"] * 79 + (base["frames"] / 41) * 3060
    eta_total = eta_each * total
    print(f"Batch: {total} prompts  |  ~{int(eta_each/60)}min each  |  ~{int(eta_total/3600)}h{int((eta_total%3600)/60)}m total")
    print(f"Preset: steps={base['steps']} frames={base['frames']} {base['width']}x{base['height']}")
    print()

    failed = []
    for idx, prompt in enumerate(prompts, 1):
        label = f"{idx}/{total}"
        short = prompt[:60] + ("..." if len(prompt) > 60 else "")
        print(f"\n[{label}] {short}")
        payload = build_payload(prompt, args, base)
        job_id = submit_payload(payload)
        url = poll(job_id, label=label, interval=args.poll_interval)
        if url is None:
            failed.append((idx, prompt))

    print(f"\n{'='*50}")
    print(f"Batch complete: {total - len(failed)}/{total} succeeded")
    if failed:
        print("Failed:")
        for idx, p in failed:
            print(f"  [{idx}] {p[:80]}")
    _telegram_text(f"Batch done: {total - len(failed)}/{total} videos generated.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit video generation jobs to Portal and poll until done.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Presets:
  (default)  25 steps, 480p, 41 frames (~85 min)
  --preview  10 steps, 480p,  9 frames (~24 min) — batch testing
  --quality  35 steps, 720p, 41 frames (~3 hr)

Examples:
  # Single prompt — fast defaults:
  python3 scripts/gen-video.py "your prompt"

  # Batch from file — one prompt per line, ~24 min each:
  python3 scripts/gen-video.py --batch prompts.txt --preview

  # Quality single run:
  python3 scripts/gen-video.py "your prompt" --quality

  # Override specific params:
  python3 scripts/gen-video.py "your prompt" --steps 30 --cfg 6.2 --shift 9.8

  # Fixed seed for reproducible comparisons:
  python3 scripts/gen-video.py "your prompt" --seed 42

  # Submit and exit — poll manually later:
  python3 scripts/gen-video.py "your prompt" --no-wait

  # Poll an existing job:
  python3 scripts/gen-video.py --status <job_id>
""",
    )
    parser.add_argument("prompt", nargs="?", help="Text prompt for video generation")
    parser.add_argument("--preview", action="store_true", help="Preview preset: 10 steps, 9 frames (~24 min) — ideal for batch testing")
    parser.add_argument("--quality", action="store_true", help="Quality preset: 35 steps, 720p, 41 frames (~3 hr)")
    parser.add_argument("--batch", metavar="FILE", help="Run all prompts from FILE (one per line) sequentially")
    parser.add_argument("--steps", type=int, default=None, help="Inference steps")
    parser.add_argument("--cfg", type=float, default=None, help="CFG scale (range 5.5–7.0)")
    parser.add_argument("--frames", type=int, default=None, help="Number of frames")
    parser.add_argument("--width", type=int, default=None, help="Width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Height in pixels")
    parser.add_argument("--shift", type=float, default=None, help="Sample shift (range 8–11, higher = more motion)")
    parser.add_argument("--sampler", type=str, default=None, help="Sampler name (default: uni_pc)")
    parser.add_argument("--negative", type=str, default=None, metavar="TEXT", help="Override negative prompt")
    parser.add_argument("--seed", type=int, default=None, help="Seed (-1 = random)")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between status polls (default: 30)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and exit immediately, printing job_id")
    parser.add_argument("--status", metavar="JOB_ID", help="Poll an existing job by ID")

    args = parser.parse_args()

    if args.status:
        poll(args.status, interval=args.poll_interval)
        return

    if args.preview and args.quality:
        parser.error("--preview and --quality are mutually exclusive")

    base = PREVIEW if args.preview else (QUALITY if args.quality else DEFAULTS)
    preset_label = "preview" if args.preview else ("quality" if args.quality else "fast")

    if args.batch:
        try:
            with open(args.batch) as f:
                prompts = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except OSError as e:
            parser.error(f"Cannot read batch file: {e}")
        if not prompts:
            parser.error("Batch file is empty")
        run_batch(prompts, args, base)
        return

    if not args.prompt:
        parser.error("prompt is required (or use --batch FILE or --status JOB_ID)")

    steps = args.steps or base["steps"]
    cfg = args.cfg or base["cfg"]
    shift = args.shift or base["shift"]
    w = args.width or base["width"]
    h = args.height or base["height"]
    frames = args.frames or base["frames"]

    print(f"Submitting [{preset_label}]: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  steps={steps}  cfg={cfg}  shift={shift}  {w}x{h}  frames={frames}")

    payload = build_payload(args.prompt, args, base)
    job_id = submit_payload(payload)

    if args.no_wait:
        print(f"job_id: {job_id}")
        print(f"Poll later: python3 scripts/gen-video.py --status {job_id}")
        return

    poll(job_id, interval=args.poll_interval)


if __name__ == "__main__":
    main()
