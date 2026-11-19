"""Section — the image module's OWUI turn produces, publishes and reads back one artifact."""

from __future__ import annotations

import re
import time
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


def read_back(url: str, api_key: str) -> tuple[bool, str]:
    """GET the published artifact — 200 + non-empty body proves it exists and serves."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = httpx.get(url, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        return False, f"read failed: {exc}"
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


def run(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
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
