"""Section — one Open WebUI music turn writes a wav and the hop reads it back.

WARN while ``modules.music.enabled`` is false. The module ships disabled.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from portal.platform.mcp_host.workspace import get_generated_dir

from .context import TraceContext, env_value
from .model import Hop, Status, short
from .owui import _new_chat, completion_body

WORKSPACE = "auto-audio::music"
PROMPT = (
    "Call music_start exactly once with prompt='short soft piano', "
    "lyrics='[Instrumental]', seconds=15, steps=8, engine='acestep', seed=42. "
    "Then call music_status with that job_id until status is done or error. "
    "Reply with the artifact_path and nothing else."
)
_PRESET = "imports/openwebui/workspaces/workspace_auto_audio_music.json"


def music_enabled(portal: dict[str, Any]) -> bool:
    """True only when config explicitly enables the music module."""
    modules = portal.get("modules")
    if not isinstance(modules, dict):
        return False
    music = modules.get("music")
    return isinstance(music, dict) and music.get("enabled") is True


def _disabled_hop() -> Hop:
    return Hop(
        "music artifact",
        Status.WARN,
        "module disabled",
        "a RIFF wav under ${AI_OUTPUT_DIR}/generated/music",
        "modules.music.enabled is false",
    )


def _newest_wav(since: float) -> Path | None:
    found: list[Path] = []
    for path in get_generated_dir("music").glob("*.wav"):
        try:
            if path.stat().st_mtime >= since - 1:
                found.append(path)
        except OSError:
            continue
    return max(found, key=lambda item: item.stat().st_mtime) if found else None


def _chat(ctx: TraceContext, key: str, preset: dict[str, Any]) -> str:
    user_id, message_id = str(uuid.uuid4()), str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=ctx.timeout_s) as client:
        created = client.post(
            f"{ctx.owui_url}/api/v1/chats/new",
            headers=headers,
            json=_new_chat(WORKSPACE, PROMPT, user_id, message_id),
        )
        created.raise_for_status()
        chat_id = str(created.json()["id"])
        try:
            response = client.post(
                f"{ctx.owui_url}/api/chat/completions",
                headers=headers,
                json=completion_body(
                    preset, PROMPT, chat_id, message_id, f"portal-trace-music-{uuid.uuid4()}"
                ),
            )
            response.raise_for_status()
            deadline = time.monotonic() + ctx.timeout_s
            while (
                client.get(f"{ctx.owui_url}/api/tasks/chat/{chat_id}", headers=headers)
                .json()
                .get("task_ids")
            ):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"Open WebUI chat {chat_id} timed out")
                time.sleep(min(1.0, left))
            final = client.get(f"{ctx.owui_url}/api/v1/chats/{chat_id}", headers=headers)
            final.raise_for_status()
            message = final.json()["chat"]["history"]["messages"][message_id]
            return str(message.get("content") or "")
        finally:
            client.delete(f"{ctx.owui_url}/api/v1/chats/{chat_id}", headers=headers)


def _live(ctx: TraceContext) -> list[Hop]:
    key = env_value("OWUI_API_KEY")
    if not key:
        return [Hop("music artifact", Status.WARN, "not run: no OWUI_API_KEY", "a RIFF wav")]
    preset_path = ctx.repo_root / _PRESET
    if not preset_path.is_file():
        return [
            Hop(
                "music artifact",
                Status.WARN,
                "preset missing",
                _PRESET,
                "sync-config after enabling music",
            )
        ]
    started = time.time()
    try:
        body = _chat(ctx, key, json.loads(preset_path.read_text(encoding="utf-8")))
    except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError, OSError) as exc:
        return [
            Hop(
                "music artifact",
                Status.FAIL,
                f"{type(exc).__name__}: {exc}"[:120],
                "a completed OWUI music turn",
            )
        ]
    wav = _newest_wav(started)
    if wav is None:
        return [
            Hop("music artifact", Status.FAIL, "no new wav", "generated/music/*.wav", short(body))
        ]
    header = wav.read_bytes()[:12]
    ok = wav.stat().st_size > 44 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    return [
        Hop(
            "music artifact",
            Status.PASS if ok else Status.FAIL,
            f"{wav} {wav.stat().st_size}B",
            "RIFF/WAVE",
            "" if ok else short(body),
        )
    ]


def run(ctx: TraceContext, portal: dict[str, Any]) -> list[Hop]:
    """One music artifact hop, or a WARN while the module is disabled."""
    if not music_enabled(portal):
        return [_disabled_hop()]
    return _live(ctx)
