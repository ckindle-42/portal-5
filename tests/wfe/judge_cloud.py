#!/usr/bin/env python3
"""Cloud judge backend — OpenAI-compatible /v1/chat/completions.

Reads its config from tests/wfe/judge.yaml under ``profiles.cloud``; env vars
override the file (``WFE_JUDGE_CLOUD_MODEL`` / ``WFE_JUDGE_CLOUD_URL``).  The
judgement is stored alongside the local lane in ``judgements/cloud/`` so the two
profiles can be compared directly.

Security-sensitive suites are refused outright: real-use scenarios are synthetic
so a cloud judge is allowed there, but anything with security / compliance /
detection in the suite name stays local.
"""

from __future__ import annotations

import contextlib
import json
import os
import urllib.request
from pathlib import Path

import yaml

from tests.wfe.judge import parse_verdict

CLOUD_CONFIG_PATH = Path(__file__).resolve().parent / "judge.yaml"


def _cloud_config() -> dict:
    """The committed cloud profile ({} when the file is absent or unreadable)."""
    with contextlib.suppress(Exception):
        data = yaml.safe_load(CLOUD_CONFIG_PATH.read_text()) or {}
        return (data.get("profiles") or {}).get("cloud") or {}
    return {}


def cloud_model(explicit: str | None = None) -> str:
    model = explicit or os.environ.get("WFE_JUDGE_CLOUD_MODEL") or _cloud_config().get("model")
    if not model:
        raise ValueError(
            "no cloud judge model: set WFE_JUDGE_CLOUD_MODEL, pass --model, or add "
            "profiles.cloud.model to tests/wfe/judge.yaml"
        )
    return model


def cloud_url(explicit: str | None = None) -> str:
    return (
        explicit
        or os.environ.get("WFE_JUDGE_CLOUD_URL")
        or _cloud_config().get("url")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")


def cloud_api_key() -> str:
    key_env = _cloud_config().get("api_key_env") or "OPENAI_API_KEY"
    key = os.environ.get(key_env)
    if not key:
        raise ValueError(
            f"no cloud API key: set {key_env} (from tests/wfe/judge.yaml profiles.cloud.api_key_env)"
        )
    return key


def refuse_cloud_for_security(campaign_dir: Path) -> None:
    """Refuse the cloud profile for any suite name matching realuse_sec* or
    *security*/*compliance*/*detection.  Synthetic real-use scenarios are safe;
    security/PII-adjacent suites are not."""
    manifest = json.loads((campaign_dir / "manifest.json").read_text())
    for m in manifest.get("rows") or []:
        suite = m.get("suite") or ""
        if any(
            p in suite
            for p in (
                "realuse_sec",
                "security",
                "compliance",
                "detection",
            )
        ):
            raise ValueError(
                f"refusing cloud judge for suite {suite!r}: security/compliance/detection "
                "suites must use the local judge (WFE_JUDGE_ALLOW_REMOTE=1 does not help)"
            )


def ask_cloud_judge(
    messages: list[dict],
    model: str,
    url: str,
    api_key: str,
    timeout: int = 600,
) -> str:
    """One cloud judge completion POSTed to an OpenAI-compatible /v1/chat/completions."""
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "seed": 7,
    }
    req = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read() or b"{}")
    choices = out.get("choices") or []
    message = (choices[0] if choices else {}).get("message") or {}
    return str(message.get("content") or "")


def parse_cloud_verdict(text: str) -> tuple[str, str]:
    """Delegate to the shared parser — cloud models are asked to emit the same
    JSON object the local judge expects."""
    return parse_verdict(text)
