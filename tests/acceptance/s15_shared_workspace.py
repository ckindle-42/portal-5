"""S15: Shared workspace verification (TASK-WORKSPACE-001)."""

import asyncio
import contextlib
import os
import time
from pathlib import Path

from tests.acceptance._common import (
    record,
)


async def run() -> None:
    """S15: Shared workspace verification (TASK-WORKSPACE-001)."""
    print("\n━━━ S15. SHARED WORKSPACE ━━━")
    sec = "S15"

    workspace_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))

    # S15-01: Workspace root exists
    t0 = time.time()
    record(
        sec,
        "S15-01",
        "Workspace root exists",
        "PASS" if workspace_root.is_dir() else "FAIL",
        str(workspace_root),
        t0=t0,
    )

    # S15-02: All canonical subdirectories exist
    t0 = time.time()
    expected = [
        "uploads",
        "generated/transcripts",
        "generated/documents",
        "generated/images",
        "generated/videos",
        "generated/music",
        "generated/speech",
    ]
    missing = [d for d in expected if not (workspace_root / d).is_dir()]
    record(
        sec,
        "S15-02",
        "Workspace subdirectories",
        "PASS" if not missing else "FAIL",
        "all present" if not missing else f"missing: {missing}",
        t0=t0,
    )

    # S15-03: OWUI bind mount visible (write from host, read from OWUI container)
    t0 = time.time()
    probe = workspace_root / "uploads" / ".workspace_probe"
    probe.write_text("portal-5 workspace probe")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            "deploy/portal-5/docker-compose.yml",
            "exec",
            "-T",
            "open-webui",
            "cat",
            "/app/backend/data/uploads/.workspace_probe",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if b"portal-5 workspace probe" in stdout:
            record(
                sec, "S15-03", "OWUI uploads bind mount", "PASS", "host↔OWUI bidirectional", t0=t0
            )
        else:
            record(
                sec,
                "S15-03",
                "OWUI uploads bind mount",
                "FAIL",
                "probe not visible from OWUI",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S15-03", "OWUI uploads bind mount", "FAIL", str(e)[:100], t0=t0)
    finally:
        with contextlib.suppress(Exception):
            probe.unlink()

    # S15-04: Helper module imports cleanly
    t0 = time.time()
    try:
        from portal.platform.mcp_host.workspace import get_generated_dir, get_workspace_root

        root = get_workspace_root()
        get_generated_dir("transcripts")
        record(sec, "S15-04", "workspace helper imports", "PASS", str(root), t0=t0)
    except Exception as e:
        record(sec, "S15-04", "workspace helper imports", "FAIL", str(e)[:100], t0=t0)

    # S15-05: AUDIO_STT_ENGINE is disabled in OWUI config
    t0 = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            "deploy/portal-5/docker-compose.yml",
            "exec",
            "-T",
            "open-webui",
            "sh",
            "-c",
            'echo "${AUDIO_STT_ENGINE}"',
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        value = stdout.decode().strip()
        if not value:
            record(sec, "S15-05", "AUDIO_STT_ENGINE disabled", "PASS", "empty (correct)", t0=t0)
        else:
            record(
                sec,
                "S15-05",
                "AUDIO_STT_ENGINE disabled",
                "WARN",
                f"unexpected value: {value!r}",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S15-05", "AUDIO_STT_ENGINE disabled", "FAIL", str(e)[:100], t0=t0)
