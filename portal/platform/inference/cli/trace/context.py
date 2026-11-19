"""Shared plumbing for ``portal trace``: repo settings, HTTP, subprocesses."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

#: Names that only resolve inside the compose network.
CONTAINER_HOSTS = frozenset({"host.docker.internal", "portal-pipeline", "portal_pipeline"})


@dataclass(frozen=True)
class CommandResult:
    """Result of a bounded subprocess call."""

    ok: bool
    stdout: str = ""
    stderr: str = ""

    @property
    def error(self) -> str:
        return (self.stderr or self.stdout).strip()


@dataclass(frozen=True)
class TraceContext:
    """Everything a section needs to reach the live system."""

    repo_root: Path
    pipeline_url: str
    api_key: str
    omlx_url: str
    ollama_url: str
    owui_url: str
    budget_s: float
    timeout_s: float


def env_value(name: str, default: str = "") -> str:
    """``name`` from the environment, else from the repo ``.env``. Never printed."""
    value = os.environ.get(name)
    if value:
        return value
    env_file = Path(__file__).resolve().parents[5] / ".env"
    if not env_file.is_file():
        return default
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(f"{name}="):
            return line.partition("=")[2].strip().strip("\"'") or default
    return default


def host_url(name: str, default: str, override: str = "") -> str:
    """A host-side endpoint: .env carries container hostnames, which become loopback here."""
    value = (env_value(override) if override else "") or env_value(name, default)
    if Path("/.dockerenv").exists():
        return value.rstrip("/")
    host = urlsplit(value).hostname or ""
    if host not in CONTAINER_HOSTS:
        return value.rstrip("/")
    return value.replace(host, "127.0.0.1", 1).rstrip("/")


def run_cmd(cmd: list[str], timeout: float = 20.0) -> CommandResult:
    """Run ``cmd``, capturing output; a missing binary or timeout is a failure, not a crash."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(ok=False, stderr=f"{type(exc).__name__}: {exc}")
    return CommandResult(ok=done.returncode == 0, stdout=done.stdout, stderr=done.stderr)


def expand_env(value: object) -> str:
    """Resolve ``${VAR:-default}`` / ``${VAR}`` in a backends.yaml scalar."""
    text = str(value or "")
    if text.startswith("${") and text.endswith("}"):
        body = text[2:-1]
        name, _, default = body.partition(":-")
        return os.environ.get(name) or default
    return text
