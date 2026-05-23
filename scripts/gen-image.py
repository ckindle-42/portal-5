#!/usr/bin/env python3
"""CLI for rapid image generation iteration via the Portal ComfyUI MCP."""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

MCP_URL = "http://localhost:8910"


def _load_env_file() -> dict:
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


def _notify(title: str, message: str) -> None:
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


DEFAULTS = {
    "model": "flux",
    "steps": 20,
    "cfg": 4.5,
    "width": 1024,
    "height": 1024,
}

QUALITY = {
    "model": "flux",
    "steps": 30,
    "cfg": 5.0,
    "width": 1328,
    "height": 1328,
}

FAST = {
    "model": "flux",
    "steps": 4,
    "cfg": 1.0,
    "width": 1024,
    "height": 1024,
}

# ── Qwen-Image-2512 presets (PHASE_PLAN_MODEL_REFRESH_V7_V2) ─────────────────
# Requires: ./launch.sh pull-qwen-image (~30GB) + ComfyUI template export
# See: docs/COMFYUI_SETUP.md § Qwen-Image-2512
QWEN_IMAGE_PRESETS: dict[str, dict] = {
    "qwen-2512-quality": {
        "model": "qwen-image-2512",
        "steps": 50,
        "cfg": 4.0,
        "width": 1328,
        "height": 1328,
        "description": "Qwen-Image-2512 high quality — 50 steps, CFG 4.0, ~3-5 min on M4 Pro. Best for: text rendering, posters, typography.",
    },
    "qwen-2512-fast": {
        "model": "qwen-image-2512-lightning",
        "steps": 8,
        "cfg": 1.0,
        "width": 1328,
        "height": 1328,
        "description": "Qwen-Image-2512 Lightning — 8 steps, CFG-distilled, ~30s on M4 Pro.",
    },
    "qwen-edit-2511": {
        "model": "qwen-image-edit-2511",
        "steps": 50,
        "cfg": 4.0,
        "width": 1328,
        "height": 1328,
        "description": "Qwen-Image-Edit-2511 — instruction-based image editing. NEW: no FLUX equivalent.",
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
        "steps": args.steps if args.steps is not None else base["steps"],
        "cfg": args.cfg if args.cfg is not None else base["cfg"],
        "width": args.width if args.width is not None else base["width"],
        "height": args.height if args.height is not None else base["height"],
        "model": getattr(args, "model_override", None) or base.get("model", "flux"),
    }
    if args.negative:
        payload["negative_prompt"] = args.negative
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.lora:
        payload["lora"] = args.lora
    return payload


def submit_payload(payload: dict) -> str:
    result = post("/tools/start_image_generation", payload)
    job_id = result.get("job_id") or result.get("id")
    if not job_id:
        print(f"ERROR: no job_id in response: {result}", file=sys.stderr)
        sys.exit(1)
    return job_id


def poll(job_id: str, label: str = "", interval: int = 10) -> str | None:
    print(f"job_id: {job_id}", flush=True)
    spinner = ["|", "/", "-", "\\"]
    i = 0
    start = time.time()
    while True:
        try:
            result = post("/tools/get_image_status", {"job_id": job_id})
        except Exception as e:
            print(f"\nPoll error: {e}", file=sys.stderr)
            time.sleep(interval)
            continue

        status = result.get("status", "unknown")
        elapsed = int(time.time() - start)
        mins, secs = divmod(elapsed, 60)

        if status == "complete":
            urls = result.get("urls", [])
            url = urls[0] if urls else result.get("url", "")
            suffix = f" [{label}]" if label else ""
            print(f"\n\nDone in {mins}m{secs:02d}s{suffix}")
            print(f"URL: {url}")
            _notify(f"Image ready{suffix}", f"Done in {mins}m{secs:02d}s")
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
            _notify(f"Image failed{suffix}", msg)
            return None
        else:
            spin = spinner[i % len(spinner)]
            lbl = f" {label}" if label else ""
            print(f"\r{spin}{lbl} {status} — {mins}m{secs:02d}s elapsed", end="", flush=True)
            i += 1
            time.sleep(interval)


def main() -> None:
    qwen_names = sorted(QWEN_IMAGE_PRESETS.keys())
    qwen_help = "\n".join(
        f"  {k:25s} {v['description']}" for k, v in QWEN_IMAGE_PRESETS.items()
    )
    parser = argparse.ArgumentParser(
        description="Submit image generation jobs to Portal ComfyUI MCP and poll until done.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Presets:
  (default)   FLUX schnell — 20 steps, 1024x1024
  --quality   FLUX schnell — 30 steps, 1328x1328
  --fast      FLUX schnell — 4 steps, 1024x1024

Qwen-Image-2512 presets (--preset NAME, requires pull-qwen-image + ComfyUI template export):
{qwen_help}

Examples:
  # Default FLUX:
  python3 scripts/gen-image.py "a photorealistic mountain at sunset"

  # Quality preset:
  python3 scripts/gen-image.py "your prompt" --quality

  # Qwen-Image text rendering:
  python3 scripts/gen-image.py "a poster for a jazz concert in blue and gold" --preset qwen-2512-quality

  # Fast iteration:
  python3 scripts/gen-image.py "your prompt" --preset qwen-2512-fast

  # Override params:
  python3 scripts/gen-image.py "your prompt" --steps 25 --cfg 5.0 --width 1024 --height 768

  # Fixed seed:
  python3 scripts/gen-image.py "your prompt" --seed 42

  # Submit and exit — poll manually later:
  python3 scripts/gen-image.py "your prompt" --no-wait

  # Poll an existing job:
  python3 scripts/gen-image.py --status <job_id>
""",
    )
    parser.add_argument("prompt", nargs="?", help="Text prompt for image generation")
    parser.add_argument("--quality", action="store_true", help="Quality preset: 30 steps, 1328x1328")
    parser.add_argument("--fast", action="store_true", help="Fast preset: 4 steps, 1024x1024")
    parser.add_argument("--preset", choices=qwen_names, metavar="PRESET",
                        help=f"Qwen-Image preset. Choices: {', '.join(qwen_names)}")
    parser.add_argument("--model", dest="model_override", type=str, default=None, metavar="MODEL_ID",
                        help="Override model ID (e.g. qwen-image-2512, qwen-image-edit-2511, sdxl)")
    parser.add_argument("--steps", type=int, default=None, help="Inference steps")
    parser.add_argument("--cfg", type=float, default=None, help="CFG / guidance scale")
    parser.add_argument("--width", type=int, default=None, help="Image width in pixels")
    parser.add_argument("--height", type=int, default=None, help="Image height in pixels")
    parser.add_argument("--negative", type=str, default=None, metavar="TEXT", help="Negative prompt")
    parser.add_argument("--seed", type=int, default=None, help="Seed (-1 = random)")
    parser.add_argument("--lora", type=str, default=None, metavar="FILE", help="LoRA filename to apply")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between status polls (default: 10)")
    parser.add_argument("--no-wait", action="store_true", help="Submit and exit immediately, printing job_id")
    parser.add_argument("--status", metavar="JOB_ID", help="Poll an existing job by ID")

    args = parser.parse_args()

    if args.status:
        poll(args.status, interval=args.poll_interval)
        return

    if sum([bool(args.preset), args.quality, args.fast]) > 1:
        parser.error("--preset, --quality, --fast are mutually exclusive")

    if args.preset:
        qwen = QWEN_IMAGE_PRESETS[args.preset]
        base = {k: v for k, v in qwen.items() if k != "description"}
        preset_label = args.preset
    elif args.quality:
        base = QUALITY
        preset_label = "quality"
    elif args.fast:
        base = FAST
        preset_label = "fast"
    else:
        base = DEFAULTS
        preset_label = "default"

    if not args.prompt:
        parser.error("prompt is required (or use --status JOB_ID)")

    steps = args.steps or base["steps"]
    cfg = args.cfg or base["cfg"]
    w = args.width or base["width"]
    h = args.height or base["height"]
    model_tag = args.model_override or base.get("model", "flux")
    print(f"Submitting [{preset_label}]: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  model={model_tag}  steps={steps}  cfg={cfg}  {w}x{h}")

    payload = build_payload(args.prompt, args, base)
    job_id = submit_payload(payload)

    if args.no_wait:
        print(f"job_id: {job_id}")
        print(f"Poll later: python3 scripts/gen-image.py --status {job_id}")
        return

    poll(job_id, interval=args.poll_interval)


if __name__ == "__main__":
    main()
