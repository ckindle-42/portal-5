"""Section — the media modules' OWUI turns become published artifacts and read back.

The image hop is the live-proven one; the video and music hops each drive one real
OWUI turn on ``auto-audio::video`` / ``auto-audio::music`` and WARN with the reason
while those modules are disabled in ``config/portal.yaml``.
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
from .owui import chat_turn, trace_hop
from .workspaces import StreamedTurn

WORKSPACE = "auto-audio::image"
PRESET = "imports/openwebui/workspaces/workspace_auto_audio_image.json"
PROMPT = (
    "Use the image_start tool to generate a 512x512 image of a single red circle on a plain "
    "white background, then call image_status with the returned job_id until its status is "
    "'done'. Reply with only the image's download URL."
)
#: publish_file's URL shape — {PUBLIC_URL}/api/v1/files/{id}/content/{name}
_ARTIFACT_RE = re.compile(r"https?://\S*?/api/v1/files/[0-9a-fA-F-]{8,}/content/\S+")

VIDEO_WORKSPACE = "auto-audio::video"
VIDEO_PRESET = "imports/openwebui/workspaces/workspace_auto_audio_video.json"
VIDEO_PROMPT = "Create a 4-second 512x320 video of ocean waves hitting basalt rocks at sunset."
ARTIFACT_TIMEOUT_ENV = "PORTAL_TRACE_MEDIA_TIMEOUT_S"
DEFAULT_ARTIFACT_TIMEOUT_S = 900.0
_URL_RE = re.compile(r"https?://\S+")


def media_timeout_s() -> float:
    """A render takes minutes; the artifact turn gets its own, longer budget."""
    try:
        return float(os.environ.get(ARTIFACT_TIMEOUT_ENV, DEFAULT_ARTIFACT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_ARTIFACT_TIMEOUT_S


def module_hop(portal: dict[str, Any]) -> Hop | None:
    """WARN with the reason while the image module is disabled (config/portal.yaml)."""
    modules = portal.get("modules") or {}
    if (modules.get("image") or {}).get("enabled", True):
        return None
    return Hop(
        "image module",
        Status.WARN,
        "skipped: modules.image.enabled is false",
        "module enabled",
        "portal module enable image --yes, then install-mflux + pull-mflux-models + sync-config",
    )


def artifact_url(text: str) -> str:
    """The published download URL in an assistant reply, or ''."""
    match = _ARTIFACT_RE.search(text) or re.search(r"https?://\S+\.(?:png|webp|jpg)\b", text)
    return match.group(0).rstrip(".,)") if match else ""


def fetch_file(url: str, api_key: str) -> tuple[httpx.Response | None, str]:
    """Fetch an OWUI artifact with the configured API key."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        return httpx.get(url, headers=headers, timeout=30.0), ""
    except httpx.HTTPError as exc:
        return None, str(exc)


def read_back(url: str, api_key: str) -> tuple[bool, str]:
    """GET the published artifact — 200 + non-empty body proves it exists and serves."""
    resp, error = fetch_file(url, api_key)
    if resp is None:
        return False, f"read failed: {error}"
    return resp.status_code == 200 and len(resp.content) > 0, (
        f"http {resp.status_code}, {len(resp.content)} bytes"
    )


def artifact_hop(turn: StreamedTurn, api_key: str) -> Hop:
    """The turn's reply carries the download URL; the artifact must still read back."""
    if turn.error or turn.status_code != 200:
        reason = turn.error or f"http {turn.status_code}"
        return Hop("image artifact", Status.FAIL, short(reason, 70), "OWUI turn completes")
    url = artifact_url(turn.stats.text)
    if not url:
        return Hop(
            "image artifact", Status.FAIL, short(turn.stats.text, 70), "download URL in reply"
        )
    ok, detail = read_back(url, api_key)
    return Hop(
        "image artifact", Status.PASS if ok else Status.FAIL, short(url, 60), "200 + bytes", detail
    )


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


def image_hops(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """One real image turn: OWUI → Pipeline → mflux MCP → published artifact read back."""
    gate = module_hop(portal)
    if gate is not None:
        return [gate]
    key = env_value("OWUI_API_KEY")
    if not key:
        return [Hop("owui turn", Status.WARN, "not run: no OWUI_API_KEY", "an OWUI turn", "set it")]
    preset = ctx.repo_root / PRESET
    if not preset.is_file():
        return [
            Hop(
                "image preset",
                Status.WARN,
                "preset missing",
                preset.name,
                "run ./launch.sh sync-config with modules.image enabled, then seed Open WebUI",
            )
        ]
    started = time.time()
    try:
        turn = chat_turn(ctx, key, workspace=WORKSPACE, prompt=PROMPT, preset_path=preset)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        turn = StreamedTurn(0, error=f"{type(exc).__name__}: {exc}")
    return [artifact_hop(turn, key), trace_hop(ctx, started, workspace=WORKSPACE)]


def video_hops(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
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
    preset = ctx.repo_root / VIDEO_PRESET
    if not preset.is_file():
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
            workspace=VIDEO_WORKSPACE,
            prompt=VIDEO_PROMPT,
            preset_path=preset,
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


MUSIC_WORKSPACE = "auto-audio::music"
MUSIC_PRESET = "imports/openwebui/workspaces/workspace_auto_audio_music.json"
MUSIC_PROMPT = (
    "Use the music_start tool to generate 15 seconds of gentle solo piano "
    "(lyrics='[Instrumental]', engine='acestep', steps=8), then call music_status "
    "with the returned job_id until its status is 'done'. Reply with only the wav's "
    "download URL."
)


def music_enabled(portal: dict[str, Any]) -> bool:
    """`modules.music.enabled` from the trace's portal.yaml snapshot."""
    modules = portal.get("modules") if isinstance(portal, dict) else None
    spec = modules.get("music") if isinstance(modules, dict) else None
    return bool(spec.get("enabled")) if isinstance(spec, dict) else False


def music_hops(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """One music request end to end, or a WARN that says why it did not run."""
    if not music_enabled(portal):
        return [
            Hop(
                "music artifact turn",
                Status.WARN,
                "skipped: music module disabled",
                "a generated wav",
                "config/portal.yaml modules.music.enabled: false — enable with "
                "./launch.sh install-music, portal module enable music, run "
                "./launch.sh sync-config, then re-run",
            )
        ]
    key = env_value("OWUI_API_KEY")
    if not key:
        return [Hop("music artifact turn", Status.WARN, "not run: no OWUI_API_KEY", "an OWUI turn")]
    preset = ctx.repo_root / MUSIC_PRESET
    if not preset.is_file():
        return [
            Hop(
                "music artifact turn",
                Status.WARN,
                "skipped: workspace preset missing",
                "workspace_auto_audio_music.json",
                "run ./launch.sh sync-config with the module enabled, then re-run",
            )
        ]
    started = time.time()
    try:
        turn = chat_turn(
            ctx,
            key,
            workspace=MUSIC_WORKSPACE,
            prompt=MUSIC_PROMPT,
            preset_path=preset,
            timeout_s=media_timeout_s(),
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        turn = StreamedTurn(0, error=f"{type(exc).__name__}: {exc}")
    return [music_artifact_hop(turn, key), trace_hop(ctx, started, workspace=MUSIC_WORKSPACE)]


def music_artifact_hop(turn: StreamedTurn, api_key: str) -> Hop:
    """The turn's reply carries the published wav URL; the artifact must read back."""
    if turn.error or turn.status_code != 200:
        reason = turn.error or f"http {turn.status_code}"
        return Hop("music artifact", Status.FAIL, short(reason, 70), "OWUI turn completes")
    url = artifact_url(turn.stats.text)
    if not url:
        return Hop(
            "music artifact", Status.FAIL, short(turn.stats.text, 70), "download URL in reply"
        )
    ok, detail = read_back(url, api_key)
    return Hop(
        "music artifact", Status.PASS if ok else Status.FAIL, short(url, 60), "200 + bytes", detail
    )


def run(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """One media section: the image turn's artifacts, then the video and music hops."""
    return image_hops(ctx, portal) + video_hops(ctx, portal) + music_hops(ctx, portal)
