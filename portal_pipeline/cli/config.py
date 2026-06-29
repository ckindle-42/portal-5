"""``portal config <cmd>`` — config introspection."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from portal_pipeline.config import load_portal_config

from ._apps import config_app


@config_app.command("show")
def config_show(
    raw: Annotated[
        bool, typer.Option("--raw", help="Emit raw YAML values (no env override)")
    ] = False,
) -> None:
    """Print the resolved portal.yaml config as pretty-printed JSON."""
    cfg = load_portal_config()
    data = {
        "ollama_url": cfg.ollama_url,
        "request_timeout": cfg.request_timeout,
        "workspaces": list(cfg.workspaces.keys()),
        "workspace_count": len(cfg.workspaces),
        "mcp_fleet_count": len(cfg.mcp_fleet),
        "mcp_fleet": [
            {
                "id": s.id,
                "name": s.name,
                "port": s.port,
                "expose_to_pipeline": s.expose_to_pipeline,
            }
            for s in cfg.mcp_fleet
        ],
    }
    typer.echo(json.dumps(data, indent=2))
