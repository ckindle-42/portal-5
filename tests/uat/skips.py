"""Portal 5 UAT — skip-condition detection, bot dispatcher path.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase C).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

# Skip condition detection
# ---------------------------------------------------------------------------


def evaluate_skip_conditions() -> dict:
    conditions: dict[str, bool] = {}
    try:
        r = httpx.get("http://localhost:8188/system_stats", timeout=3)
        conditions["no_comfyui"] = r.status_code != 200
    except Exception:
        conditions["no_comfyui"] = True

    env_content = Path(".env").read_text() if Path(".env").exists() else ""
    # Per-key check: KEY=value on its own line, value non-empty, value != "CHANGEME".
    # The previous `"CHANGEME" in env_content` substring check fired on any other
    # placeholder elsewhere in the file (PIPELINE_API_KEY, GRAFANA_PASSWORD, the
    # comment on line 3 of .env.example, etc.), falsely flagging both bot
    # predicates as "not configured" even with valid tokens set.
    conditions["no_bot_telegram"] = not _env_var_set(env_content, "TELEGRAM_BOT_TOKEN")
    conditions["no_bot_slack"] = not _env_var_set(env_content, "SLACK_BOT_TOKEN")
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    conditions["no_image_upload"] = not (fixtures / "sample.png").exists()
    conditions["no_audio_fixture"] = not (fixtures / "sample.wav").exists()
    conditions["no_two_speaker_audio_fixture"] = not (fixtures / "sample_two_speakers.wav").exists()
    try:
        r = httpx.get("http://localhost:8924/health", timeout=3)
        conditions["no_transcribe_server"] = r.status_code != 200
    except Exception:
        conditions["no_transcribe_server"] = True
    conditions["no_docx_fixture"] = not (fixtures / "sample.docx").exists()
    conditions["no_knowledge_base"] = not (fixtures / "knowledge_base").is_dir()
    return conditions


def _env_var_set(env_content: str, key: str) -> bool:
    """True iff ``key`` is set in env content with a non-empty value that isn't ``CHANGEME``.

    Reads ``KEY=value`` on its own line; tolerates leading whitespace, inline
    comments, and surrounding quotes on the value. Comments and unrelated
    placeholders elsewhere in the file do not affect the result.
    """
    import re

    pat = rf"^[ \t]*{re.escape(key)}=([^\r\n]*)$"
    m = re.search(pat, env_content, re.MULTILINE)
    if not m:
        return False
    raw = m.group(1)
    # Strip inline comment ("# ..." not inside quotes — simple heuristic that
    # matches typical .env practice; values containing literal '#' should be
    # quoted, which is the convention .env.example follows).
    if "#" in raw and not (raw.lstrip().startswith(('"', "'"))):
        raw = raw.split("#", 1)[0]
    val = raw.strip().strip('"').strip("'")
    return bool(val) and val != "CHANGEME"


def _bot_container_running(container_name: str) -> tuple[bool, str]:
    """True if the named docker container is in 'running' state.

    Used by via_dispatcher tests to surface a clear failure when the bot
    container itself is down — distinct from the dispatcher path failing.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return False, f"container not found: {container_name}"
        status = r.stdout.strip()
        return status == "running", f"status={status}"
    except FileNotFoundError:
        return False, "docker CLI not available"
    except Exception as exc:
        return False, f"inspect error: {exc}"


async def _run_via_dispatcher(workspace: str, prompt: str, timeout: int) -> str:
    """Drive a chat completion through the Pipeline as a Telegram/Slack bot would.

    Bypasses Open WebUI to exercise the exact code path
    ``portal_channels.dispatcher.call_pipeline_async`` uses on every inbound
    message: a single POST to ``:9099/v1/chat/completions`` with
    ``Authorization: Bearer ${PIPELINE_API_KEY}``. Returns the assistant content
    string. Raises on transport error or non-2xx response — caller handles.
    """
    api_key = os.environ.get("PIPELINE_API_KEY", "portal-pipeline")
    pipeline_url = os.environ.get("PIPELINE_URL", "http://localhost:9099")
    payload = {
        "model": workspace,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{pipeline_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])
