"""Generate the media set the media_alignment / unified_recall probes score.

Sequential, one request in flight (the platform's memory admission may refuse; a refusal is
recorded, never retried in a loop). Artifacts land in /Volumes/data01/portal5_scratch_eg2/media with
a manifest.json mapping each file to its prompt.

    uv run python -m tests.benchmarks.embedding_consumers.gen_media [--only images|videos|music|edits]
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import httpx

from .probes._common import DATA

SCRATCH = Path("/Volumes/data01/portal5_scratch_eg2/media")
OUT = Path.home() / "AI_Output"
SERVICES = {
    "images": "http://localhost:8933",
    "videos": "http://localhost:8935",
    "music": "http://localhost:8912",
}


def _newest(dirpath: Path, before: set[str], suffixes: tuple[str, ...]) -> Path | None:
    new = [p for p in dirpath.iterdir() if p.name not in before and p.suffix.lower() in suffixes]
    return max(new, key=lambda p: p.stat().st_mtime) if new else None


def _call(c: httpx.Client, base: str, tool: str, args: dict) -> dict:
    r = c.post(f"{base}/tools/{tool}", json={"arguments": args}, timeout=3600)
    r.raise_for_status()
    return r.json()


def run(only: str | None) -> None:  # noqa: C901, PLR0912, PLR0915
    media = json.loads((DATA / "media_prompts.json").read_text())["media"]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    mf = SCRATCH / "manifest.json"
    man = (
        json.loads(mf.read_text())
        if mf.is_file()
        else {"images": [], "videos": [], "music": [], "edits": []}
    )
    with httpx.Client() as c:
        if only in (None, "images"):
            d = OUT / "images"
            for i, row in enumerate(
                media["images"][len(man["images"]) :], start=len(man["images"])
            ):
                before = {p.name for p in d.iterdir()}
                t = time.time()
                res = _call(
                    c,
                    SERVICES["images"],
                    "generate_image",
                    {
                        "prompt": row["prompt"],
                        "model": "schnell",
                        "width": 768,
                        "height": 768,
                        "seed": 100 + i,
                    },
                )
                f = _newest(d, before, (".png",))
                man["images"].append(
                    {
                        "prompt": row["prompt"],
                        "file": str(shutil.copy(f, SCRATCH / f"img_{i:02d}.png")) if f else None,
                        "ok": bool(res.get("success")),
                        "error": res.get("error"),
                        "seconds": round(time.time() - t, 1),
                    }
                )
                mf.write_text(json.dumps(man, indent=1))
        if only in (None, "videos"):
            d = OUT / "videos"
            d.mkdir(exist_ok=True)
            for i, row in enumerate(
                media["videos"][len(man["videos"]) :], start=len(man["videos"])
            ):
                before = {p.name for p in d.iterdir()}
                t = time.time()
                res = _call(
                    c,
                    SERVICES["videos"],
                    "generate_video",
                    {
                        "prompt": row["prompt"],
                        "frames": 49,
                        "width": 512,
                        "height": 320,
                        "seed": 200 + i,
                    },
                )
                f = _newest(d, before, (".mp4",))
                man["videos"].append(
                    {
                        "prompt": row["prompt"],
                        "file": str(shutil.copy(f, SCRATCH / f"vid_{i:02d}.mp4")) if f else None,
                        "ok": bool(res.get("success")),
                        "error": res.get("error"),
                        "seconds": round(time.time() - t, 1),
                    }
                )
                mf.write_text(json.dumps(man, indent=1))
        if only in (None, "music"):
            d = OUT / "music"
            d.mkdir(exist_ok=True)
            for i, row in enumerate(media["music"][len(man["music"]) :], start=len(man["music"])):
                before = {p.name for p in d.iterdir()}
                t = time.time()
                res = _call(
                    c,
                    SERVICES["music"],
                    "minimax_generate",
                    {"prompt": row["prompt"], "seconds": 20, "steps": 12, "seed": 300 + i},
                )
                job = res.get("job_id")
                status: dict = res
                while job and status.get("status") not in ("done", "error"):
                    time.sleep(15)
                    status = _call(c, SERVICES["music"], "minimax_status", {"job_id": job})
                f = _newest(d, before, (".wav", ".mp3", ".flac", ".m4a"))
                man["music"].append(
                    {
                        "prompt": row["prompt"],
                        "file": str(shutil.copy(f, SCRATCH / f"mus_{i:02d}{f.suffix}"))
                        if f
                        else None,
                        "ok": bool(f),
                        "error": status.get("error") or res.get("error"),
                        "seconds": round(time.time() - t, 1),
                    }
                )
                mf.write_text(json.dumps(man, indent=1))
        if only in (None, "edits"):
            up = OUT / "uploads"
            up.mkdir(exist_ok=True)
            d = OUT / "images"
            for i, row in enumerate(media["edits"][len(man["edits"]) :], start=len(man["edits"])):
                src = man["images"][row["source_image_index"]].get("file")
                if not src:
                    man["edits"].append({"ok": False, "error": "source image missing"})
                    continue
                name = f"eg2_edit_src_{i}.png"
                shutil.copy(src, up / name)
                before = {p.name for p in d.iterdir()}
                t = time.time()
                res = _call(
                    c,
                    SERVICES["images"],
                    "edit_image",
                    {
                        "image_url": name,
                        "prompt": row["instruction"],
                        "model": "qwen-image-edit",
                        "seed": 400 + i,
                        "width": 768,
                        "height": 768,
                    },
                )
                f = _newest(d, before, (".png",))
                man["edits"].append(
                    {
                        "source": src,
                        "instruction": row["instruction"],
                        "opposite": row["opposite"],
                        "file": str(shutil.copy(f, SCRATCH / f"edit_{i:02d}.png")) if f else None,
                        "ok": bool(res.get("success")),
                        "error": res.get("error"),
                        "seconds": round(time.time() - t, 1),
                    }
                )
                mf.write_text(json.dumps(man, indent=1))
    print(json.dumps({k: sum(1 for x in v if x.get("ok")) for k, v in man.items()}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["images", "videos", "music", "edits"])
    run(ap.parse_args().only)
