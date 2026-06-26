"""Shared helpers for the portal CLI sub-modules."""
from __future__ import annotations

import os
import subprocess
import sys

def _detect_ollama_cmd() -> str | None:
    """Return the ollama command to use (native or docker exec), or None."""
    # Check native Ollama
    import urllib.request as _ur

    try:
        r = _ur.urlopen("http://localhost:11434/api/tags", timeout=3)
        r.close()
        if subprocess.run(["which", "ollama"], capture_output=True).returncode == 0:
            return "ollama"
    except Exception:
        pass
    # Check Docker Ollama
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        if "portal5-ollama" in result.stdout:
            return "docker exec portal5-ollama ollama"
    except Exception:
        pass
    return None


def _model_exists_in_ollama(model_name: str, ollama_cmd: str) -> bool:
    """Check if a model is already loaded in Ollama."""
    parts = ollama_cmd.split() + ["list"]
    try:
        result = subprocess.run(parts, capture_output=True, text=True, timeout=10)
        for line in result.stdout.lower().splitlines():
            if model_name.lower() in line:
                return True
    except Exception:
        pass
    return False


def _fmt_size(size: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def _resolve_model_name(raw: str) -> str:
    """Resolve ${VAR:-default} env var references in model names."""
    import re as _re

    def _repl(m):
        var, default = m.group(1), m.group(2)
        return os.environ.get(var, default)

    return _re.sub(r"\$\{(\w+):-([^}]+)\}", _repl, raw)

