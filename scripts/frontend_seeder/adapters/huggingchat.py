"""HuggingChat (chat-ui) adapter — generates models config for chat-ui.

chat-ui reads model config from the MODELS environment variable (JSON array).
The generate_models_json() function produces this JSON for runtime use.
The generate_models_yaml() function produces a human-readable YAML for reference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml as _yaml

from frontend_seeder.source import (
    PORTAL_ROOT,
    load_workspaces,
    production_workspaces,
)

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")
PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://portal-pipeline:9099/v1")


def _build_model_list(api_key: str = "", pipeline_url: str = "") -> list[dict[str, Any]]:
    """Build the model list dict shared by YAML and JSON generators."""
    key = api_key or PIPELINE_API_KEY
    url = pipeline_url or PIPELINE_URL
    workspaces = production_workspaces(load_workspaces())
    models: list[dict[str, Any]] = []
    for ws_id, ws_cfg in workspaces.items():
        desc = ws_cfg.get("description", "")
        entry: dict[str, Any] = {
            "name": ws_cfg["name"],
            "id": ws_id,
            "displayName": ws_cfg["name"],
            "description": desc,
            "endpoints": [
                {
                    "type": "openai",
                    "url": url,
                    "authorization": f"Bearer {key}",
                    "model": ws_id,
                }
            ],
            "parameters": {
                "temperature": 0.7,
                "max_new_tokens": 4096,
            },
        }
        if desc:
            entry["preprompt"] = desc
        models.append(entry)
    return models


def generate_models_json(api_key: str = "", pipeline_url: str = "") -> str:
    """Generate chat-ui MODELS JSON string for the MODELS env var.

    chat-ui reads model config from the MODELS environment variable.
    Pass api_key and pipeline_url to override the environment defaults.
    """
    models = _build_model_list(api_key=api_key, pipeline_url=pipeline_url)
    return json.dumps(models, ensure_ascii=False)


def generate_models_yaml(output_path: Path | None = None) -> str:
    """Generate human-readable models.yaml for documentation/reference.

    Note: chat-ui does NOT read this file directly. The MODELS env var (JSON)
    is what chat-ui actually uses. This YAML is kept as a readable reference
    and is committed to the repo with empty API keys.
    """
    models = _build_model_list(api_key="", pipeline_url="")
    # In the committed YAML, use placeholder format for credentials
    for m in models:
        m["endpoints"][0]["authorization"] = "Bearer "
        m["endpoints"][0]["apiKey"] = ""

    out = _yaml.dump(models, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(out)
        print(f"  [huggingchat] Wrote {output_path} ({len(models)} models)")
    return out
