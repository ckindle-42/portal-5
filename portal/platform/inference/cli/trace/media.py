"""Section — one real video request becomes an artifact and reads back.

WARN with the reason while the video module is disabled; when it is enabled,
drive one real OWUI turn on ``auto-audio::video``, then read the produced
artifact back over HTTP and from ``${AI_OUTPUT_DIR}/generated/videos/``.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from .context import TraceContext, env_value
from .model import Hop, Status, short
from .owui import chat_turn

WORKSPACE = "auto-audio::video"
PRESET_PATH = "imports/openwebui/workspaces/workspace_auto_audio_video.json"
PROMPT = "Create a 4-second 512x320 video of ocean waves hitting basalt rocks at sunset."
ARTIFACT_TIMEOUT_ENV = "PORTAL_TRACE_MEDIA_TIMEOUT_S"
DEFAULT_ARTIFACT_TIMEOUT_S = 900.0
_URL_RE = re.compile(r"https?://\S+")


def media_timeout_s() -> float:
    """A render takes minutes; the artifact turn gets its own, longer budget."""
    try:
        return float(os.environ.get(ARTIFACT_TIMEOUT_ENV, DEFAULT_ARTIFACT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_ARTIFACT_TIMEOUT_S


def video_enabled(portal: dict[str, Any]) -> bool:
    """`modules.video.enabled` from the trace's portal.yaml snapshot."""
    modules = portal.get("modules") if isinstance(portal, dict) else None
    spec = modules.get("video") if isinstance(modules, dict) else None
    return bool(spec.get("enabled")) if isinstance(spec, dict) else False


def turn_hop(text: str, error: str) -> Hop:
    """The turn's verdict: the reply must carry a downloadable artifact URL."""
    if error:
        return Hop("video artifact turn", Status.FAIL, short(error, 70), "a done job")
    url = _URL_RE.search(text)
    if url is None:
        return Hop(
            "video artifact turn",
            Status.FAIL,
            f"no url in reply ({short(text or '(empty)', 50)})",
            "a download link",
        )
    observed = f"url={short(url.group(0), 50)}"
    done = "job" in text.lower() or "video" in text.lower()
    return Hop("video artifact turn", Status.PASS if done else Status.WARN, observed, "a done job")


def readback_hop(url: str, api_key: str) -> Hop:
    """GET the produced artifact: HTTP 200 and real MP4 bytes."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(url, headers=headers, timeout=60.0, follow_redirects=True)
        body = response.content
    except httpx.HTTPError as exc:
        return Hop("video artifact readback", Status.FAIL, "unread", "HTTP 200", str(exc)[:70])
    magic = body[4:8] == b"ftyp" if len(body) >= 12 else False
    observed = f"http={response.status_code} bytes={len(body)} mp4={magic}"
    ok = response.status_code == 200 and len(body) > 0
    return Hop(
        "video artifact readback",
        Status.PASS if ok else Status.FAIL,
        observed,
        "HTTP 200, non-empty MP4",
        "" if ok else body[:16].hex(),
    )


def clip_hop(clip: Path | None, since: float) -> Hop:
    """The renderer wrote under ${AI_OUTPUT_DIR}/generated/videos/ (Rule 11)."""
    if clip is None:
        return Hop(
            "video artifact file",
            Status.FAIL,
            "no new ltx_*/wan_* mp4",
            "a clip newer than the turn",
            "checked ${AI_OUTPUT_DIR}/generated/videos/",
        )
    size_mb = clip.stat().st_size / 1e6
    fresh = clip.stat().st_mtime >= since
    return Hop(
        "video artifact file",
        Status.PASS if fresh and size_mb > 0 else Status.WARN,
        f"{clip.name} {size_mb:.1f}MB",
        "written during the turn",
    )


def newest_clip(since: float) -> Path | None:
    from portal.platform.mcp_host.workspace import get_generated_dir

    try:
        out_dir = get_generated_dir("videos")
    except OSError:
        return None
    clips = [
        p
        for p in out_dir.glob("*.mp4")
        if p.name.startswith(("ltx_", "wan_")) and p.stat().st_mtime >= since
    ]
    return max(clips, key=lambda p: p.stat().st_mtime) if clips else None


def run(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """One video request end to end, or a WARN that says why it did not run."""
    if not video_enabled(portal):
        return [
            Hop(
                "video artifact turn",
                Status.WARN,
                "skipped: video module disabled",
                "a generated mp4",
                "config/portal.yaml modules.video.enabled: false — enable with "
                "./launch.sh install-video-mlx + portal module enable video, run "
                "./launch.sh sync-config, then re-run",
            )
        ]
    key = env_value("OWUI_API_KEY")
    if not key:
        return [Hop("video artifact turn", Status.WARN, "not run: no OWUI_API_KEY", "an OWUI turn")]
    if not (ctx.repo_root / PRESET_PATH).exists():
        return [
            Hop(
                "video artifact turn",
                Status.WARN,
                "skipped: workspace preset missing",
                "workspace_auto_audio_video.json",
                "run ./launch.sh sync-config with the module enabled, then re-run",
            )
        ]
    started = time.time()
    try:
        turn = chat_turn(
            ctx,
            key,
            workspace=WORKSPACE,
            prompt=PROMPT,
            preset_path=PRESET_PATH,
            timeout_s=media_timeout_s(),
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        turn_hop_err = f"{type(exc).__name__}: {exc}"
        return [turn_hop("", turn_hop_err), clip_hop(None, started)]
    hop = turn_hop(turn.stats.text, turn.error)
    hops = [hop]
    if hop.status is Status.FAIL:
        return [*hops, clip_hop(None, started)]
    url_match = _URL_RE.search(turn.stats.text)
    hops.append(readback_hop(url_match.group(0), key) if url_match else readback_hop("", key))
    hops.append(clip_hop(newest_clip(started), started))
    return hops
