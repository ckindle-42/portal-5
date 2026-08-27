"""S7: Music generation tests — both engines (MiniMax + ACE-Step)."""

import asyncio
import json
import time

from tests.acceptance._common import MCP, _chat, _get, _mcp_raw, record


async def _poll_until_done(
    port: int, status_tool: str, job_id: str, section: str, tid: str, poll_timeout_s: int = 1200
) -> dict | None:
    elapsed = 0
    while elapsed < poll_timeout_s:
        await asyncio.sleep(15)
        elapsed += 15
        status_text = await _mcp_raw(
            port,
            status_tool,
            {"job_id": job_id},
            section=section,
            tid=f"{tid}-poll",
            name=f"Poll {status_tool} (t+{elapsed}s)",
            ok_fn=lambda text: "status" in text.lower(),
            timeout=20,
        )
        try:
            parsed = json.loads(status_text)
        except (json.JSONDecodeError, TypeError):
            continue
        if parsed.get("status") in ("done", "error"):
            return parsed
    return None


async def _run_engine(
    section: str, port: int, gen_tool: str, status_tool: str, tid: str, gen_args: dict
) -> str | None:
    start_text = await _mcp_raw(
        port,
        gen_tool,
        gen_args,
        section=section,
        tid=tid,
        name=f"Start {gen_tool} (60s/30-step)",
        ok_fn=lambda text: "job_id" in text.lower() or "success" in text.lower(),
        warn_if=["not available", "error", "refused"],
        timeout=30,
    )
    try:
        job_id = json.loads(start_text).get("job_id")
    except (json.JSONDecodeError, AttributeError):
        job_id = None
    if not job_id:
        record(
            section, f"{tid}-result", f"{gen_tool} completed", "WARN", "no job_id", t0=time.time()
        )
        return None
    final = await _poll_until_done(port, status_tool, job_id, section, tid)
    if final and final.get("status") == "done":
        record(
            section,
            f"{tid}-result",
            f"{gen_tool} completed",
            "PASS",
            f"✓ {final.get('download_url', '')[:80]}",
            t0=time.time(),
        )
        return final.get("filename")
    record(
        section,
        f"{tid}-result",
        f"{gen_tool} completed",
        "WARN",
        f"did not complete: {str(final)[:120] if final else 'timeout'}",
        t0=time.time(),
    )
    return None


async def run() -> None:
    print("\n━━━ S7. MUSIC GENERATION (dual engine) ━━━")
    section = "S7"
    for tid, key, label in (
        ("S7-01", "music_minimax", "MiniMax MCP"),
        ("S7-02", "music_ace", "ACE MCP"),
    ):
        t0 = time.time()
        code, data = await _get(f"http://localhost:{MCP[key]}/health")
        record(
            section,
            tid,
            f"{label} health",
            "PASS" if code == 200 else "WARN",
            data.get("service", "?") if isinstance(data, dict) else f"HTTP {code}",
            t0=t0,
        )
    await _run_engine(
        section,
        MCP["music_minimax"],
        "minimax_generate",
        "minimax_status",
        "S7-03",
        {
            "prompt": "upbeat jazz piano solo",
            "lyrics": "[Instrumental]",
            "seconds": 60,
            "steps": 30,
        },
    )
    ace_file = await _run_engine(
        section,
        MCP["music_ace"],
        "ace_generate",
        "ace_status",
        "S7-04",
        {
            "prompt": "upbeat jazz piano solo",
            "lyrics": "[Instrumental]",
            "seconds": 60,
            "steps": 30,
            "model": "acestep-v15-sft",
        },
    )
    if ace_file:
        await _run_engine(
            section,
            MCP["music_ace"],
            "ace_generate",
            "ace_status",
            "S7-05",
            {
                "prompt": "add a brighter horn section here",
                "task_type": "repaint",
                "src_audio_path": ace_file,
                "repainting_start": 5,
                "repainting_end": 10,
                "steps": 30,
            },
        )
    else:
        record(
            section, "S7-05", "ACE repaint", "WARN", "no S7-04 output to repaint", t0=time.time()
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
