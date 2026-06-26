"""Section C10 — Output validation."""
from __future__ import annotations

import httpx
import time

from ._common import (
    COMFYUI_URL,
    _comfyui_get,
    record,
)


async def run() -> None:
    """Output validation."""
    """Validate that ComfyUI output files exist and have correct MIME types.

    Checks the most recent entries in ComfyUI /history, fetches the file via
    /view, and validates file size and format.
    """
    print("\n━━━ C10. OUTPUT VALIDATION ━━━")
    sec = "C10"

    t0 = time.time()
    code, history = await _comfyui_get("/history?max_items=10")
    if code != 200 or not isinstance(history, dict) or not history:
        record(
            sec,
            "C10-01",
            "ComfyUI /history has recent outputs",
            "WARN",
            f"HTTP {code} or empty history",
            t0=t0,
        )
        return

    # Collect all outputs from recent history
    images_found: list[dict] = []
    videos_found: list[dict] = []
    video_extensions = {".mp4", ".webm", ".gif", ".avi", ".mov"}
    for entry in history.values():
        for node_outputs in entry.get("outputs", {}).values():
            # ComfyUI stores images in "images" key
            for item in node_outputs.get("images", []):
                fname = item.get("filename", "")
                if any(fname.lower().endswith(ext) for ext in video_extensions):
                    videos_found.append(item)
                else:
                    images_found.append(item)
            # Some nodes store videos in "videos" or "gifs" keys
            for item in node_outputs.get("videos", node_outputs.get("gifs", [])):
                videos_found.append(item)

    record(
        sec,
        "C10-01",
        "Recent outputs in ComfyUI /history",
        "PASS" if (images_found or videos_found) else "WARN",
        f"{len(images_found)} image(s), {len(videos_found)} video(s) in recent history",
        t0=t0,
    )

    # Validate most recent image
    if images_found:
        img = images_found[-1]
        fname = img.get("filename", "")
        subfolder = img.get("subfolder", "")
        ftype = img.get("type", "output")
        t0 = time.time()
        params = f"filename={fname}&subfolder={subfolder}&type={ftype}"
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{COMFYUI_URL}/view?{params}")
                size_kb = len(r.content) / 1024
                content_type = r.headers.get("content-type", "unknown")
                is_image = "image" in content_type or fname.endswith((".png", ".jpg", ".webp"))
                record(
                    sec,
                    "C10-02",
                    "Latest image accessible and valid",
                    "PASS" if r.status_code == 200 and size_kb > 1 and is_image else "WARN",
                    f"{fname}: {size_kb:.1f}KB, {content_type}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, "C10-02", "Latest image accessible and valid", "WARN", str(e)[:120], t0=t0)
    else:
        record(
            sec,
            "C10-02",
            "Latest image accessible and valid",
            "INFO",
            "no images in recent history",
            t0=None,
        )

    # Validate most recent video
    if videos_found:
        vid = videos_found[-1]
        fname = vid.get("filename", "")
        subfolder = vid.get("subfolder", "")
        ftype = vid.get("type", "output")
        t0 = time.time()
        params = f"filename={fname}&subfolder={subfolder}&type={ftype}"
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{COMFYUI_URL}/view?{params}")
                size_mb = len(r.content) / (1024 * 1024)
                content_type = r.headers.get("content-type", "unknown")
                is_video = "video" in content_type or fname.endswith((".mp4", ".webm", ".gif"))
                record(
                    sec,
                    "C10-03",
                    "Latest video accessible and valid",
                    "PASS" if r.status_code == 200 and size_mb > 0.05 and is_video else "WARN",
                    f"{fname}: {size_mb:.2f}MB, {content_type}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, "C10-03", "Latest video accessible and valid", "WARN", str(e)[:120], t0=t0)
    else:
        record(
            sec,
            "C10-03",
            "Latest video accessible and valid",
            "INFO",
            "no videos in recent history",
            t0=None,
        )

