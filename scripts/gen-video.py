#!/usr/bin/env python3
"""CLI for rapid video generation iteration via the portal video MCP."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

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


_env_cache: dict[str, str] = {}


def _getenv(key: str) -> str:
    if not _env_cache:
        _env_cache.update(_load_env_file())
    return os.environ.get(key) or _env_cache.get(key, "")


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
    "steps": 30,
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
    "width": 832,
    "height": 480,
    "frames": 41,
}

# 720p at 35 steps + 41 frames is ~15-17 hours on M-series (observed 2026-05-23).
# Use --overnight only when you have a full day to spare.
OVERNIGHT = {
    "steps": 35,
    "cfg": 6.5,
    "shift": 10.0,
    "sampler": "uni_pc",
    "width": 1280,
    "height": 720,
    "frames": 41,
}

# ── Wan 2.2 presets (PHASE_PLAN_MODEL_REFRESH_V7_V2) ─────────────────────────
# Requires: ./launch.sh pull-wan22 + ComfyUI running
# Use: python3 scripts/gen-video.py "prompt" --preset wan22-fast
WAN22_PRESETS: dict[str, dict] = {
    "wan22-fast": {
        "model": "wan22-t2v-a14b",
        "steps": 20,
        "cfg": 6.0,
        "shift": 8.0,
        "sampler": "uni_pc",
        "width": 832,
        "height": 480,
        "frames": 41,
        "description": "Wan 2.2 T2V-A14B fast — 20 steps, 480p, text-to-video",
    },
    "wan22-quality": {
        "model": "wan22-t2v-a14b",
        "steps": 35,
        "cfg": 6.0,
        "shift": 8.0,
        "sampler": "uni_pc",
        "width": 1280,
        "height": 720,
        "frames": 41,
        "description": "Wan 2.2 T2V-A14B quality — 35 steps, 720p, text-to-video",
    },
    "wan22-ti2v": {
        "model": "wan22-ti2v-5b",
        "steps": 20,
        "cfg": 5.0,
        "shift": 8.0,
        "sampler": "uni_pc",
        "width": 1280,
        "height": 704,
        "frames": 121,
        "description": "Wan 2.2 TI2V-5B — image-to-video, ~5s clip (requires --image-url)",
        "_requires_image": True,
    },
    "wan22-s2v": {
        "model": "wan22-s2v-14b",
        "steps": 20,
        "cfg": 6.0,
        "shift": 8.0,
        "sampler": "uni_pc",
        "width": 640,
        "height": 640,
        "frames": 77,
        "description": "Wan 2.2 S2V-14B — speech-to-video (requires --image-url and --audio-url)",
        "_requires_image": True,
        "_requires_audio": True,
    },
    "wan22-animate": {
        "model": "wan22-animate-14b",
        "steps": 35,
        "cfg": 6.0,
        "shift": 8.0,
        "sampler": "uni_pc",
        "width": 1280,
        "height": 720,
        "frames": 41,
        "description": "Wan 2.2 Animate-14B — character animation (stub, requires custom ComfyUI nodes)",
    },
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
    model = getattr(args, "model", None) or base.get("model", "")
    if model:
        payload["model"] = model
    if args.seed is not None:
        payload["seed"] = args.seed
    if getattr(args, "image_url", None):
        payload["image_url"] = args.image_url
    if getattr(args, "audio_url", None):
        payload["audio_url"] = args.audio_url
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


def _eta_seconds(steps: int, frames: int, width: int, height: int) -> int:
    """Estimate generation time in seconds on Apple Silicon MPS (Wan 2.1/2.2 backends).

    Calibrated from observed run 2026-05-23:
      Wan 2.1 NSFW, 35 steps, 41 frames, 1280×720 → 1578s/step → 15.4h total
    Back-solving: ref_step_s = 55320 / (35 × 10.52) ≈ 150s at 832×480 9-frame reference.
    Scales linearly with (width×height) and (frames).
    """
    ref_step_s = 150.0         # seconds/step at reference config (832×480, 9 frames)
    ref_pixels = 832 * 480
    ref_frames = 9
    res_scale = (width * height) / ref_pixels
    frame_scale = frames / ref_frames
    per_step = ref_step_s * res_scale * frame_scale
    return int(steps * per_step) + 120


def run_batch(prompts: list[str], args: argparse.Namespace, base: dict) -> None:
    total = len(prompts)
    w = base.get("width", 832)
    h = base.get("height", 480)
    eta_each = _eta_seconds(base["steps"], base["frames"], w, h)
    eta_total = eta_each * total
    print(f"Batch: {total} prompts  |  ~{int(eta_each/60)}min each  |  ~{int(eta_total/3600)}h{int((eta_total%3600)/60)}m total")
    print(f"Preset: steps={base['steps']} frames={base['frames']} {w}x{h}")
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
    wan22_preset_names = sorted(WAN22_PRESETS.keys())
    wan22_preset_help = "\n".join(
        f"  {k:20s} {v['description']}" for k, v in WAN22_PRESETS.items()
    )
    parser = argparse.ArgumentParser(
        description="Submit video generation jobs to Portal and poll until done.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Presets (times are approximate on Apple Silicon, Wan 2.1 14B NSFW):
  --preview   20 steps, 480p,  9 frames (~52 min) — prompt quality check
  (default)   25 steps, 480p, 41 frames (~4.8 hr) — standard run
  --quality   35 steps, 480p, 41 frames (~6.7 hr) — best quality at 480p
  --overnight 35 steps, 720p, 41 frames (~15-17 hr) — leave running overnight

Wan 2.2 presets (--preset NAME, requires pull-wan22 + ComfyUI template export):
{wan22_preset_help}

Examples:
  # Single prompt — standard run:
  python3 scripts/gen-video.py "your prompt"

  # Prompt quality check (fastest, ~52 min, confirms content/composition):
  python3 scripts/gen-video.py "your prompt" --preview

  # Batch from file — one prompt per line:
  python3 scripts/gen-video.py --batch prompts.txt --preview

  # Quality single run at 480p:
  python3 scripts/gen-video.py "your prompt" --quality

  # Full 720p — leave running overnight:
  python3 scripts/gen-video.py "your prompt" --overnight

  # Wan 2.2 text-to-video (fast):
  python3 scripts/gen-video.py "your prompt" --preset wan22-fast

  # Wan 2.2 image-to-video (start frame → animated clip):
  python3 scripts/gen-video.py "your prompt" --preset wan22-ti2v --image-url /path/to/frame.png

  # Wan 2.2 speech-to-video (audio drives motion):
  python3 scripts/gen-video.py "your prompt" --preset wan22-s2v --image-url /path/to/frame.png --audio-url /path/to/audio.mp3

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
    parser.add_argument("--preview", action="store_true", help="Preview preset: 20 steps, 480p, 9 frames (~52 min) — prompt quality check")
    parser.add_argument("--quality", action="store_true", help="Quality preset: 35 steps, 480p, 41 frames (~6.7 hr) — best quality at 480p")
    parser.add_argument("--overnight", action="store_true", help="Overnight preset: 35 steps, 720p, 41 frames (~15-17 hr) — leave running overnight")
    parser.add_argument("--preset", choices=wan22_preset_names, metavar="PRESET",
                        help=f"Wan 2.2 preset. Choices: {', '.join(wan22_preset_names)}")
    parser.add_argument("--model", type=str, default=None, metavar="MODEL_ID",
                        help="Override model ID (e.g. wan22-t2v-a14b, wan22-ti2v-5b)")
    parser.add_argument("--image-url", type=str, default=None, metavar="URL",
                        help="Start-frame image URL or local path (required for wan22-ti2v and wan22-s2v)")
    parser.add_argument("--audio-url", type=str, default=None, metavar="URL",
                        help="Reference audio URL or local path (required for wan22-s2v)")
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

    explicit_flags = [args.preview, args.quality, args.overnight]
    if sum(bool(f) for f in explicit_flags) > 1:
        parser.error("--preview, --quality, and --overnight are mutually exclusive")
    if args.preset and any(explicit_flags):
        parser.error("--preset is mutually exclusive with --preview / --quality / --overnight")

    if args.preset:
        wan22 = WAN22_PRESETS[args.preset]
        base = {k: v for k, v in wan22.items() if k not in ("model", "description", "_requires_image", "_requires_audio")}
        if not args.model:
            args.model = wan22["model"]
        preset_label = args.preset
        if wan22.get("_requires_image") and not args.image_url:
            parser.error(f"--preset {args.preset} requires --image-url")
        if wan22.get("_requires_audio") and not args.audio_url:
            parser.error(f"--preset {args.preset} requires --audio-url")
    elif args.preview:
        base = PREVIEW
        preset_label = "preview"
    elif args.quality:
        base = QUALITY
        preset_label = "quality"
    elif args.overnight:
        base = OVERNIGHT
        preset_label = "overnight"
    else:
        base = DEFAULTS
        preset_label = "fast"

    if args.batch:
        try:
            with open(args.batch) as f:
                prompts = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
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

    model_tag = f"  model={args.model}" if getattr(args, "model", None) else ""
    print(f"Submitting [{preset_label}]: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  steps={steps}  cfg={cfg}  shift={shift}  {w}x{h}  frames={frames}{model_tag}")

    payload = build_payload(args.prompt, args, base)
    job_id = submit_payload(payload)

    if args.no_wait:
        print(f"job_id: {job_id}")
        print(f"Poll later: python3 scripts/gen-video.py --status {job_id}")
        return

    poll(job_id, interval=args.poll_interval)


if __name__ == "__main__":
    main()
