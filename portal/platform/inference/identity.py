"""oMLX checkpoint content identity shared with the WFE identity guard."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Directory named after the model id. OMLX_MODEL_DIR overrides the server settings.
OMLX_SERVER_SETTINGS = Path(
    os.environ.get("OMLX_SERVER_SETTINGS", str(Path.home() / ".omlx" / "settings.json"))
)
OMLX_SETTINGS = Path(
    os.environ.get("OMLX_SETTINGS", str(Path.home() / ".omlx" / "model_settings.json"))
)
OMLX_DEFAULT_MODEL_DIR = "/Volumes/data01/omlx-models"
# What makes a checkpoint what it is, short of hashing its weights.
OMLX_IDENTITY_FILES = (
    "config.json",
    "tokenizer_config.json",
    "chat_template.jinja",
    "generation_config.json",
)


def omlx_model_dirs(
    *,
    server_settings: Path | None = None,
    default_model_dir: str | None = None,
) -> list[Path]:
    """Where oMLX looks for model directories: OMLX_MODEL_DIR, else its settings."""
    if os.environ.get("OMLX_MODEL_DIR"):
        return [Path(p) for p in os.environ["OMLX_MODEL_DIR"].split(os.pathsep) if p]
    path = OMLX_SERVER_SETTINGS if server_settings is None else server_settings
    fallback = OMLX_DEFAULT_MODEL_DIR if default_model_dir is None else default_model_dir
    try:
        model = json.loads(path.read_text()).get("model") or {}
    except (OSError, ValueError):
        model = {}
    dirs = model.get("model_dirs") or [model.get("model_dir") or fallback]
    return [Path(str(d)).expanduser() for d in dirs if d]


def omlx_content_id(
    model: str,
    *,
    settings: Path | None = None,
    server_settings: Path | None = None,
    default_model_dir: str | None = None,
) -> tuple[str, str]:
    """Content id for an oMLX checkpoint, or ("", why it is unobservable)."""
    dirs = omlx_model_dirs(server_settings=server_settings, default_model_dir=default_model_dir)
    root = next(
        (directory / model for directory in dirs if (directory / model / "config.json").is_file()),
        None,
    )
    if root is None:
        return "", f"no {model}/config.json under {[str(directory) for directory in dirs]}"
    digest = hashlib.sha256()
    for name in OMLX_IDENTITY_FILES:
        identity_file = root / name
        body = identity_file.read_bytes() if identity_file.is_file() else b"-"
        digest.update(name.encode() + b"\0" + body + b"\0")
    for weight in sorted(root.glob("*.safetensors")):
        digest.update(f"{weight.name}:{weight.stat().st_size}\0".encode())
    settings_path = OMLX_SETTINGS if settings is None else settings
    try:
        entry = (json.loads(settings_path.read_text()).get("models") or {}).get(model)
    except (OSError, ValueError):
        entry = None
    digest.update(json.dumps(entry, sort_keys=True).encode())
    return digest.hexdigest()[:32], ""
