"""S7: Music generation — one MCP, ACE-Step primary, MiniMax fallback. Module ships disabled."""

import asyncio
import json
import time

from tests.acceptance._common import MCP, _chat, _get, _mcp_raw, record


async def _poll_until_done(
    port: int, job_id: str, section: str, tid: str, poll_timeout_s: int = 1200
) -> dict | None:
    elapsed = 0
    while elapsed < poll_timeout_s:
        await asyncio.sleep(15)
        elapsed += 15
        status_text = await _mcp_raw(
            port,
            "music_status",
            {"job_id": job_id, "wait_s": 15},
            section=section,
            tid=f"{tid}-poll",
            name=f"Poll music_status (t+{elapsed}s)",
            ok_fn=lambda text: "status" in text.lower(),
            timeout=30,
        )
        try:
            parsed = json.loads(status_text)
        except (json.JSONDecodeError, TypeError):
            continue
        if parsed.get("status") in ("done", "error"):
            return parsed
    return None


async def run() -> None:
    print("\n━━━ S7. MUSIC GENERATION (ACE-Step XL-Turbo, MiniMax fallback) ━━━")
    section = "S7"
    t0 = time.time()
    code, data = await _get(f"http://localhost:{MCP['music']}/health")
    record(
        section,
        "S7-01",
        "Music MCP health",
        "PASS"
        if code == 200 and isinstance(data, dict) and data.get("service") == "music-mcp"
        else "WARN",
        data.get("service", "?") if isinstance(data, dict) else f"HTTP {code}",
        t0=t0,
    )
    start_text = await _mcp_raw(
        MCP["music"],
        "music_start",
        {
            "prompt": "upbeat jazz piano solo",
            "lyrics": "[Instrumental]",
            "seconds": 15,
            "steps": 8,
            "engine": "acestep",
            "seed": 42,
        },
        section=section,
        tid="S7-03",
        name="Start music_start (15s/8-step acestep)",
        ok_fn=lambda text: "job_id" in text.lower(),
        warn_if=["not available", "error", "refused"],
        timeout=60,
    )
    try:
        job_id = json.loads(start_text).get("job_id")
    except (json.JSONDecodeError, AttributeError):
        job_id = None
    final = await _poll_until_done(MCP["music"], job_id, section, "S7-03") if job_id else None
    if final and final.get("status") == "done":
        record(
            section,
            "S7-03-result",
            "music_start completed",
            "PASS",
            f"✓ {final.get('download_url', '')[:80]}",
            t0=time.time(),
        )
    else:
        record(
            section,
            "S7-03-result",
            "music_start completed",
            "WARN",
            "no job_id" if not job_id else f"did not complete: {str(final)[:120]}",
            t0=time.time(),
        )
    t0 = time.time()
    code, text = await _chat(
        "auto-music",
        "Describe what a 15-second jazz piano trio piece with upright bass would sound like. Include tempo, key, and primary motifs.",
        max_tokens=150,
        timeout=120,
    )
    if code == 200 and text.strip():
        record(
            section,
            "S7-06",
            "auto-music workspace round-trip",
            "PASS",
            f"'{text[:80].strip()}'",
            t0=t0,
        )
    else:
        record(
            section,
            "S7-06",
            "auto-music workspace round-trip",
            "WARN",
            "503 — backend not available" if code == 503 else f"HTTP {code}",
            t0=t0,
        )
