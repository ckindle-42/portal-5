"""Shared infrastructure for acceptance section modules.

Delegates to the monolith (portal5_acceptance_v6) at call time, so section
files can import from here without circular imports.  Constants (PIPELINE_URL,
AUTH, etc.) are loaded independently from env so they are available at import
time without touching the monolith.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path

# ── Constants (loaded independently from env) ────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent

_env_file = _ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

PIPELINE_URL = "http://localhost:9099"
OPENWEBUI_URL = "http://localhost:8080"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").replace(
    "host.docker.internal", "localhost"
)
MLX_URL = os.environ.get("MLX_LM_URL", "http://localhost:8081").replace(
    "host.docker.internal", "localhost"
)
API_KEY = os.environ.get("PIPELINE_API_KEY", "")
AUTH = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
MCP = {
    "comfyui": int(os.environ.get("COMFYUI_MCP_HOST_PORT", "8910")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
    "security": int(os.environ.get("SECURITY_HOST_PORT", "8919")),
}

# ── Lazy delegation to monolith ──────────────────────────────────────────────


def _monolith():
    """Return the monolith module.

    When the suite runs as `python3 tests/portal5_acceptance_v6.py`, the
    module is registered as `__main__`.  Importing it by name would create a
    *second* copy with a separate `_log`, so we prefer `__main__` when it
    looks like the monolith (has `record` and `_log`).
    """
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "record") and hasattr(main, "_log"):
        return main
    # Fallback: import by name (works when the suite is imported as a module)
    tests_dir = str(Path(__file__).parent.parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    return importlib.import_module("portal5_acceptance_v6")


def record(
    section: str,
    tid: str,
    name: str,
    status: str,
    detail: str = "",
    evidence: list[str] | None = None,
    fix: str = "",
    t0: float | None = None,
):
    """Record a test result into the monolith's shared log."""
    return _monolith().record(section, tid, name, status, detail, evidence, fix, t0)


async def _get(url: str, timeout: int = 10) -> tuple[int, dict | str]:
    return await _monolith()._get(url, timeout)


async def _post(
    url: str,
    body: dict,
    headers: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict | str]:
    return await _monolith()._post(url, body, headers, timeout)


async def _chat_with_model(
    workspace: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 400,
    timeout: int = 240,
    stream: bool = False,
) -> tuple[int, str, str, str]:
    return await _monolith()._chat_with_model(
        workspace, prompt, system, max_tokens, timeout, stream
    )


async def _mlx_health() -> tuple[str, dict]:
    return await _monolith()._mlx_health()


# ── Additional delegation helpers ────────────────────────────────────────────

ROOT = _ROOT  # alias for section modules

SEARXNG_URL = "http://localhost:8088"
PROMETHEUS_URL = "http://localhost:9090"
GRAFANA_URL = "http://localhost:3000"
COMFYUI_URL = "http://localhost:8188"
EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "http://localhost:8917")


def _docker_alive():
    return _monolith()._docker_alive()


def _git_sha() -> str:
    return _monolith()._git_sha()


def _ollama_models() -> list[str]:
    return _monolith()._ollama_models()


def _load_backends_yaml() -> dict:
    return _monolith()._load_backends_yaml()


def _get_personas() -> list[dict]:
    """Return PERSONAS list from the monolith."""
    return _monolith().PERSONAS


def _get_ws_ids() -> list[str]:
    """Return WS_IDS list from the monolith."""
    return _monolith().WS_IDS
